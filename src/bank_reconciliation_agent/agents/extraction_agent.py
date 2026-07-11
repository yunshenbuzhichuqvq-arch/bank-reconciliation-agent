import json
from typing import Literal

from pydantic import BaseModel, Field

from bank_reconciliation_agent.core.llm.provider import LLMProvider, get_llm_provider
from bank_reconciliation_agent.core.llm.structured import (
    StructuredLLMError,
    complete_structured,
)
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
    ) -> None:
        loaded_prompt_text, loaded_prompt_version = load_prompt("extraction")
        self.provider = provider or get_llm_provider()
        self.prompt_text = prompt_text or loaded_prompt_text
        self.prompt_version = prompt_version or loaded_prompt_version
        self.last_llm_result = None
        self.last_llm_summary = None

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

        try:
            completion = complete_structured(
                self.provider,
                messages,
                schema=ExtractionResult,
                agent_name="ExtractionAgent",
                step="extract",
                prompt_version=self.prompt_version,
            )
        except StructuredLLMError as exc:
            self.last_llm_result = exc.last_result
            self.last_llm_summary = exc.summary
            raise ExtractionAgentError("invalid LLM JSON for ExtractionAgent") from exc

        self.last_llm_result = completion.last_result
        self.last_llm_summary = completion.summary
        return completion.value


extraction_agent = ExtractionAgent()
