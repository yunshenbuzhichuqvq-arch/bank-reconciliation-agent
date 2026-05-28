from pydantic import BaseModel

from bank_reconciliation_agent.schemas.rag import RagSearchItem


class AuditDecision(BaseModel):
    flow_id: str
    decision: str
    risk_level: str
    reason: str
    evidence: list[RagSearchItem]
    confidence: float


class AuditAgent:
    def decide(
        self,
        flow_id: str,
        error_type: str,
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
                reason=f"未检索到 {error_type} 的规则依据，不能生成自动审计结论。",
                evidence=[],
                confidence=0.0,
            )

        confidence = self._confidence_from_evidence(evidence)
        if error_type == "AMOUNT_MISMATCH":
            reason = (
                f"银行端与清算端金额不一致：银行端金额 {bank_amount}，清算端金额 {clear_amount}，"
                f"差异金额 {amount_diff}，已检索到金额差异处理依据，建议人工复核确认。"
            )
            risk_level = "MEDIUM"
        elif error_type == "SINGLE_SIDE_MISSING":
            reason = "该流水仅单侧存在，已检索到单边缺失和查询查复依据，建议人工复核或追溯。"
            risk_level = "MEDIUM"
        else:
            reason = f"已检索到 {error_type} 的规则依据，建议人工复核。"
            risk_level = "MEDIUM"

        return AuditDecision(
            flow_id=flow_id,
            decision="PENDING_HUMAN",
            risk_level=risk_level,
            reason=reason,
            evidence=evidence,
            confidence=confidence,
        )

    def _confidence_from_evidence(self, evidence: list[RagSearchItem]) -> float:
        best_score = max(item.score for item in evidence)
        return round(min(0.85, 0.60 + best_score / 100), 2)


audit_agent = AuditAgent()
