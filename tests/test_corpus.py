import json
from dataclasses import FrozenInstanceError

import pytest

from knowledge_agent import KnowledgeTools, load_corpus


def test_hidden_document_cannot_be_read_or_searched(corpus):
    tools = KnowledgeTools(corpus)
    assert tools.read_document("D02").error.code == "DOCUMENT_NOT_FOUND"
    assert "D02" not in {h["doc_id"] for h in tools.search_docs("报销期限", 10).data["hits"]}
    with pytest.raises(TypeError):
        corpus.documents["D02"] = corpus.documents["D01"]
    with pytest.raises(FrozenInstanceError):
        corpus.documents["D01"].content = "changed"


def test_content_mutation_changes_snapshot_and_index(data_dir):
    old = load_corpus(data_dir, "baseline")
    new = load_corpus(data_dir, "deadline_45")
    missing = load_corpus(data_dir, "deadline_missing")
    assert len({c.snapshot_id for c in (old, new, missing)}) == 3
    assert old.documents["D01"].version_date == new.documents["D01"].version_date
    assert "30 个自然日" in old.documents["D01"].content
    assert "45 个自然日" in KnowledgeTools(new).read_document("D01").data["content"]
    assert KnowledgeTools(old).search_docs("45").data["hits"] == []
    assert KnowledgeTools(new).search_docs("45").data["hits"][0]["doc_id"] == "D01"
    assert "期限" not in KnowledgeTools(missing).read_document("D01").data["content"]
    assert load_corpus(data_dir).snapshot_id == old.snapshot_id


@pytest.mark.parametrize("mutation", ["duplicate_doc", "invalid_date", "missing_content", "unknown_ref", "unknown_include", "duplicate_include", "hidden_override", "duplicate_override", "unknown_field"])
def test_invalid_data_fails_fast(data_dir, tmp_path, mutation):
    docs = json.loads((data_dir / "documents.json").read_text(encoding="utf-8"))
    scenarios = json.loads((data_dir / "scenarios.json").read_text(encoding="utf-8"))
    scene = scenarios["scenarios"][0]
    if mutation == "duplicate_doc":
        docs["documents"].append(docs["documents"][0])
    elif mutation == "invalid_date":
        docs["documents"][0]["version_date"] = "2026-02-30"
    elif mutation == "missing_content":
        del docs["documents"][0]["content"]
    elif mutation == "unknown_ref":
        docs["documents"][0]["supersedes"] = ["D999"]
    elif mutation == "unknown_include":
        scene["include_doc_ids"].append("D999")
    elif mutation == "duplicate_include":
        scene["include_doc_ids"].append("D01")
    elif mutation == "hidden_override":
        scene["overrides"] = [{"doc_id": "D02", "content": "hidden"}]
    elif mutation == "duplicate_override":
        scene["overrides"] = [{"doc_id": "D01", "content": "new"}] * 2
    else:
        scene["overrides"] = [{"doc_id": "D01", "answer": "leak"}]
    for name, value in (("documents.json", docs), ("scenarios.json", scenarios)):
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError):
        load_corpus(tmp_path)


def test_unknown_scenario_is_not_silent_fallback(data_dir):
    with pytest.raises(ValueError, match="Unknown scenario"):
        load_corpus(data_dir, "typo")


def test_all_evaluation_evidence_matches_loaded_snapshot(data_dir):
    cases = json.loads((data_dir / "evaluation_cases.json").read_text(encoding="utf-8"))["cases"]
    for case in cases:
        snapshot = load_corpus(data_dir, case["scenario_id"])
        for evidence in case["expected"]["required_evidence"]:
            assert evidence["quote"] in snapshot.documents[evidence["doc_id"]].content
