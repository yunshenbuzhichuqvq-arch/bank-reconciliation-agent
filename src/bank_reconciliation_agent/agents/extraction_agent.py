import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from bank_reconciliation_agent.core.llm.provider import LLMProvider, get_llm_provider
from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.core.prompts import load_prompt


class ExtractionResult(BaseModel):
    standard_type: Literal["REVERSAL", "REFUND", "CANCEL", "UNKNOWN"]
    original_flow_id: str | None
    cleaned_remark: str
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractionAgentError(RuntimeError):
    pass


class ExtractionAgent:
    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        prompt_text: str | None = None,
        prompt_version: str | None = None,
        max_retries: int = 1,
    ) -> None:
        loaded_prompt_text, loaded_prompt_version = load_prompt("extraction")
        self.provider = provider or get_llm_provider()
        self.prompt_text = prompt_text or loaded_prompt_text
        self.prompt_version = prompt_version or loaded_prompt_version
        self.max_retries = max_retries
        self.last_llm_result = None

    def extract(
        self,
        *,
        flow_id: str,
        summary: str,
        remark: str | None,
    ) -> ExtractionResult:
        messages = [
            {"role": "system", "content": self.prompt_text},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "extraction",
                        "flow_id": flow_id,
                        "summary": summary,
                        "remark": remark,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        ]

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            log.info(
                "agent_llm_call",
                agent_name="ExtractionAgent",
                step="extract",
                prompt_version=self.prompt_version,
                attempt=attempt + 1,
            )
            result = self.provider.complete(messages, temperature=0.0, response_format="json_object")
            self.last_llm_result = result
            try:
                return ExtractionResult.model_validate(json.loads(result.text))
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                log.warning(
                    "agent_llm_invalid_output",
                    agent_name="ExtractionAgent",
                    step="extract",
                    prompt_version=self.prompt_version,
                    attempt=attempt + 1,
                )

        raise ExtractionAgentError("invalid LLM JSON for ExtractionAgent") from last_error


extraction_agent = ExtractionAgent()
