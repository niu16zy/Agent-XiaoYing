"""Offline by default. --mode real explicitly enables paid API evaluation."""

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowledge_agent.config import load_env
from knowledge_agent.evaluation import expand_cases, mutation_comparisons, retrieval_experiment, run_case, source_manifest
from knowledge_agent.model import OpenAIModel
from knowledge_agent.trace import RunTrace


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline", "real"), default="offline")
    parser.add_argument("--cases", nargs="+", help="Exact expanded IDs, e.g. T04 T04-v1")
    parser.add_argument("--compare-baseline", action="store_true", help="Additional same-model literal-retrieval runs")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "examples/stage4")
    args = parser.parse_args()
    cases = expand_cases(json.loads((ROOT / "data/evaluation_cases.json").read_text(encoding="utf-8"))["cases"])
    if args.cases and set(args.cases) - {c["case_id"] for c in cases}:
        parser.error("Unknown case ID")
    if args.mode == "offline" and args.cases and set(args.cases) != {"T10"}:
        parser.error("Offline mode only executes T10; use --mode real for business cases")
    if args.compare_baseline and args.mode != "real":
        parser.error("--compare-baseline requires --mode real")
    selected = [c for c in cases if not args.cases or c["case_id"] in args.cases]
    if args.mode == "offline":
        selected = [c for c in selected if c["case_id"] == "T10"]
    load_env(ROOT / ".env")
    batch = RunTrace(args.output_dir)
    started = datetime.now(timezone.utc).isoformat()
    packages = {}
    for name in ("openai", "pytest", "setuptools"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    batch.write("manifest.json", {"started_at": started, "mode": args.mode, "python": platform.python_version(),
                "platform": platform.platform(), "packages": packages, "source_sha256": source_manifest(ROOT),
                "case_ids": [c["case_id"] for c in selected], "compare_baseline": args.compare_baseline})
    batch.write("retrieval-comparison.json", retrieval_experiment(cases, ROOT / "data"))
    rows = []
    schedule = [(c, "improved") for c in selected]
    if args.compare_baseline:
        schedule += [(c, "baseline") for c in selected if c["case_id"] in {"T01", "T02", "T04", "T04-v1", "T04-v2", "T13"}]
    for case, mode in schedule:
        model = None if case["case_id"] == "T10" else OpenAIModel()
        row = run_case(case, ROOT / "data", batch.directory / mode, model, mode)
        artifact_path = Path(row["artifact_dir"]).resolve()
        row["artifact_dir"] = (artifact_path.relative_to(ROOT).as_posix()
                               if artifact_path.is_relative_to(ROOT) else artifact_path.as_posix())
        rows.append(row)
        # Save partial results after each case; interruptions do not erase evidence.
        batch.write("results.json", {"mode": args.mode, "rows": rows, "complete": False})
        print(json.dumps({k: row[k] for k in ("case_id", "retrieval_mode", "status", "automatic_pass", "run_id")}, ensure_ascii=False), flush=True)
    batch.write("mutations.json", mutation_comparisons(rows))
    batch.write("results.json", {"mode": args.mode, "rows": rows, "complete": True, "started_at": started,
                "finished_at": datetime.now(timezone.utc).isoformat(), "semantic_review": "pending" if args.mode == "real" else "not_applicable_mock"})
    print(json.dumps({"batch_dir": str(batch.directory), "note": "Automatic checks are not semantic acceptance."}))
    return 1 if any(not r["automatic_pass"] for r in rows if r["retrieval_mode"] == "improved") else 0


if __name__ == "__main__":
    raise SystemExit(main())
