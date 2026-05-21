from pydantic import BaseModel

from bank_reconciliation_agent.schemas.rag import RagSearchItem


class AuditDecision(BaseModel):
    suggestion: str
    reason: str
    evidence: list[RagSearchItem]
    confidence: float


class AuditAgent:
    def decide(self, error_type: str, evidence: list[RagSearchItem]) -> AuditDecision:
        if not evidence:
            return AuditDecision(
                suggestion="PENDING_HUMAN",
                reason=f"No RAG evidence found for {error_type}.",
                evidence=[],
                confidence=0.0,
            )

        return AuditDecision(
            suggestion="PENDING_HUMAN",
            reason=f"Evidence found for {error_type}; deterministic checks are still required.",
            evidence=evidence,
            confidence=max(item.score for item in evidence),
        )


audit_agent = AuditAgent()

