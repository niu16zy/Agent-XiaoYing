"""Evaluation-only helpers. Gold labels never enter Agent.run or the corpus."""

import copy
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from .agent import Agent, Limits
from .corpus import load_corpus
from .mock_model import ScriptedModel
from .retrieval import Retriever
from .tools import FaultInjection, KnowledgeTools
from .trace import RunTrace


def expand_cases(cases):
    expanded = []
    for case in cases:
        expanded.append(copy.deepcopy(case))
        for number, question in enumerate(case.get("question_variants", []), 1):
            variant = copy.deepcopy(case)
            variant.update(case_id=f'{case["case_id"]}-v{number}', question=question)
            expanded.append(variant)
    return expanded


def source_manifest(root):
    paths = [*Path(root).glob("src/**/*.py"), *Path(root).glob("scripts/*.py"),
             *Path(root).glob("data/*.json"), Path(root) / "pyproject.toml"]
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def check_run(case, output, events, corpus, limits):
    """Structural/provenance checks only; semantic review remains mandatory."""
    checks = {}
    expected = case["expected"]
    checks["status"] = output["status"] in expected.get("status_in", [expected.get("status")])
    observations = [e for e in events if e["event"] == "observation"]
    actions = [e for e in events if e["event"] == "action"]
    reads = [e["observation"]["data"] for e in observations
             if e["tool"] == "read_document" and e["observation"]["ok"]]
    checks["budget"] = (output["model_turns"] <= limits.max_model_turns
                        and output["tool_calls"] <= limits.max_tool_calls
                        and output["tool_calls"] == len(observations))
    checks["trace_complete"] = bool(events and events[-1]["event"] == "completed"
                                     and events[-1]["status"] == output["status"])
    checks["read_snapshots"] = all(
        r["snapshot_id"] == corpus.snapshot_id and r["doc_id"] in corpus.documents
        and r["content"] == corpus.documents[r["doc_id"]].content[r["start"]:r["end"]]
        and r["version_date"] == corpus.documents[r["doc_id"]].version_date for r in reads)

    def valid_citation(c):
        doc = corpus.documents.get(c.get("doc_id"))
        start, end = c.get("start"), c.get("end")
        return bool(doc and type(start) is int and type(end) is int and 0 <= start < end <= len(doc.content)
                    and c.get("quote") == doc.content[start:end]
                    and c.get("version_date") == doc.version_date
                    and c.get("snapshot_id") == corpus.snapshot_id
                    and any(r["doc_id"] == doc.doc_id and r["start"] <= start < end <= r["end"] for r in reads))

    citations = output["citations"]
    checks["citation_provenance"] = all(valid_citation(c) for c in citations)
    checks["answered_has_citations"] = output["status"] != "answered" or bool(citations)
    checks["nonanswer_has_gaps"] = output["status"] == "answered" or bool(output["gaps"])
    checks["clarification_has_question"] = output["status"] != "needs_clarification" or bool(output["follow_up_question"])
    checks["no_answered_conflicts"] = output["status"] != "answered" or not output["conflicts"]
    coverage = []
    for required in expected.get("required_evidence", []):
        doc = corpus.documents[required["doc_id"]]
        start = doc.content.find(required["quote"])
        spans = [(c.get("start", -1), c.get("end", -1)) for c in citations
                 if c["doc_id"] == doc.doc_id and valid_citation(c)]
        # Permit multiple adjacent quotations; every original character must be covered.
        coverage.append(start >= 0 and all(any(a <= i < b for a, b in spans)
                        for i in range(start, start + len(required["quote"]))))
    checks["required_evidence_coverage"] = all(coverage)
    outcome = "not_applicable"
    if case.get("fault_injection"):
        fault = case["fault_injection"]
        failures = [e for e in observations if e["tool"] == fault["tool"]
                    and not e["observation"]["ok"]
                    and e["observation"]["error"]["code"] == fault["error_code"]]
        checks["fault_observed"] = bool(failures)
        checks["model_decision_after_failure"] = bool(failures and any(
            a["model_turn"] > failures[0]["model_turn"] for a in actions))
        checks["failure_not_model_api"] = output.get("error", {}).get("source") != "model"
        if output["status"] == "answered":
            target = fault["match_args"]["doc_id"]
            checks["recovered_read"] = bool(failures and any(
                e["model_turn"] > failures[0]["model_turn"] and e["tool"] == "read_document"
                and e["observation"]["ok"] and e["observation"]["data"]["doc_id"] == target for e in observations))
            checks["recovered_citation"] = any(c["doc_id"] == target and valid_citation(c) for c in citations)
            outcome = "recovered"
        else:
            outcome = "safe_stop" if output["status"] == "tool_error" else "budget_or_other_failure"
    if case["case_id"] == "T10":
        checks["budget_stop"] = output.get("error", {}).get("code") == "BUDGET_EXHAUSTED"
    return {"checks": checks, "automatic_pass": all(checks.values()),
            "fault_outcome": outcome, "semantic_review": "pending" if output["mode"] == "real" else "not_applicable_mock",
            "review_requirements": expected, "actions": [a["action"] for a in actions],
            "action_details": [{"action": a["action"], "arguments": a["arguments"]} for a in actions],
            "status": output["status"], "model_turns": output["model_turns"], "tool_calls": output["tool_calls"]}


def run_case(case, data_dir, output_dir, model=None, retrieval_mode="improved"):
    """The only model-visible input here is question/history and tool observations."""
    mock = case.get("runtime_overrides", {}).get("model_mode") == "mock"
    if mock:
        model = ScriptedModel([{**a, "reason": "离线预算工程测试。"} for a in case["forced_mock_actions"]])
        limits = Limits(max_model_turns=case["runtime_overrides"]["max_model_turns"],
                        max_tool_calls=case["runtime_overrides"]["max_tool_calls"])
    else:
        if model is None:
            raise ValueError("Real cases require an explicit model; no silent Mock fallback")
        limits = Limits(model_timeout=90, total_timeout=300)
    corpus = load_corpus(data_dir, case["scenario_id"])
    tools = KnowledgeTools(corpus, retrieval_mode=retrieval_mode,
                           fault=FaultInjection(**case["fault_injection"]) if case.get("fault_injection") else None)
    trace = RunTrace(output_dir)
    trace.write("run-config.json", {"case_id": case["case_id"], "scenario": case["scenario_id"],
                "retrieval_mode": retrieval_mode, "fault": case.get("fault_injection"), "limits": asdict(limits)})
    trace.write("model-config.json", {"mode": model.mode, "model": model.name, "endpoint": getattr(model, "endpoint", None),
                "request_parameters": ({"response_format": "json_object", "max_tokens": 8192,
                    "thinking": "enabled", "reasoning_effort": "high", "sdk_max_retries": 0}
                    if getattr(model, "is_deepseek", False) else {"adapter": type(model).__name__})})
    output = Agent(model, tools, limits, trace).run(case["question"], case.get("history", []))
    report = check_run(case, output, trace.events, corpus, limits)
    trace.write("automatic-checks.json", report)
    return {"case_id": case["case_id"], "run_id": trace.run_id, "mode": model.mode,
            "snapshot_id": corpus.snapshot_id, "retrieval_mode": retrieval_mode,
            "artifact_dir": trace.directory.as_posix(), **report}


def retrieval_experiment(cases, data_dir, top_k=5):
    rows = []
    for case in cases:
        relevant = {r["doc_id"] for r in case["expected"].get("required_evidence", [])}
        if not relevant:
            continue  # No gold relevance labels: do not invent a recall score.
        corpus = load_corpus(data_dir, case["scenario_id"])
        query = " ".join([h["content"] for h in case.get("history", []) if h["role"] == "user"] + [case["question"]])
        row = {"case_id": case["case_id"], "query": query, "snapshot_id": corpus.snapshot_id,
               "required_doc_ids": sorted(relevant)}
        for mode in ("baseline", "improved"):
            hits = [h["doc_id"] for h in Retriever(corpus, mode).search(query, top_k)["hits"]]
            row[mode] = {"hits": hits, "recall": len(relevant.intersection(hits)) / len(relevant),
                         "all_required_found": relevant.issubset(hits)}
        rows.append(row)
    return {"top_k": top_k, "query_policy": "Previous user messages plus current question, identical for both modes; no gold queries.",
            "baseline": "NFKC/lowercase literal full-query substring match; intentionally simple, not BM25/vector search.",
            "limitations": "Small synthetic development set, includes related variants; no held-out/generalization claim. Recall excludes unlabeled cases; no precision labels.",
            "rows": rows, "summary": {mode: {"cases": len(rows),
                "macro_recall": sum(r[mode]["recall"] for r in rows) / len(rows) if rows else None,
                "all_required_found": sum(r[mode]["all_required_found"] for r in rows)} for mode in ("baseline", "improved")}}


def mutation_comparisons(rows):
    indexed = {r["case_id"]: r for r in rows if r["retrieval_mode"] == "improved"}
    if "T01" not in indexed:
        return []
    base = indexed["T01"]
    return [{"baseline": "T01", "changed": key, "baseline_run": base["run_id"], "changed_run": row["run_id"],
             "snapshot_changed": base["snapshot_id"] != row["snapshot_id"],
             "statuses": [base["status"], row["status"]],
             "action_sequences": [base["actions"], row["actions"]],
             "action_details_changed": base["action_details"] != row["action_details"],
             "automatic_checks_pass": base["automatic_pass"] and row["automatic_pass"],
             "semantic_review": "pending"} for key in ("T07", "T08", "T09") if (row := indexed.get(key))]
