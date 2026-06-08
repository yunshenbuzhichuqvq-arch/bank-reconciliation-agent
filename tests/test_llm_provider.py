from decimal import Decimal
import json
import sys

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.core.llm.cost import compute_cost
from bank_reconciliation_agent.core.llm.provider import (
    DeepSeekProvider,
    FakeLLMProvider,
    LLMResult,
    LLMUnavailable,
    get_llm_provider,
)


def test_get_llm_provider_defaults_to_fake() -> None:
    settings.llm_provider = "fake"

    provider = get_llm_provider()

    assert isinstance(provider, FakeLLMProvider)


def test_fake_provider_returns_deterministic_json_for_agent_prompts() -> None:
    provider = FakeLLMProvider()
    prompts = {
        "extraction": "请执行 extraction，从摘要中提取冲正线索",
        "audit": "请执行 audit，结合 RAG evidence 输出审计判断",
        "trace": "请执行 trace，识别 T+1 跨日切追溯线索",
    }

    for agent_name, content in prompts.items():
        messages = [{"role": "user", "content": content}]
        first = provider.complete(messages)
        second = provider.complete(messages)

        assert first == second
        assert isinstance(first, LLMResult)
        payload = json.loads(first.text)
        assert payload["agent"] == agent_name
        assert first.prompt_tokens == 128
        assert first.completion_tokens == 64
        assert first.model == "fake-llm"


def test_fake_provider_prefers_explicit_audit_task_over_evidence_keywords() -> None:
    provider = FakeLLMProvider()

    result = provider.complete([
        {
            "role": "system",
            "content": "# Audit Prompt v1",
        },
        {
            "role": "user",
            "content": '{"task": "audit", "evidence": ["T+1 跨日追溯规则"]}',
        },
    ])

    payload = json.loads(result.text)
    assert payload["agent"] == "audit"
    assert payload["decision"] == "PENDING_HUMAN"


def test_fake_provider_prefers_explicit_trace_task_over_prompt_keywords() -> None:
    provider = FakeLLMProvider()

    result = provider.complete([
        {
            "role": "system",
            "content": "# Trace Prompt v1\n只给追溯线索和建议，不做最终审计结论。",
        },
        {
            "role": "user",
            "content": '{"task": "trace", "summary": "T+1 跨日切"}',
        },
    ])

    payload = json.loads(result.text)
    assert payload["agent"] == "trace"
    assert payload["trace_found"] is True


def test_compute_cost_uses_decimal_without_float() -> None:
    result = compute_cost(prompt_tokens=1_000_000, completion_tokens=1_000_000)

    assert result == Decimal("1.305")
    assert isinstance(result, Decimal)


def test_llm_provider_module_does_not_import_openai() -> None:
    assert "openai" not in sys.modules


def test_get_llm_provider_returns_deepseek_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "deepseek")
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(settings, "deepseek_model", "deepseek-v4-pro")
    monkeypatch.setattr(settings, "deepseek_base_url", "https://api.deepseek.com")

    provider = get_llm_provider()

    assert isinstance(provider, DeepSeekProvider)


def test_deepseek_provider_requires_api_key() -> None:
    provider = DeepSeekProvider(api_key=None, model="deepseek-v4-pro")

    try:
        provider.complete([{"role": "user", "content": "返回 JSON"}])
    except LLMUnavailable as exc:
        assert "DeepSeek API key is not configured" in str(exc)
    else:
        raise AssertionError("expected LLMUnavailable")


def test_deepseek_provider_wraps_client_failures() -> None:
    provider = DeepSeekProvider(
        api_key="test-key",
        model="deepseek-v4-pro",
        client=FailingClient(),
    )

    try:
        provider.complete([{"role": "user", "content": "返回 JSON"}])
    except LLMUnavailable as exc:
        assert "DeepSeek request failed" in str(exc)
    else:
        raise AssertionError("expected LLMUnavailable")


class FailingClient:
    chat = None

    def __init__(self) -> None:
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        raise RuntimeError("network down")
