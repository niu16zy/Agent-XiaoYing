import copy

import pytest

from knowledge_agent import KnowledgeTools, load_corpus
from knowledge_agent.agent import Agent, Limits
from knowledge_agent.evidence import EvidenceState
from knowledge_agent.model import Action, ActionError
from knowledge_agent.mock_model import ScriptedModel
from knowledge_agent.render import render_answer
from knowledge_agent.validation import check_result


def citation(doc, quote=None):
    return {"doc_id": doc["doc_id"], "version_date": doc["version_date"], "quote": quote or doc["content"].split('。')[0]+'。', "supports": "规则及条件"}


def result(status="answered", citations=None):
    return Action("ask_user" if status == "needs_clarification" else "finish", {
        "answer": "存在差异，需要确认。", "status": status, "citations": citations or [],
        "conflicts": [{"description": "两条期限冲突"}] if status == "needs_clarification" else [],
        "gaps": ["适用关系不明"], "follow_up_question": "适用哪个制度？" if status == "needs_clarification" else None}, "根据证据判断。")


@pytest.fixture
def conflict(data_dir):
    tools = KnowledgeTools(load_corpus(data_dir, "conflict"))
    state = EvidenceState(tools.corpus.snapshot_id)
    for key in ("D01", "D02"):
        state.add_read(tools.read_document(key).data)
    return state


def test_conflict_is_detected_and_cannot_be_silently_dropped(conflict):
    assert len(conflict.unresolved) == 1
    with pytest.raises(ActionError, match="未解决冲突"):
        check_result(result(citations=[citation(conflict.reads[0])]), conflict)
    response = check_result(result("needs_clarification", [citation(d) for d in conflict.reads]), conflict)
    assert response["conflicts"][0]["doc_ids"] == ["D01", "D02"]


def test_both_sides_must_be_cited(conflict):
    with pytest.raises(ActionError, match="冲突各方"):
        check_result(result("needs_clarification", [citation(conflict.reads[0])]), conflict)


@pytest.mark.parametrize("change", ["version", "quote", "unread"])
def test_invalid_citation(conflict, change):
    c = citation(conflict.reads[0])
    if change == "version": c["version_date"] = "2099-01-01"
    if change == "quote": c["quote"] = "伪造的原文"
    if change == "unread": c["doc_id"] = "D03"
    with pytest.raises(ActionError): conflict.cite(c)


def test_evidence_is_copied_and_offsets_respected(corpus):
    doc = KnowledgeTools(corpus).read_document("D01", 2, 14).data
    state = EvidenceState(corpus.snapshot_id)
    state.add_read(doc)
    c = state.cite(citation(doc, doc["content"]))
    doc["content"] = "mutated"
    assert c["start"] == 2 and c["end"] == 14
    state.reads[0]["content"] = "mutated again"
    assert state.reads[0]["content"] != "mutated again"
    state.add_read(state.reads[0])
    assert len(state.reads) == 1


def test_snapshot_mismatch(corpus):
    state = EvidenceState("another-snapshot")
    with pytest.raises(ValueError): state.add_read(KnowledgeTools(corpus).read_document("D01").data)


def test_newer_date_and_numeric_rule_cannot_resolve(conflict):
    c = conflict.unresolved[0]
    update = {"conflict_id": c["conflict_id"], "topic": "期限", "status": "resolved", "resolution": "新版更优先",
              "citations": [citation(d) for d in conflict.reads], "resolution_citations": [citation(conflict.reads[1])]}
    with pytest.raises(ActionError, match="适用关系"):
        conflict.record({"conflicts": [update]})
    assert conflict.unresolved


def test_explicit_relation_can_be_recorded(data_dir):
    tools = KnowledgeTools(load_corpus(data_dir, "explicit_revision"))
    state = EvidenceState(tools.corpus.snapshot_id)
    for key in ("D11", "D12"): state.add_read(tools.read_document(key).data)
    docs = state.reads
    update = {"conflict_id": "retention", "topic": "临时文件期限", "status": "resolved", "resolution": "8月1日起完成导出的文件按D12，其余按D11。",
              "citations": [citation(d) for d in docs], "resolution_citations": [citation(docs[1], docs[1]["content"])]}
    state.record({"facts": [{"claim": "9月导出的文件保留14天", "citation": citation(docs[1])}], "conflicts": [update]})
    assert not state.unresolved and state.view()["facts"]


def test_scope_differences_are_not_automatic_conflicts(data_dir):
    tools = KnowledgeTools(load_corpus(data_dir, "scope_rules"))
    state = EvidenceState(tools.corpus.snapshot_id)
    for key in ("D05", "D06"): state.add_read(tools.read_document(key).data)
    assert state.unresolved == []


@pytest.mark.parametrize("boundary", ["含当日", "含当天", "当天结束", "当日结束"])
def test_duration_cannot_justify_inclusive_deadline(data_dir, boundary):
    tools = KnowledgeTools(load_corpus(data_dir, "explicit_revision"))
    state = EvidenceState(tools.corpus.snapshot_id)
    doc = tools.read_document("D12").data
    state.add_read(doc)
    action = result(citations=[citation(doc)])
    action.arguments["answer"] = f"保留到9月24日（{boundary}）。"
    with pytest.raises(ActionError, match="包含边界"):
        check_result(action, state)


def test_explicit_inclusive_boundary_is_allowed():
    doc = {"doc_id": "NEW", "version_date": "2026-01-01", "content": "活动截止到10月31日，含当日。",
           "start": 0, "end": 17, "snapshot_id": "custom"}
    doc["end"] = len(doc["content"])
    action = result(citations=[citation(doc, doc["content"])])
    action.arguments["answer"] = doc["content"]
    assert check_result(action, [doc])["status"] == "answered"


@pytest.mark.parametrize("answer", ["检索摘要提示可能是30天，但未经核实。", "检索到的其它文档摘要也均标明不规定期限。"])
def test_search_snippets_cannot_be_repeated_as_final_claims(answer):
    action = result("tool_error")
    action.arguments["answer"] = answer
    with pytest.raises(ActionError, match="检索摘要"):
        check_result(action, [])


def test_conflicts_survive_budget_stop(data_dir):
    tools = KnowledgeTools(load_corpus(data_dir, "conflict"))
    actions = [{"action": "read_document", "arguments": {"doc_id": key}, "reason": "核对原文。"} for key in ("D01", "D02")]
    output = Agent(ScriptedModel(actions), tools, Limits(max_model_turns=2)).run("报销期限")
    assert output["status"] == "incomplete" and output["conflicts"][0]["doc_ids"] == ["D01", "D02"]
    assert "D01" in render_answer(output) and "资料缺口" in render_answer(output)


def test_previous_answer_cannot_be_used_as_authority(corpus):
    state = EvidenceState(corpus.snapshot_id)
    doc = KnowledgeTools(corpus).read_document("D03").data
    state.add_read(doc)
    action = result(citations=[citation(doc)])
    action.arguments["answer"] = "材料包含发票；期限仍按上轮所述规则执行。"
    with pytest.raises(ActionError, match="先前回答"):
        check_result(action, state)


def test_answered_with_declared_conflict_is_rejected(corpus):
    state = EvidenceState(corpus.snapshot_id)
    doc = KnowledgeTools(corpus).read_document("D01").data
    state.add_read(doc)
    action = result(citations=[citation(doc)])
    action.arguments["conflicts"] = [{"description": "存在另一规则，仍选当前答案"}]
    with pytest.raises(ActionError, match="未解决冲突"):
        check_result(action, state)
