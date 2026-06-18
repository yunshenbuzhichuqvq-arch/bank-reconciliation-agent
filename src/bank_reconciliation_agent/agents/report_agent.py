import json

from pydantic import ValidationError

from bank_reconciliation_agent.core.llm.provider import LLMProvider, LLMUnavailable, get_llm_provider
from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.core.prompts import load_prompt
from bank_reconciliation_agent.schemas.report import (
    LLMReportNarrative,
    ReportNarrative,
    TaskReportMetrics,
)


class ReportAgent:
    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        prompt_text: str | None = None,
        prompt_version: str | None = None,
    ) -> None:
        loaded_prompt_text, loaded_prompt_version = load_prompt("report")
        self.provider = provider or get_llm_provider()
        self.prompt_text = prompt_text or loaded_prompt_text
        self.prompt_version = prompt_version or loaded_prompt_version

    def narrate(self, metrics: TaskReportMetrics) -> ReportNarrative:
        messages = [
            {"role": "system", "content": self.prompt_text},
            {
                "role": "user",
                "content": json.dumps(
                    {"task": "report", "metrics": metrics.model_dump(mode="json")},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        ]
        log.info(
            "agent_llm_call",
            agent_name="ReportAgent",
            step="narrate",
            prompt_version=self.prompt_version,
        )
        try:
            result = self.provider.complete(
                messages,
                temperature=0.0,
                response_format="json_object",
            )
            narrative = LLMReportNarrative.model_validate(json.loads(result.text))
            return ReportNarrative(**narrative.model_dump(), llm_used=True)
        except LLMUnavailable:
            log.warning(
                "agent_llm_unavailable",
                agent_name="ReportAgent",
                step="narrate",
                prompt_version=self.prompt_version,
            )
        except (json.JSONDecodeError, ValidationError) as exc:
            log.warning(
                "agent_llm_invalid_output",
                agent_name="ReportAgent",
                step="narrate",
                prompt_version=self.prompt_version,
                error_type=type(exc).__name__,
            )
        return self._fallback_narrative()

    def _fallback_narrative(self) -> ReportNarrative:
        return ReportNarrative(
            risk_summary="系统已保留任务指标，请结合异常明细识别重点风险。",
            review_advice="建议人工复核待处理事项及相关业务依据。",
            followup="建议完成复核后更新处理状态并保留审计记录。",
            llm_used=False,
        )


report_agent = ReportAgent()
