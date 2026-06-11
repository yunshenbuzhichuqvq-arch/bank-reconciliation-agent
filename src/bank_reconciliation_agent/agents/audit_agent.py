import json
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field, ValidationError, model_validator

from bank_reconciliation_agent.core.llm.provider import LLMProvider, LLMUnavailable, get_llm_provider
from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.core.prompts import load_prompt
from bank_reconciliation_agent.schemas.rag import RagSearchItem


class BranchProfile(NamedTuple):
    risk_level: str
    ai_suggestion: str
    reason_template: str


BRANCH_PROFILE: dict[str, BranchProfile] = {
    "BE-R002": BranchProfile(
        "MEDIUM",
        "PENDING_HUMAN",
        "银行端与企业端金额不一致：差异 {amount_diff}，已检索到金额差异处理依据，建议人工复核。",
    ),
    "BE-R004": BranchProfile(
        "LOW",
        "APPROVED_MATCH",
        "金额与入账一致，但摘要/客户名不一致（疑似冲正/同一笔），已检索到核对依据，建议确认平账。",
    ),
    "BE-R005": BranchProfile(
        "MEDIUM",
        "PENDING_HUMAN",
        "企业已记账、银行未到账（单边），已检索到查询查复依据，建议追溯后续到账。",
    ),
    "BE-R006": BranchProfile(
        "MEDIUM",
        "PENDING_HUMAN",
        "银行已到账、企业未入账（单边），已检索到补登依据，建议核实补登。",
    ),
    "BE-R008": BranchProfile(
        "HIGH",
        "FORCE_HOLD",
        "同主体同金额疑似一端重复记账，已检索到排查依据，建议挂账核实。",
    ),
}


class AuditDecision(BaseModel):
    flow_id: str
    decision: Literal["AUTO_FIXED", "PENDING_HUMAN", "UNRESOLVED"]
    risk_level: str
    reason: str
    ai_suggestion: str
    evidence: list[RagSearchItem]
    confidence: float = Field(ge=0.0, le=1.0)
    fallback_applied: bool = False
    fallback_level: int = 0
    next_action: str = "PENDING_HUMAN"

    @model_validator(mode="after")
    def _c2_evidence_required_unless_human(self) -> "AuditDecision":
        if self.decision != "PENDING_HUMAN" and not self.evidence:
            raise ValueError("C2: 非转人工决策 evidence 不能为空")
        return self


class LLMAuditDecision(BaseModel):
    decision: str
    risk_level: str
    reason: str
    ai_suggestion: str
    evidence: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


class AuditAgent:
    def __init__(
        self,
        *,
        provider: LLMProvider | None = None,
        prompt_text: str | None = None,
        prompt_version: str | None = None,
    ) -> None:
        loaded_prompt_text, loaded_prompt_version = load_prompt("audit")
        self.provider = provider or get_llm_provider()
        self.prompt_text = prompt_text or loaded_prompt_text
        self.prompt_version = prompt_version or loaded_prompt_version
        self.last_llm_result = None

    def decide(
        self,
        flow_id: str,
        error_type: str,
        exception_branch: str | None,
        bank_amount: str | None,
        clear_amount: str | None,
        amount_diff: str | None,
        evidence: list[RagSearchItem],
    ) -> AuditDecision:
        """根据异常类型和 RAG 证据给出审计建议；无证据时必须转人工。"""
        if not evidence:
            return AuditDecision(
                flow_id=flow_id,
                decision="PENDING_HUMAN",
                risk_level="HIGH",
                reason=f"未检索到{error_type}规则依据，不能自动判定，转人工。",
                ai_suggestion="PENDING_HUMAN",
                evidence=[],
                confidence=0.0,
            )

        confidence = self._confidence_from_evidence(evidence)
        profile = BRANCH_PROFILE.get(exception_branch or "")
        if profile:
            risk_level = profile.risk_level
            reason = profile.reason_template.format(
                bank_amount=bank_amount,
                clear_amount=clear_amount,
                amount_diff=amount_diff,
            )
            ai_suggestion = profile.ai_suggestion
        else:
            reason = f"已检索到 {error_type} 的规则依据，建议人工复核。"
            risk_level = "MEDIUM"
            ai_suggestion = "PENDING_HUMAN"

        return AuditDecision(
            flow_id=flow_id,
            decision="PENDING_HUMAN",
            risk_level=risk_level,
            reason=reason,
            ai_suggestion=ai_suggestion,
            evidence=evidence,
            confidence=confidence,
            next_action=ai_suggestion,
        )

    def decide_with_llm(
        self,
        flow_id: str,
        error_type: str,
        exception_branch: str | None,
        bank_amount: str | None,
        clear_amount: str | None,
        amount_diff: str | None,
        evidence: list[RagSearchItem],
        few_shot_cases: list[dict[str, object]] | None = None,
        trace_context: dict[str, object] | None = None,
        memory_context: str | None = None,
    ) -> AuditDecision:
        """LLM audit path; missing evidence still short-circuits to manual review."""
        if not evidence:
            return self.decide(
                flow_id=flow_id,
                error_type=error_type,
                exception_branch=exception_branch,
                bank_amount=bank_amount,
                clear_amount=clear_amount,
                amount_diff=amount_diff,
                evidence=[],
            )

        user_payload: dict[str, object] = {
            "task": "audit",
            "flow_id": flow_id,
            "error_type": error_type,
            "exception_branch": exception_branch,
            "bank_amount": bank_amount,
            "clear_amount": clear_amount,
            "amount_diff": amount_diff,
            "evidence": [item.model_dump(mode="json") for item in evidence],
        }
        if few_shot_cases is not None:
            user_payload["few_shot_cases"] = few_shot_cases
        if trace_context is not None:
            user_payload["trace_context"] = trace_context

        messages = [{"role": "system", "content": self.prompt_text}]
        if memory_context:
            messages.append({"role": "system", "content": memory_context})
        messages.append(
            {
                "role": "user",
                "content": json.dumps(
                    user_payload,
                    default=str,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
        )

        log.info(
            "agent_llm_call",
            agent_name="AuditAgent",
            step="decide_with_llm",
            prompt_version=self.prompt_version,
        )
        try:
            result = self.provider.complete(messages, temperature=0.0, response_format="json_object")
            self.last_llm_result = result
            llm_decision = LLMAuditDecision.model_validate(json.loads(result.text))
            return AuditDecision(
                flow_id=flow_id,
                decision=llm_decision.decision,
                risk_level=llm_decision.risk_level,
                reason=llm_decision.reason,
                ai_suggestion=llm_decision.ai_suggestion,
                evidence=evidence,
                confidence=llm_decision.confidence,
                fallback_applied=False,
                fallback_level=0,
                next_action=llm_decision.decision,
            )
        except LLMUnavailable:
            log.warning(
                "agent_llm_unavailable",
                agent_name="AuditAgent",
                step="decide_with_llm",
                prompt_version=self.prompt_version,
            )
            return self._fallback_decision(
                flow_id=flow_id,
                error_type=error_type,
                exception_branch=exception_branch,
                bank_amount=bank_amount,
                clear_amount=clear_amount,
                amount_diff=amount_diff,
                evidence=evidence,
            )
        except (json.JSONDecodeError, ValidationError) as exc:
            log.warning(
                "agent_llm_invalid_output",
                agent_name="AuditAgent",
                step="decide_with_llm",
                prompt_version=self.prompt_version,
                error_type=type(exc).__name__,
            )
            return self._fallback_decision(
                flow_id=flow_id,
                error_type=error_type,
                exception_branch=exception_branch,
                bank_amount=bank_amount,
                clear_amount=clear_amount,
                amount_diff=amount_diff,
                evidence=evidence,
            )

    def _fallback_decision(
        self,
        *,
        flow_id: str,
        error_type: str,
        exception_branch: str | None,
        bank_amount: str | None,
        clear_amount: str | None,
        amount_diff: str | None,
        evidence: list[RagSearchItem],
    ) -> AuditDecision:
        fallback_decision = self.decide(
            flow_id=flow_id,
            error_type=error_type,
            exception_branch=exception_branch,
            bank_amount=bank_amount,
            clear_amount=clear_amount,
            amount_diff=amount_diff,
            evidence=evidence,
        )
        fallback_decision.fallback_applied = True
        fallback_decision.fallback_level = 1
        fallback_decision.next_action = "PENDING_HUMAN"
        return fallback_decision

    def _confidence_from_evidence(self, evidence: list[RagSearchItem]) -> float:
        best_score = max(item.score for item in evidence)
        if best_score <= 1:
            return round(min(0.85, 0.60 + best_score * 0.25), 2)
        return round(min(0.85, 0.60 + best_score / 100), 2)


audit_agent = AuditAgent()
