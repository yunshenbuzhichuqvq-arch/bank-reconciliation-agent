import pytest

from bank_reconciliation_agent.agents.extraction_agent import (
    ExtractionAgent,
    ExtractionAgentError,
    ExtractionResult,
)
from bank_reconciliation_agent.core.llm.provider import FakeLLMProvider, LLMResult


def test_extraction_agent_returns_valid_result_with_fake_provider() -> None:
    agent = ExtractionAgent(provider=FakeLLMProvider())

    result = agent.extract(
        flow_id="FLOW-REVERSAL-001",
        summary="客户退款冲正，关联原流水 FLOW-ORIGINAL-001",
        remark="冲正退款",
    )

    assert isinstance(result, ExtractionResult)
    assert result.standard_type == "REVERSAL"
    assert result.original_flow_id == "FLOW-ORIGINAL-001"
    assert "冲正线索" in result.cleaned_remark
    assert result.confidence == 0.92


def test_extraction_agent_is_deterministic_with_fake_provider() -> None:
    agent = ExtractionAgent(provider=FakeLLMProvider())

    first = agent.extract(flow_id="FLOW-REVERSAL-001", summary="摘要含冲正", remark=None)
    second = agent.extract(flow_id="FLOW-REVERSAL-001", summary="摘要含冲正", remark=None)

    assert first == second


def test_extraction_agent_retries_invalid_json_then_raises_explicit_error() -> None:
    agent = ExtractionAgent(provider=InvalidJsonProvider(), max_retries=1)

    with pytest.raises(ExtractionAgentError, match="invalid LLM JSON"):
        agent.extract(flow_id="FLOW-BAD-001", summary="摘要含冲正", remark=None)

    assert InvalidJsonProvider.calls == 2


class InvalidJsonProvider:
    calls = 0

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: str = "json_object",
    ) -> LLMResult:
        del messages, temperature, response_format
        InvalidJsonProvider.calls += 1
        return LLMResult(
            text="{not-json",
            prompt_tokens=1,
            completion_tokens=1,
            model="invalid-json-provider",
        )
