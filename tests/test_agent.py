import copy
import json
import time

import pytest

from knowledge_agent import KnowledgeTools
from knowledge_agent.agent import Agent, Limits
from knowledge_agent.mock_model import MockModel, ScriptedModel
from knowledge_agent.model import ModelError
from knowledge_agent.tools import FaultInjection
from knowledge_agent.trace import RunTrace


def action(name, args):
    return {"action": name, "arguments": args, "reason": "测试动作。"}


def finish(status="insufficient_evidence", citations=None):
    return action("finish", {"answer": "测试结果。", "status": status, "citations": citations or [],
                             "conflicts": [], "gaps": ["测试资料不足"] if status != "answered" else [], "follow_up_question": None})


def test_search_read_finish_loop_and_artifacts(corpus, tmp_path):
    citation = {"doc_id": "D01", "version_date": "2026-01-10", "quote": "报销期限为 30 个自然日，自费用发生之日起计算。", "supports": "期限"}
    model = ScriptedModel([action("search_docs", {"query": "报销"}), action("read_document", {"doc_id": "D01"}), finish("answered", [citation])])
    trace = RunTrace(tmp_path)
    output = Agent(model, KnowledgeTools(corpus), trace=trace).run("期限多久？")
    assert output["status"] == "answered" and output["tool_calls"] == 2 and output["model_turns"] == 3
    assert output["citations"][0]["start"] == 0
    assert json.loads((trace.directory / "evidence.json").read_text(encoding="utf-8"))[0]["doc_id"] == "D01"
    assert len((trace.directory / "trace.jsonl").read_text(encoding="utf-8").splitlines()) == 6


def test_observations_and_history_are_visible(corpus):
    class Observing:
        mode, name = "mock", "observing-test"
        def choose(self, messages, timeout):
            state = json.loads(messages[1]["content"])
            assert state["history"][0]["content"] == "报销期限多久？"
            observed = [json.loads(m["content"]) for m in messages if m["role"] == "user"]
            if any("observation" in x for x in observed):
                last = next(x["observation"] for x in reversed(observed) if "observation" in x)
                assert last["ok"] and last["data"]["hits"] == []
                return finish()
            return action("search_docs", {"query": "xyznotfound"})
    result = Agent(Observing(), KnowledgeTools(corpus)).run("那材料呢？", [{"role": "user", "content": "报销期限多久？"}])
    assert result["status"] == "insufficient_evidence"


@pytest.mark.parametrize("limits,turns,calls", [(Limits(max_model_turns=2), 2, 2), (Limits(max_tool_calls=1), 1, 1)])
def test_budget_does_not_make_extra_calls(corpus, limits, turns, calls):
    model = ScriptedModel([action("search_docs", {"query": "报销"})] * 10)
    result = Agent(model, KnowledgeTools(corpus), limits).run("期限")
    assert result["status"] == "incomplete" and result["model_turns"] == turns and result["tool_calls"] == calls


def test_invalid_actions_count_and_can_be_repaired(corpus):
    result = Agent(ScriptedModel([{"action": "shell"}, finish()]), KnowledgeTools(corpus)).run("问题")
    assert result["model_turns"] == 2 and result["tool_calls"] == 0


def test_invalid_tool_arguments_return_observation(corpus):
    trace = RunTrace()
    result = Agent(ScriptedModel([action("read_document", {"path": "data/documents.json"}), finish()]), KnowledgeTools(corpus), trace=trace).run("问题")
    assert result["tool_calls"] == 1
    assert next(e for e in trace.events if e["event"] == "observation")["observation"]["error"]["code"] == "INVALID_ARGUMENT"


def test_failure_observed_then_model_retries(corpus):
    class RetryModel:
        mode, name = "mock", "retry-test"
        def choose(self, messages, timeout):
            observations = [json.loads(m["content"]) for m in messages if m["role"] == "user"]
            observations = [o["observation"] for o in observations if "observation" in o]
            if not observations or not observations[-1]["ok"]:
                return action("read_document", {"doc_id": "D01"})
            return finish()
    fault = FaultInjection("read_document", {}, "first_matching_call", "TEMPORARY_FAILURE", True)
    result = Agent(RetryModel(), KnowledgeTools(corpus, fault=fault)).run("问题")
    assert result["tool_calls"] == 2 and result["model_turns"] == 3


def test_unread_or_false_quote_rejected(corpus):
    citation = {"doc_id": "D01", "version_date": "2026-01-10", "quote": "期限是999天", "supports": "期限"}
    trace = RunTrace()
    result = Agent(ScriptedModel([finish("answered", [citation]), finish()]), KnowledgeTools(corpus), trace=trace).run("问题")
    assert result["status"] == "insufficient_evidence"
    assert any(e["event"] == "invalid_result" for e in trace.events)


def test_ask_user(corpus):
    a = finish("needs_clarification")
    a["action"] = "ask_user"
    a["arguments"]["follow_up_question"] = "适用哪个制度？"
    result = Agent(ScriptedModel([a]), KnowledgeTools(corpus)).run("问题")
    assert result["status"] == "needs_clarification"


def test_model_error_has_source_and_no_fallback(corpus):
    class Broken:
        mode, name = "real", "broken-test"
        def choose(self, messages, timeout):
            raise ModelError("MODEL_HTTP_401")
    result = Agent(Broken(), KnowledgeTools(corpus)).run("问题")
    assert result["mode"] == "real" and result["model_turns"] == 1
    assert result["error"] == {"source": "model", "code": "MODEL_HTTP_401"}


def test_model_timeout_returns_promptly(corpus):
    class Slow:
        mode, name = "mock", "slow-test"
        def choose(self, messages, timeout):
            time.sleep(0.2)
            return finish()
    started = time.monotonic()
    result = Agent(Slow(), KnowledgeTools(corpus), Limits(model_timeout=0.02)).run("问题")
    assert result["error"]["code"] == "MODEL_TIMEOUT"
    assert time.monotonic() - started < 0.15


def test_tool_timeout_is_an_observation(corpus):
    tools = KnowledgeTools(corpus)
    def slow(query):
        time.sleep(0.2)
    tools.search_docs = slow
    trace = RunTrace()
    result = Agent(ScriptedModel([action("search_docs", {"query": "问题"}), finish()]), tools, Limits(tool_timeout=0.02), trace).run("问题")
    assert result["tool_calls"] == 1
    assert any(e.get("summary") == "TEMPORARY_FAILURE" for e in trace.events)


def test_mock_is_labelled_and_does_not_claim_answer(corpus):
    result = Agent(MockModel(), KnowledgeTools(corpus)).run("报销期限")
    assert result["mode"] == "mock" and result["status"] == "incomplete" and result["tool_calls"] == 2


def test_trace_redacts_configured_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "secret-example-do-not-store")
    trace = RunTrace(tmp_path)
    trace.add(event="test", value="secret-example-do-not-store")
    assert "secret-example" not in (trace.directory / "trace.jsonl").read_text()


@pytest.mark.parametrize("kwargs", [{"max_model_turns": 0}, {"max_tool_calls": True}, {"model_timeout": float("nan")}, {"total_timeout": -1}])
def test_invalid_limits(kwargs):
    with pytest.raises(ValueError):
        Limits(**kwargs)


def test_total_deadline_reports_incomplete(corpus):
    class Slow:
        mode, name = "mock", "slow"
        def choose(self, messages, timeout):
            time.sleep(0.2)
            return finish()
    result = Agent(Slow(), KnowledgeTools(corpus), Limits(total_timeout=0.02)).run("问题")
    assert result["status"] == "incomplete" and result["error"]["source"] == "executor"


def test_repeated_invalid_actions_stop_at_budget(corpus):
    result = Agent(ScriptedModel([{}] * 10), KnowledgeTools(corpus), Limits(max_model_turns=2)).run("问题")
    assert result["model_turns"] == 2 and result["tool_calls"] == 0 and result["status"] == "incomplete"
