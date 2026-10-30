"""One OpenAI-compatible JSON action per request, with SDK retries disabled."""

import json
import os
from dataclasses import dataclass
from urllib.parse import urlsplit


class ModelError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ActionError(ValueError):
    pass


@dataclass(frozen=True)
class Action:
    action: str
    arguments: dict
    reason: str

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) != {"action", "arguments", "reason"}:
            raise ActionError("动作必须且仅包含 action、arguments、reason。")
        if value["action"] not in ("search_docs", "read_document", "record_evidence", "ask_user", "finish"):
            raise ActionError("不支持的动作。")
        if not isinstance(value["arguments"], dict):
            raise ActionError("arguments 必须是对象。")
        if not isinstance(value["reason"], str) or not 1 <= len(value["reason"]) <= 150:
            raise ActionError("reason 必须为 1 至 150 字的简短依据。")
        return cls(**value)


class OpenAIModel:
    mode = "real"

    def __init__(self, model=None, base_url=None, api_key=None, client=None):
        self.name = model or os.getenv("MODEL_NAME") or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
        endpoint = base_url or os.getenv("MODEL_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
            raise ModelError("INVALID_ENDPOINT")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ModelError("HTTPS_REQUIRED")
        self.endpoint = endpoint
        self.is_deepseek = parsed.hostname == "api.deepseek.com"
        self.last_metadata = {}
        if client is None:
            key = api_key or os.getenv("MODEL_API_KEY") or os.getenv("DEEPSEEK_API_KEY" if self.is_deepseek else "OPENAI_API_KEY")
            if not key:
                raise ModelError("MISSING_API_KEY")
            try:
                from openai import OpenAI
            except ImportError:
                raise ModelError("MISSING_OPENAI_DEPENDENCY") from None
            client = OpenAI(api_key=key, base_url=endpoint, max_retries=0)
        self.client = client

    def choose(self, messages, timeout):
        self.last_metadata = {}
        parameters = (
            {"max_tokens": 8192, "reasoning_effort": "high",
             "extra_body": {"thinking": {"type": "enabled"}}}
            if self.is_deepseek else {"max_completion_tokens": 2000}
        )
        try:
            response = self.client.chat.completions.create(
                model=self.name, messages=messages, response_format={"type": "json_object"},
                timeout=timeout, **parameters,
            )
        except Exception as exc:
            # Provider text may contain credentials or request details. Never persist it.
            status = getattr(exc, "status_code", None)
            code = "MODEL_TIMEOUT" if "Timeout" in type(exc).__name__ else "MODEL_REQUEST_FAILED"
            if type(status) is int:
                code = f"MODEL_HTTP_{status}"
            raise ModelError(code) from None
        try:
            self.last_metadata = {"response_id": response.id, "model": response.model,
                                  "usage": response.usage.model_dump() if response.usage else None}
            if response.choices[0].finish_reason != "stop":
                raise ActionError("模型输出未完整结束，请缩短并重发合法动作。")
            return json.loads(response.choices[0].message.content)
        except (AttributeError, IndexError, TypeError, json.JSONDecodeError):
            raise ActionError("模型响应不是有效 JSON 动作，请修正。") from None
