from fastapi import APIRouter, Depends

from bank_reconciliation_agent.api.v1 import ledger, memory, rag, reconcile, review
from bank_reconciliation_agent.api.dependencies import require_demo_user


api_router = APIRouter(dependencies=[Depends(require_demo_user)])
api_router.include_router(reconcile.router, prefix="/reconcile", tags=["reconcile"])
api_router.include_router(review.router, prefix="/review", tags=["review"])
api_router.include_router(ledger.router, prefix="/ledger", tags=["ledger"])
api_router.include_router(rag.router, prefix="/rag", tags=["rag"])
api_router.include_router(memory.router, prefix="/memory", tags=["memory"])
