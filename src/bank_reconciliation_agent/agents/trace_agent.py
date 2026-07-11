import json

from pydantic import BaseModel, Field

from bank_reconciliation_agent.core.llm.provider import LLMProvider, get_llm_provider
from bank_reconciliation_agent.core.llm.structured import (
    StructuredLLMError,
    complete_structured,
)
from bank_reconciliation_agent.core.prompts import load_prompt


class TraceResult(BaseModel):
    trace_found: bool
    related_flow_ids: list[str]
    trace_summary: str
    confidence: float = Field(ge=0.0, le=1.0)


class TraceAgentError(RuntimeError):
    pass


class TraceAgent:
    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        prompt_text: str | None = None,
        prompt_version: str | None = None,
    ) -> None:
        loaded_prompt_text, loaded_prompt_version = load_prompt("trace")
        self.provider = provider or get_llm_provider()
        self.prompt_text = prompt_text or loaded_prompt_text
        self.prompt_version = prompt_version or loaded_prompt_version
        self.last_llm_result = None
        self.last_llm_summary = None

    def trace(
        self,
        *,
        flow_id: str,
        summary: str,
        transaction_date: str | None,
        amount: str | None,
        remark: str | None,
        cutoff_t1_context: dict[str, str] | None = None,
    ) -> TraceResult:
        payload: dict[str, object] = {
            "task": "trace",
            "flow_id": flow_id,
            "summary": summary,
            "transaction_date": transaction_date,
            "amount": amount,
            "remark": remark,
        }
        if cutoff_t1_context is not None:
            payload["cutoff_t1_context"] = cutoff_t1_context

        messages = [
            {"role": "system", "content": self.prompt_text},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            },
        ]

        try:
            completion = complete_structured(
                self.provider,
                messages,
                schema=TraceResult,
                agent_name="TraceAgent",
                step="trace",
                prompt_version=self.prompt_version,
            )
        except StructuredLLMError as exc:
            self.last_llm_result = exc.last_result
            self.last_llm_summary = exc.summary
            raise TraceAgentError("invalid LLM JSON for TraceAgent") from exc

        self.last_llm_result = completion.last_result
        self.last_llm_summary = completion.summary
        return completion.value


trace_agent = TraceAgent()
