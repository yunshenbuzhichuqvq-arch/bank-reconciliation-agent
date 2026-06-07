from typing import NamedTuple

from pydantic import BaseModel

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
    decision: str
    risk_level: str
    reason: str
    ai_suggestion: str
    evidence: list[RagSearchItem]
    confidence: float


class AuditAgent:
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
        )

    def _confidence_from_evidence(self, evidence: list[RagSearchItem]) -> float:
        best_score = max(item.score for item in evidence)
        if best_score <= 1:
            return round(min(0.85, 0.60 + best_score * 0.25), 2)
        return round(min(0.85, 0.60 + best_score / 100), 2)


audit_agent = AuditAgent()
