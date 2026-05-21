from fastapi import APIRouter

from bank_reconciliation_agent.rag.retriever import rule_retriever
from bank_reconciliation_agent.schemas.common import ApiResponse
from bank_reconciliation_agent.schemas.rag import RagSearchRequest, RagSearchResponse


router = APIRouter()


@router.post("/search", response_model=ApiResponse[RagSearchResponse])
async def search_rules(request: RagSearchRequest) -> ApiResponse[RagSearchResponse]:
    return ApiResponse(data=rule_retriever.search(request))

