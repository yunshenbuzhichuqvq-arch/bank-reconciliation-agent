from fastapi import APIRouter

from bank_reconciliation_agent.rag.retriever import rule_retriever
from bank_reconciliation_agent.schemas.common import ApiResponse
from bank_reconciliation_agent.schemas.rag import RagSearchRequest, RagSearchResponse


router = APIRouter()


@router.post("/search", response_model=ApiResponse[RagSearchResponse])
async def search_rules(request: RagSearchRequest) -> ApiResponse[RagSearchResponse]:
    """根据查询文本检索规则依据，供审计 Agent 判断时引用。"""
    return ApiResponse(data=rule_retriever.search(request))
