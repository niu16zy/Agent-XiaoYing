"""CLI for explicit real and offline runs. Outputs structured JSON and artifacts."""

import argparse
import json
from pathlib import Path
import sys

from .agent import Agent, Limits, validate_input
from .corpus import load_corpus
from .config import load_env
from .mock_model import MockModel, ScriptedModel
from .model import ModelError, OpenAIModel
from .schemas import Answer, TaskStatus
from .tools import FaultInjection, KnowledgeTools
from .trace import RunTrace
from .render import render_answer


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--question")
    inputs.add_argument("--input", type=Path, help="JSON with question and optional history only")
    parser.add_argument("--mode", choices=["real", "mock"], default="mock")
    parser.add_argument("--scenario", default="baseline")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, help="Parent directory; each run creates a new subdirectory")
    parser.add_argument("--model")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--base-url")
    parser.add_argument("--mock-actions", type=Path, help="JSON action array; mock mode only")
    parser.add_argument("--fault", type=Path, help="Test-only fault configuration JSON")
    parser.add_argument("--max-model-turns", type=int, default=8)
    parser.add_argument("--max-tool-calls", type=int, default=6)
    parser.add_argument("--model-timeout", type=float, default=30)
    parser.add_argument("--tool-timeout", type=float, default=5)
    parser.add_argument("--total-timeout", type=float, default=120)
    args = parser.parse_args(argv)
    try:
        load_env(args.env_file)
        data = json.loads(args.input.read_text(encoding="utf-8-sig")) if args.input else {"question": args.question}
        if not isinstance(data, dict) or set(data) - {"question", "history"}:
            raise ValueError("输入文件只允许 question 和 history 字段。")
        validate_input(data.get("question"), data.get("history", []))
        limits = Limits(args.max_model_turns, args.max_tool_calls, args.model_timeout, args.tool_timeout, args.total_timeout)
        corpus = load_corpus(args.data_dir, args.scenario)
        fault = FaultInjection(**json.loads(args.fault.read_text(encoding="utf-8-sig"))) if args.fault else None
        if args.mode == "real" and args.mock_actions:
            raise ValueError("真实模式不能使用 Mock 动作。")
        actions = json.loads(args.mock_actions.read_text(encoding="utf-8-sig")) if args.mock_actions else None
        if actions is not None and not isinstance(actions, list):
            raise ValueError("Mock 动作必须为数组。")
    except (OSError, ValueError, TypeError):
        parser.error("输入/配置无效：请检查 JSON 字段、场景、路径和预算。")
    trace = RunTrace(args.output_dir or Path("examples") / args.mode)
    trace.write("run-config.json", {"mode": args.mode, "scenario": args.scenario,
                                   "fault": json.loads(args.fault.read_text(encoding="utf-8-sig")) if args.fault else None})
    try:
        model = OpenAIModel(args.model, args.base_url) if args.mode == "real" else (ScriptedModel(actions) if actions is not None else MockModel())
    except ModelError as exc:
        result = Answer("模型配置不可用。", TaskStatus.TOOL_ERROR, gaps=["请配置可用的模型服务。"] ).to_dict()
        result.update({"mode": args.mode, "run_id": trace.run_id, "model_turns": 0, "tool_calls": 0,
                       "error": {"source": "model", "code": exc.code}})
        trace.write("input.json", data)
        trace.add(event="configuration_error", code=exc.code)
        trace.write("output.json", result)
    else:
        trace.write("model-config.json", {"mode": model.mode, "model": model.name,
                    "endpoint": getattr(model, "endpoint", None), "sdk_retries": 0,
                    "response_format": "json_object" if model.mode == "real" else None})
        result = Agent(model, KnowledgeTools(corpus, fault=fault), limits, trace).run(data["question"], data.get("history", []))
    result = trace.clean({**result, "artifact_dir": str(trace.directory.resolve())})
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(render_answer(result) if args.format == "text" else json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] in {"tool_error", "incomplete"} else 0
