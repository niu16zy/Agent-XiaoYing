"""Human-readable view of the same validated result saved as JSON."""

LABELS = {"answered": "已回答", "needs_clarification": "需要确认", "insufficient_evidence": "资料不足", "tool_error": "调用失败", "incomplete": "未完成"}


def render_answer(result):
    lines = [f"任务状态：{LABELS.get(result['status'], result['status'])}", "", result["answer"]]
    if result.get("mode") == "mock":
        lines.insert(0, "离线 Mock：仅验证流程，不证明真实模型决策效果。")
    if result.get("citations"):
        lines += ["", "原文引用："]
        for c in result["citations"]:
            lines += [f"- {c['doc_id']}（版本 {c['version_date']}）：{c['quote']}", f"  支持：{c['supports']}"]
    if result.get("conflicts"):
        lines += ["", "资料冲突："]
        for c in result["conflicts"]:
            lines.append("- " + c.get("topic", c.get("description", "存在待确认的规则差异")))
            for cite in c.get("citations", []):
                lines.append(f"  {cite['doc_id']}：{cite['quote']}")
    if result.get("gaps"):
        lines += ["", "资料缺口："] + [f"- {gap}" for gap in result["gaps"]]
    if result.get("follow_up_question"):
        lines += ["", "需要确认：" + result["follow_up_question"]]
    return "\n".join(lines) + "\n"
