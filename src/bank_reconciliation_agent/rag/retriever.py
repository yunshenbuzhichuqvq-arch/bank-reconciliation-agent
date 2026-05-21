from bank_reconciliation_agent.schemas.rag import RagSearchItem, RagSearchRequest, RagSearchResponse


class RuleRetriever:
    def search(self, request: RagSearchRequest) -> RagSearchResponse:
        return RagSearchResponse(
            items=[
                RagSearchItem(
                    source="rules/reconciliation.md#MVP-0审计边界",
                    score=1.0,
                    content="AuditAgent must include evidence and defer when evidence is missing.",
                )
            ][: request.top_k]
        )


rule_retriever = RuleRetriever()

