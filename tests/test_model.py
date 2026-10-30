from types import SimpleNamespace

import pytest

from knowledge_agent.model import ActionError, ModelError, OpenAIModel


def test_request_contract_and_metadata():
    recorded = {}
    def create(**kwargs):
        recorded.update(kwargs)
        return SimpleNamespace(id="test-id", model="test-model", usage=None,
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"action":"search_docs","arguments":{"query":"abc"},"reason":"test"}'))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model = OpenAIModel(model="test-model", client=client)
    assert model.choose([], 3)["action"] == "search_docs"
    assert recorded["response_format"] == {"type": "json_object"} and recorded["timeout"] == 3
    assert model.last_metadata["response_id"] == "test-id"


def test_provider_error_text_not_exposed():
    def create(**kwargs):
        raise RuntimeError("sensitive response containing secret")
    model = OpenAIModel(client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    with pytest.raises(ModelError, match="MODEL_REQUEST_FAILED") as exc:
        model.choose([], 1)
    assert "sensitive" not in str(exc.value)


@pytest.mark.parametrize("url", ["http://remote.example/v1", "https://user:password@host/v1", "https://host/v1?key=secret"])
def test_unsafe_endpoint_rejected(url):
    with pytest.raises(ModelError):
        OpenAIModel(base_url=url, client=object())


def test_deepseek_request_matches_official_parameters():
    recorded = {}
    def create(**kwargs):
        recorded.update(kwargs)
        return SimpleNamespace(id="test", model="deepseek-flash", usage=None,
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
                content='{"action":"search_docs","arguments":{"query":"q"},"reason":"test"}',
                reasoning_content="private reasoning not persisted"))])
    model = OpenAIModel(model="deepseek-flash", base_url="https://api.deepseek.com",
                        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    result = model.choose([], 60)
    assert recorded["max_tokens"] == 8192 and "max_completion_tokens" not in recorded
    assert recorded["reasoning_effort"] == "high"
    assert recorded["extra_body"] == {"thinking": {"type": "enabled"}}
    assert "reasoning_content" not in result and "reasoning_content" not in model.last_metadata


def test_deepseek_does_not_use_openai_key(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "wrong-provider-test-key")
    with pytest.raises(ModelError, match="MISSING_API_KEY"):
        OpenAIModel(model="deepseek-flash", base_url="https://api.deepseek.com")
