"""Final structure, citation provenance and conflict-preservation checks."""

from .model import ActionError
from .schemas import TaskStatus
from .evidence import EvidenceState
import re


def check_result(action, evidence):
    state = evidence if isinstance(evidence, EvidenceState) else None
    evidence = state.reads if state else evidence
    result = action.arguments.copy()
    if set(result) != {"answer", "status", "citations", "conflicts", "gaps", "follow_up_question"}:
        raise ActionError("最终结果字段不完整或包含额外字段。")
    if not isinstance(result["answer"], str) or not result["answer"].strip():
        raise ActionError("answer 必须是非空文本。")
    if re.search(r"(?:按|依据|根据|遵循).{0,8}(?:上轮|上次|之前|此前|前面|历史|先前)", result["answer"]):
        raise ActionError("不能以先前回答作为制度依据。只回答当前问题；需要重述旧结论时须重新读取并直接引用当前原文。")
    if result["status"] not in [s.value for s in TaskStatus]:
        raise ActionError("无效任务状态。")
    if not isinstance(result["gaps"], list) or any(not isinstance(x, str) for x in result["gaps"]):
        raise ActionError("gaps 必须是字符串数组。")
    if not isinstance(result["conflicts"], list) or any(not isinstance(x, dict) for x in result["conflicts"]):
        raise ActionError("conflicts 必须是对象数组。")
    if result["status"] == "answered" and result["conflicts"]:
        raise ActionError("answered 不得同时包含未解决冲突；已解决关系请记录到 record_evidence 并在回答中解释。")
    followup = result["follow_up_question"]
    if followup is not None and not isinstance(followup, str):
        raise ActionError("追问必须为文本或 null。")
    if (action.action == "ask_user") != (result["status"] == "needs_clarification"):
        raise ActionError("追问动作必须对应 needs_clarification。")
    if action.action == "ask_user" and (not followup or not followup.strip()):
        raise ActionError("追问必须说明需要用户提供什么。")
    citations = result["citations"]
    if not isinstance(citations, list) or (result["status"] == "answered" and not citations):
        raise ActionError("answered 必须提供已读取原文的引用。")
    enriched = []
    for c in citations:
        if not isinstance(c, dict) or set(c) != {"doc_id", "version_date", "quote", "supports"} or any(not isinstance(v, str) or not v.strip() for v in c.values()):
            raise ActionError("引用字段必须为 doc_id、version_date、quote、supports 非空文本。")
        match = next((doc for doc in evidence if doc["doc_id"] == c["doc_id"] and doc["version_date"] == c["version_date"] and c["quote"] in doc["content"]), None)
        if match is None:
            raise ActionError("引用不匹配本次成功读取的原文或版本，请重新读取或修正。")
        start = match["start"] + match["content"].index(c["quote"])
        enriched.append({**c, "start": start, "end": start + len(c["quote"]), "snapshot_id": match["snapshot_id"]})
    result["citations"] = enriched
    # Conservative boundary guard, not a general semantic-entailment checker.
    # A duration alone cannot justify an inclusive end-date/time assertion.
    quoted = "".join(c["quote"] for c in enriched)
    for snippet_claim in re.findall(r"(?:检索[^。\n]{0,60}摘要|摘要)[^。\n]{0,12}(?:显示|提示|表明|标明)", result["answer"]):
        if snippet_claim not in quoted:
            raise ActionError("最终回答不能转述检索摘要中的制度断言。删除该断言，或成功读取原文并引用后再回答；仅删除引用是不够的。")
    for boundary in ("含当日", "含当天", "当天结束", "当日结束"):
        if boundary in result["answer"] and boundary not in quoted:
            raise ActionError("引文未明确支持截止日期的包含边界。仅报告原文时长与起算点，不自行补充含当日或截止时刻。")
    if state and state.unresolved:
        if result["status"] not in {"needs_clarification", "incomplete", "tool_error"}:
            raise ActionError("存在未解决冲突，不能选定单一答案或省略冲突。")
        if result["status"] == "needs_clarification":
            needed = {doc for conflict in state.unresolved for doc in conflict["doc_ids"]}
            if not needed <= {c["doc_id"] for c in enriched} or not result["conflicts"]:
                raise ActionError("请列出未解决冲突，并引用冲突各方原文。")
        result["conflicts"] = state.unresolved
    if result["status"] in {"tool_error", "incomplete", "insufficient_evidence"} and not result["gaps"]:
        raise ActionError("未完成结果必须说明资料缺口。")
    return result

