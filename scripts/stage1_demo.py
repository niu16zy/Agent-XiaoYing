"""Run business tools explicitly. This script is NOT a model/Agent trace."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge_agent import KnowledgeTools, load_corpus
from knowledge_agent.tools import FaultInjection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="baseline")
    parser.add_argument("--query", default="报销期限多久？")
    parser.add_argument("--read-id", default="D01")
    parser.add_argument("--retrieval-mode", choices=["baseline", "improved"], default="improved")
    parser.add_argument("--fail-read", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        corpus = load_corpus(ROOT / "data", args.scenario)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    fault = FaultInjection("read_document", {"doc_id": args.read_id}, "all_matching_calls", "TOOL_UNAVAILABLE", False) if args.fail_read else None
    tools = KnowledgeTools(corpus, args.retrieval_mode, fault)
    result = {"kind": "stage1_tool_demo", "model_called": False,
              "input": {"scenario": args.scenario, "query": args.query, "read_id": args.read_id,
                        "retrieval_mode": args.retrieval_mode, "fail_read": args.fail_read},
              "snapshot_id": corpus.snapshot_id,
              "search": tools.search_docs(args.query).to_dict(),
              "read": tools.read_document(args.read_id).to_dict()}
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
