from fastapi import APIRouter

from bank_reconciliation_agent.api.v1 import ledger, rag, reconcile


api_router = APIRouter()
api_router.include_router(reconcile.router, prefix="/reconcile", tags=["reconcile"])
api_router.include_router(ledger.router, prefix="/ledger", tags=["ledger"])
api_router.include_router(rag.router, prefix="/rag", tags=["rag"])

