import pytest

from bank_reconciliation_agent.agents.trace_agent import (
    TraceAgent,
    TraceAgentError,
    TraceResult,
)
from bank_reconciliation_agent.core.llm.provider import FakeLLMProvider, LLMResult


def test_trace_agent_returns_valid_result_with_fake_provider() -> None:
    agent = TraceAgent(provider=FakeLLMProvider())

    result = agent.trace(
        flow_id="FLOW-SINGLE-001",
        summary="企业已记账，银行 T+1 次日到账待追溯",
        transaction_date="2026-06-07",
        amount="128.00",
        remark="跨日切",
    )

    assert isinstance(result, TraceResult)
    assert result.trace_found is True
    assert result.related_flow_ids == ["FLOW-T1-001"]
    assert "T+1" in result.trace_summary
    assert result.confidence == 0.9


def test_trace_agent_is_deterministic_with_fake_provider() -> None:
    agent = TraceAgent(provider=FakeLLMProvider())

    first = agent.trace(
        flow_id="FLOW-SINGLE-001",
        summary="摘要含 T+1 跨日切",
        transaction_date="2026-06-07",
        amount="128.00",
        remark=None,
    )
    second = agent.trace(
        flow_id="FLOW-SINGLE-001",
        summary="摘要含 T+1 跨日切",
        transaction_date="2026-06-07",
        amount="128.00",
        remark=None,
    )

    assert first == second


def test_trace_agent_output_does_not_include_amount_calculation() -> None:
    result = TraceAgent(provider=FakeLLMProvider()).trace(
        flow_id="FLOW-SINGLE-001",
        summary="摘要含 T+1 跨日切",
        transaction_date="2026-06-07",
        amount="128.00",
        remark=None,
    )

    assert "amount" not in result.model_dump()


def test_trace_agent_retries_invalid_json_then_raises_explicit_error() -> None:
    provider = InvalidJsonProvider()
    agent = TraceAgent(provider=provider, max_retries=1)

    with pytest.raises(TraceAgentError, match="invalid LLM JSON"):
        agent.trace(
            flow_id="FLOW-BAD-001",
            summary="摘要含 T+1 跨日切",
            transaction_date="2026-06-07",
            amount="128.00",
            remark=None,
        )

    assert provider.calls == 2


class InvalidJsonProvider:
    def __init__(self) -> None:
        self.calls = 0

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: str = "json_object",
    ) -> LLMResult:
        del messages, temperature, response_format
        self.calls += 1
        return LLMResult(
            text="{not-json",
            prompt_tokens=1,
            completion_tokens=1,
            model="invalid-json-provider",
        )
