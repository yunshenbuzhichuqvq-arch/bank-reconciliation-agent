import json

from bank_reconciliation_agent.core.llm.provider import FakeLLMProvider, LLMResult, LLMUnavailable
from bank_reconciliation_agent.core.prompts import load_prompt
from bank_reconciliation_agent.rag.query_rewrite import QueryRewriter


def test_query_rewriter_returns_deterministic_string_with_fake_provider() -> None:
    rewriter = QueryRewriter(provider=FakeLLMProvider())

    result = rewriter.rewrite("金额差异", scenario_type="BANK_ENTERPRISE")

    assert result == "金额差异 对账 规则"


def test_query_rewriter_falls_back_to_original_query_when_provider_unavailable() -> None:
    rewriter = QueryRewriter(provider=UnavailableProvider())

    result = rewriter.rewrite("单边缺失", scenario_type="BANK_ENTERPRISE")

    assert result == "单边缺失"


def test_load_prompt_returns_query_rewrite_v1() -> None:
    text, version = load_prompt("query_rewrite")

    assert version == "v1"
    assert "rewritten_query" in text


def test_fake_provider_supports_query_rewrite_payload() -> None:
    provider = FakeLLMProvider()

    result = provider.complete(
        [
            {"role": "system", "content": "# Query Rewrite Prompt v1"},
            {"role": "user", "content": '{"task": "query_rewrite", "query": "金额差异"}'},
        ]
    )

    payload = json.loads(result.text)
    assert payload["rewritten_query"] == "金额差异 对账 规则"


class UnavailableProvider:
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: str = "json_object",
    ) -> LLMResult:
        del messages, temperature, response_format
        raise LLMUnavailable("provider unavailable")
