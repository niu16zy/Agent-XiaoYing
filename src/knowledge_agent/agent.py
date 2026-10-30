"""Bounded model/action/observation loop. No scenario-specific answer branches."""

import inspect
import copy
import json
import math
from dataclasses import asdict, dataclass
from queue import Empty, Queue
from threading import Thread
from time import monotonic

from .model import Action, ActionError, ModelError
from .prompts import SYSTEM_PROMPT
from .schemas import Answer, TaskStatus, ToolError, ToolResult
from .trace import RunTrace
from .evidence import EvidenceState
from .validation import check_result
from .render import render_answer


@dataclass(frozen=True)
class Limits:
    max_model_turns: int = 8
    max_tool_calls: int = 6
    model_timeout: float = 30
    tool_timeout: float = 5
    total_timeout: float = 120

    def __post_init__(self):
        for name in ("max_model_turns", "max_tool_calls"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError("调用预算必须为正整数。")
        for name in ("model_timeout", "tool_timeout", "total_timeout"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("超时必须为有限正数。")


def bounded_call(call, timeout):
    """Stop waiting at the deadline. Timed-out daemon work is not forcibly killed."""
    queue = Queue(maxsize=1)

    def worker():
        try:
            queue.put((True, call()))
        except Exception as exc:
            queue.put((False, exc))
    Thread(target=worker, daemon=True).start()
    try:
        ok, value = queue.get(timeout=max(0, timeout))
    except Empty:
        raise TimeoutError from None
    if not ok:
        raise value
    return value


def validate_input(question, history):
    if not isinstance(question, str) or not question.strip() or len(question) > 4000:
        raise ValueError("问题必须是 1 至 4000 字符的非空文本。")
    if not isinstance(history, list) or len(history) > 20:
        raise ValueError("历史必须为最多 20 条消息的数组。")
    for item in history:
        if not isinstance(item, dict) or set(item) != {"role", "content"} or item["role"] not in ("user", "assistant") or not isinstance(item["content"], str) or len(item["content"]) > 8000:
            raise ValueError("历史只允许 user/assistant 文本消息。")




class Agent:
    def __init__(self, model, tools, limits=None, trace=None):
        self.model, self.tools = model, tools
        self.limits = limits or Limits()
        self.trace = trace or RunTrace()

    def run(self, question, history=None):
        history = [] if history is None else history
        validate_input(question, history)
        start = monotonic()
        turns = calls = 0
        evidence = EvidenceState(self.tools.corpus.snapshot_id)
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps({"question": question, "history": history}, ensure_ascii=False)}]
        self.trace.write("input.json", {"question": question, "history": history, "mode": self.model.mode,
            "model": self.model.name, "snapshot_id": self.tools.corpus.snapshot_id, "limits": asdict(self.limits)})

        def complete(result, source=None, code=None):
            result = {**result, "run_id": self.trace.run_id, "mode": self.model.mode,
                      "model_turns": turns, "tool_calls": calls, "elapsed_seconds": round(monotonic() - start, 3)}
            if source:
                result["error"] = {"source": source, "code": code}
            self.trace.add(event="completed", status=result["status"], model_turns=turns, tool_calls=calls, error=result.get("error"))
            self.trace.write("output.json", result)
            self.trace.write("evidence.json", evidence.reads)
            self.trace.write("evidence-state.json", evidence.view())
            self.trace.write_text("answer.txt", render_answer(result))
            return result

        def stop(status, gap, source=None, code=None):
            return complete(Answer("当前任务未能完成。", status, conflicts=evidence.unresolved, gaps=[gap]).to_dict(), source, code)

        while turns < self.limits.max_model_turns:
            remaining = self.limits.total_timeout - (monotonic() - start)
            if remaining <= 0 or calls >= self.limits.max_tool_calls:
                return stop(TaskStatus.INCOMPLETE, "执行时间或工具调用预算已耗尽。", "executor", "BUDGET_EXHAUSTED")
            messages.append({"role": "user", "content": json.dumps({"remaining_budget": {
                "model_turns": self.limits.max_model_turns - turns,
                "tool_calls": self.limits.max_tool_calls - calls}, "evidence_state": evidence.view()})})
            turns += 1
            try:
                timeout = min(self.limits.model_timeout, remaining)
                request_messages = copy.deepcopy(messages)
                raw = bounded_call(lambda: self.model.choose(request_messages, timeout), timeout)
                action = Action.parse(raw)
            except ActionError as exc:
                self.trace.add(event="invalid_action", model_turn=turns, message=str(exc))
                messages.append({"role": "user", "content": json.dumps({"validation_error": str(exc)}, ensure_ascii=False)})
                continue
            except (TimeoutError, ModelError) as exc:
                if monotonic() - start >= self.limits.total_timeout:
                    return stop(TaskStatus.INCOMPLETE, "总执行时间已耗尽。", "executor", "BUDGET_EXHAUSTED")
                code = exc.code if isinstance(exc, ModelError) else "MODEL_TIMEOUT"
                return stop(TaskStatus.TOOL_ERROR, "模型服务失败，未能完成下一步决策。", "model", code)
            except Exception:
                return stop(TaskStatus.TOOL_ERROR, "模型适配器异常。", "model", "MODEL_ADAPTER_ERROR")
            if monotonic() - start >= self.limits.total_timeout:
                return stop(TaskStatus.INCOMPLETE, "总执行时间已耗尽。", "executor", "BUDGET_EXHAUSTED")
            messages.append({"role": "assistant", "content": json.dumps(asdict(action), ensure_ascii=False)})
            self.trace.add(event="action", model_turn=turns, **asdict(action),
                           provider=getattr(self.model, "last_metadata", {}))
            if action.action in {"finish", "ask_user"}:
                try:
                    result = check_result(action, evidence)
                except ActionError as exc:
                    self.trace.add(event="invalid_result", model_turn=turns, message=str(exc))
                    messages.append({"role": "user", "content": json.dumps({"validation_error": str(exc)}, ensure_ascii=False)})
                    continue
                return complete(result, "business_tool" if result["status"] == "tool_error" else None, "UNRESOLVED_TOOL_FAILURE")
            if action.action == "record_evidence":
                try:
                    evidence.record(action.arguments)
                    feedback = {"evidence_state": evidence.view(), "recorded": True}
                except ActionError as exc:
                    feedback = {"validation_error": str(exc)}
                self.trace.add(event="evidence_update", model_turn=turns, **feedback)
                messages.append({"role": "user", "content": json.dumps(feedback, ensure_ascii=False)})
                continue
            calls += 1
            method = getattr(self.tools, action.action)
            try:
                inspect.signature(method).bind(**action.arguments)
            except TypeError:
                observation = ToolResult(False, error=ToolError("INVALID_ARGUMENT", "工具参数名或必需参数不正确。"))
            else:
                try:
                    timeout = min(self.limits.tool_timeout, max(0, self.limits.total_timeout - (monotonic() - start)))
                    observation = bounded_call(lambda fn=method, params=action.arguments.copy(): fn(**params), timeout)
                except TimeoutError:
                    observation = ToolResult(False, error=ToolError("TEMPORARY_FAILURE", "工具执行超时。", True))
                except Exception:
                    observation = ToolResult(False, error=ToolError("TOOL_UNAVAILABLE", "工具执行异常。", False))
            if observation.ok and action.action == "read_document":
                evidence.add_read(observation.data)
            payload = observation.to_dict()
            self.trace.add(event="observation", model_turn=turns, tool_call=calls, tool=action.action,
                           summary=("工具成功" if observation.ok else observation.error.code), observation=payload)
            messages.append({"role": "user", "content": json.dumps({"tool": action.action, "observation": payload}, ensure_ascii=False)})
        return stop(TaskStatus.INCOMPLETE, "模型决策轮数已耗尽。", "executor", "BUDGET_EXHAUSTED")
