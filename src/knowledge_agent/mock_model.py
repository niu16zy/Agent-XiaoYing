"""Explicit offline workflow simulator; never evidence of real model reasoning."""

import copy
import json


class ScriptedModel:
    mode = "mock"
    name = "scripted-actions"
    last_metadata = {}

    def __init__(self, actions):
        self.actions = iter(actions)

    def choose(self, messages, timeout):
        return copy.deepcopy(next(self.actions))


class MockModel:
    mode = "mock"
    name = "offline-observation-demo"
    last_metadata = {}

    def choose(self, messages, timeout):
        context = json.loads(messages[1]["content"])
        observations = [json.loads(m["content"]) for m in messages[2:] if m["role"] == "user"]
        observations = [o for o in observations if "observation" in o]
        if not observations:
            return {"action": "search_docs", "arguments": {"query": context["question"], "top_k": 5}, "reason": "离线流程演示：检索当前问题。"}
        last = observations[-1]["observation"]
        if not last["ok"]:
            args = {"answer": "离线演示：工具调用失败，未能完成核实。", "status": "tool_error",
                    "citations": [], "conflicts": [], "gaps": ["缺少可成功读取的原文"], "follow_up_question": None}
        elif "hits" in last["data"] and last["data"]["hits"]:
            return {"action": "read_document", "arguments": {"doc_id": last["data"]["hits"][0]["doc_id"]}, "reason": "离线流程演示：读取首个候选，不评估业务冲突。"}
        else:
            args = {"answer": "离线流程演示已结束；Mock 不生成可作为业务结论的答案。", "status": "incomplete",
                    "citations": [], "conflicts": [], "gaps": ["需要真实模型判断证据与业务结论"], "follow_up_question": None}
        return {"action": "finish", "arguments": args, "reason": "明确离线演示边界。"}
