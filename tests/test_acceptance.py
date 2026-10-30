"""Evaluator regressions and explicitly opted-in live checks (not semantic grading)."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from knowledge_agent import load_corpus
from knowledge_agent.agent import Limits
from knowledge_agent.evaluation import check_run, expand_cases, mutation_comparisons, retrieval_experiment, run_case
from knowledge_agent.mock_model import ScriptedModel


ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "data/evaluation_cases.json").read_text(encoding="utf-8"))["cases"]


def get_case(key):
    return copy.deepcopy(next(c for c in CASES if c["case_id"] == key))


def test_variants_are_separate_inputs():
    cases = expand_cases(CASES)
    assert len(cases) == 16 and len({c["case_id"] for c in cases}) == 16
    assert len({c["question"] for c in cases if c["case_id"].startswith("T04")}) == 3
    cases[0]["expected"]["status"] = "tampered"
    assert CASES[0]["expected"]["status"] == "answered"


def test_budget_case_and_no_silent_fallback(data_dir, tmp_path):
    row = run_case(get_case("T10"), data_dir, tmp_path)
    assert row["automatic_pass"] and row["mode"] == "mock"
    assert row["model_turns"] == row["tool_calls"] == 2
    assert row["semantic_review"] == "not_applicable_mock"
    with pytest.raises(ValueError, match="explicit model"):
        run_case(get_case("T01"), data_dir, tmp_path)


class SpyModel(ScriptedModel):
    def choose(self, messages, timeout):
        self.messages = copy.deepcopy(messages)
        return super().choose(messages, timeout)


def test_gold_labels_never_reach_model(data_dir, tmp_path):
    case = get_case("T01")
    case["expected"]["constraints"].append("GOLD_LABEL_SECRET_CANARY")
    model = SpyModel([{"action": "finish", "reason": "测试无依据停止。", "arguments": {
        "answer": "未确认", "status": "insufficient_evidence", "citations": [], "conflicts": [],
        "gaps": ["没有原文"], "follow_up_question": None}}])
    row = run_case(case, data_dir, tmp_path, model)
    payload = json.dumps(model.messages, ensure_ascii=False)
    assert "GOLD_LABEL_SECRET_CANARY" not in payload
    assert '"expected"' not in payload and '"scenario_id"' not in payload and '"case_id"' not in payload
    assert not row["automatic_pass"]


@pytest.fixture
def checked_run(data_dir, tmp_path):
    corpus = load_corpus(data_dir, "baseline")
    case = get_case("T01")
    model = ScriptedModel([
        {"action": "read_document", "arguments": {"doc_id": "D01"}, "reason": "读取原文。"},
        {"action": "finish", "reason": "引用已读依据。", "arguments": {
            "answer": "自费用发生之日起30个自然日。", "status": "answered", "citations": [{
                "doc_id": "D01", "version_date": corpus.documents["D01"].version_date,
                "quote": case["expected"]["required_evidence"][0]["quote"], "supports": "报销期限"}],
            "conflicts": [], "gaps": [], "follow_up_question": None}}])
    row = run_case(case, data_dir, tmp_path, model)
    directory = Path(row["artifact_dir"])
    output = json.loads((directory / "output.json").read_text(encoding="utf-8"))
    events = [json.loads(line) for line in (directory / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert row["automatic_pass"]
    return case, output, events, corpus


@pytest.mark.parametrize("tampering", ["quote", "version", "offset", "snapshot", "unread", "trace", "budget", "missing_quote"])
def test_evaluator_rejects_bad_records(checked_run, tampering):
    case, output, events, corpus = checked_run
    if tampering == "quote": output["citations"][0]["quote"] = "假的原文"
    if tampering == "version": output["citations"][0]["version_date"] = "2099-01-01"
    if tampering == "offset": output["citations"][0]["start"] += 1
    if tampering == "snapshot": output["citations"][0]["snapshot_id"] = "old-index"
    if tampering == "unread": events = [e for e in events if e["event"] != "observation"]
    if tampering == "trace": events.pop()
    if tampering == "budget": output["model_turns"] = 9
    if tampering == "missing_quote": output["citations"] = []
    assert not check_run(case, output, events, corpus, Limits())["automatic_pass"]


def test_status_only_does_not_pass_tool_failure(checked_run):
    _, output, events, corpus = checked_run
    output.update(status="tool_error", citations=[], gaps=["失败"], error={"source": "model"})
    report = check_run(get_case("T06B"), output, events, corpus, Limits())
    assert report["checks"]["status"]
    assert not report["checks"]["fault_observed"] and not report["checks"]["failure_not_model_api"]
    assert not report["automatic_pass"]


def test_valid_citation_is_not_semantic_proof(checked_run):
    case, output, events, corpus = checked_run
    output.update(mode="real", answer="报销期限为999天。")
    report = check_run(case, output, events, corpus, Limits())
    assert report["automatic_pass"]  # Provenance is valid; the answer is still false.
    assert report["semantic_review"] == "pending"


def test_comparison_uses_same_queries_and_keeps_conflict_sides(data_dir):
    result = retrieval_experiment(expand_cases(CASES), data_dir)
    row = next(r for r in result["rows"] if r["case_id"] == "T02")
    assert set(row["required_doc_ids"]) == {"D01", "D02"}
    assert row["improved"]["recall"] == 1
    assert result["summary"]["baseline"]["cases"] == result["summary"]["improved"]["cases"]
    assert "T03" not in {r["case_id"] for r in result["rows"]}


def test_mutations_report_real_changes_not_inferred_success():
    base = {"case_id": "T01", "run_id": "a", "retrieval_mode": "improved", "snapshot_id": "a",
            "status": "answered", "actions": ["finish"], "action_details": [], "automatic_pass": True}
    changed = {**base, "case_id": "T08", "run_id": "b", "snapshot_id": "b", "automatic_pass": False}
    result = mutation_comparisons([base, changed])[0]
    assert result["snapshot_changed"] and not result["automatic_checks_pass"]
    assert not result["action_details_changed"] and result["semantic_review"] == "pending"


def test_cli_offline_and_external_output_folder(tmp_path):
    result = subprocess.run([sys.executable, "scripts/evaluate.py", "--output-dir", str(tmp_path)],
                            cwd=ROOT, capture_output=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    report = json.loads(next(tmp_path.glob("*/results.json")).read_text(encoding="utf-8"))
    assert report["complete"] and [r["case_id"] for r in report["rows"]] == ["T10"]


@pytest.mark.skipif(os.getenv("KNOWLEDGE_AGENT_LIVE") != "1", reason="Set KNOWLEDGE_AGENT_LIVE=1 to explicitly enable paid API smoke test")
def test_opt_in_live_core(data_dir, tmp_path):
    from knowledge_agent.config import load_env
    from knowledge_agent.model import OpenAIModel
    load_env(ROOT / ".env")
    report = run_case(get_case("T01"), data_dir, tmp_path, OpenAIModel())
    assert report["automatic_pass"]  # Full semantic acceptance is recorded separately.
