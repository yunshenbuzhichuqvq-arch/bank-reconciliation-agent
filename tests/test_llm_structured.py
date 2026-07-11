from typing import Literal

import pytest

from bank_reconciliation_agent.core.llm.provider import LLMAttemptRecord, LLMCallError, LLMResult
from bank_reconciliation_agent.core.llm.structured import (
    StructuredCompletion,
    StructuredLLMError,
    complete_structured,
)
from pydantic import BaseModel, Field


class SampleModel(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)


class SequenceProvider:
    model = "seq-model"

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0
        self.conversations: list[list[dict[str, str]]] = []

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        response_format: Literal["text", "json_object"] = "json_object",
        response_validator=None,
    ) -> LLMResult:
        del temperature, response_format, response_validator
        self.calls += 1
        self.conversations.append(list(messages))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _result(text: str, *, prompt: int = 10, completion: int = 5, cached: bool = False,
            attempts: int = 0) -> LLMResult:
    records = [
        LLMAttemptRecord(physical_attempt=i + 1, outcome="success", duration_ms=1)
        for i in range(attempts)
    ]
    return LLMResult(
        text=text,
        prompt_tokens=prompt,
        completion_tokens=completion,
        model="seq-model",
        cached=cached,
        attempts=records,
    )


def _messages() -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": '{"task": "sample"}'},
    ]


_VALID = '{"name": "ok", "confidence": 0.9}'


def _run(provider: SequenceProvider) -> StructuredCompletion[SampleModel]:
    return complete_structured(
        provider,
        _messages(),
        schema=SampleModel,
        agent_name="SampleAgent",
        step="sample",
        prompt_version="v1",
    )


def test_structured_completion_returns_valid_initial_result() -> None:
    provider = SequenceProvider([_result(_VALID)])

    completion = _run(provider)

    assert isinstance(completion.value, SampleModel)
    assert completion.value.name == "ok"
    assert provider.calls == 1
    assert completion.summary.structured_repair_attempted is False


def test_invalid_json_gets_one_targeted_correction() -> None:
    provider = SequenceProvider([_result("{not-json"), _result(_VALID)])

    completion = _run(provider)

    assert provider.calls == 2
    assert completion.summary.structured_repair_attempted is True
    assert completion.summary.structured_repair_succeeded is True
    correction = provider.conversations[-1]
    assert correction[-2]["role"] == "assistant"
    assert correction[-1]["role"] == "user"
    assert "invalid_json" in correction[-1]["content"]
    assert "traceback" not in correction[-1]["content"].lower()


def test_schema_invalid_gets_one_targeted_correction() -> None:
    invalid = '{"name": "ok", "confidence": 1.9}'
    provider = SequenceProvider([_result(invalid), _result(_VALID)])

    completion = _run(provider)

    assert provider.calls == 2
    assert completion.summary.final_failure_type is None
    correction = provider.conversations[-1]
    assert correction[-1]["role"] == "user"
    assert "schema_invalid" in correction[-1]["content"]
    assert "confidence" in correction[-1]["content"]


def test_second_invalid_response_raises_with_summary() -> None:
    provider = SequenceProvider([_result("{not-json"), _result("{still-bad")])

    with pytest.raises(StructuredLLMError) as excinfo:
        _run(provider)

    assert provider.calls == 2
    summary = excinfo.value.summary
    assert summary.structured_repair_attempted is True
    assert summary.structured_repair_succeeded is False
    assert summary.final_failure_type == "invalid_json"
    assert summary.fallback_reason == "structured_output_invalid"


def test_initial_and_correction_tokens_are_accumulated() -> None:
    provider = SequenceProvider([
        _result("{not-json", prompt=10, completion=5),
        _result(_VALID, prompt=8, completion=4),
    ])

    completion = _run(provider)

    assert completion.summary.prompt_tokens == 18
    assert completion.summary.completion_tokens == 9
    total = completion.summary.prompt_tokens + completion.summary.completion_tokens
    assert total == 27


def test_correction_transport_attempts_contribute_to_six_call_cap() -> None:
    provider = SequenceProvider([
        _result("{not-json", attempts=3),
        _result(_VALID, attempts=3),
    ])

    completion = _run(provider)

    assert completion.summary.transport_attempts == 6


def test_cache_hit_contributes_zero_new_tokens() -> None:
    provider = SequenceProvider([_result(_VALID, prompt=10, completion=5, cached=True)])

    completion = _run(provider)

    assert completion.summary.prompt_tokens == 0
    assert completion.summary.completion_tokens == 0
    assert completion.summary.cached_calls == 1


def test_transport_failure_raises_structured_error_with_summary() -> None:
    provider = SequenceProvider([
        LLMCallError(
            failure_type="provider_5xx",
            retryable=False,
            sanitized_reason="upstream down",
        )
    ])

    with pytest.raises(StructuredLLMError) as excinfo:
        _run(provider)

    assert provider.calls == 1
    assert excinfo.value.summary.final_failure_type == "provider_5xx"
