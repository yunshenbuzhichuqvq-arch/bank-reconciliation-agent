import json

from pydantic import BaseModel, Field, ValidationError

from bank_reconciliation_agent.core.llm.provider import LLMProvider, get_llm_provider
from bank_reconciliation_agent.core.logging import log
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
        max_retries: int = 1,
    ) -> None:
        loaded_prompt_text, loaded_prompt_version = load_prompt("trace")
        self.provider = provider or get_llm_provider()
        self.prompt_text = prompt_text or loaded_prompt_text
        self.prompt_version = prompt_version or loaded_prompt_version
        self.max_retries = max_retries
        self.last_llm_result = None

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

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            log.info(
                "agent_llm_call",
                agent_name="TraceAgent",
                step="trace",
                prompt_version=self.prompt_version,
                attempt=attempt + 1,
            )
            result = self.provider.complete(messages, temperature=0.0, response_format="json_object")
            self.last_llm_result = result
            try:
                return TraceResult.model_validate(json.loads(result.text))
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                log.warning(
                    "agent_llm_invalid_output",
                    agent_name="TraceAgent",
                    step="trace",
                    prompt_version=self.prompt_version,
                    attempt=attempt + 1,
                )

        raise TraceAgentError("invalid LLM JSON for TraceAgent") from last_error


trace_agent = TraceAgent()
