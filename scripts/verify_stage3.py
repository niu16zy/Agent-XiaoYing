"""Run bounded stage-three live cases; status checks are NOT semantic grading."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge_agent import load_corpus, KnowledgeTools
from knowledge_agent.agent import Agent, Limits
from knowledge_agent.config import load_env
from knowledge_agent.model import OpenAIModel
from knowledge_agent.tools import FaultInjection
from knowledge_agent.trace import RunTrace


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_env(ROOT / ".env")
    selected = sys.argv[1:] or ["T01", "T02", "T03", "T04", "T05", "T06A", "T06B", "T09", "T11", "T12"]
    cases = json.loads((ROOT / "data/evaluation_cases.json").read_text(encoding="utf-8"))["cases"]
    known = {c["case_id"]: c for c in cases}
    if any(key not in known for key in selected): raise SystemExit("Unknown case ID")
    for key in selected:
        case = known[key]
        # Only question/history enter the model. IDs and expectations remain outside it.
        model = OpenAIModel()
        trace = RunTrace(ROOT / "examples/stage3/real")
        tools = KnowledgeTools(load_corpus(ROOT / "data", case["scenario_id"]), fault=FaultInjection(**case["fault_injection"]) if "fault_injection" in case else None)
        trace.write("run-config.json", {"case_id": key, "scenario": case["scenario_id"], "fault": case.get("fault_injection")})
        trace.write("model-config.json", {"model": model.name, "endpoint": model.endpoint, "thinking": "enabled", "reasoning_effort": "high"})
        output = Agent(model, tools, Limits(model_timeout=90, total_timeout=300), trace).run(case["question"], case["history"])
        expected = case["expected"].get("status_in", [case["expected"].get("status")])
        trace.write("status-check.json", {"case_id": key, "expected_statuses": expected, "status_matches": output["status"] in expected, "semantic_review": "pending"})
        print(json.dumps({"case_id": key, "run_id": trace.run_id, "status": output["status"], "status_matches": output["status"] in expected}, ensure_ascii=False), flush=True)


if __name__ == "__main__": main()
