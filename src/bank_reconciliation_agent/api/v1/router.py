from fastapi import APIRouter, Depends

from bank_reconciliation_agent.api.v1 import ledger, metrics, rag, reconcile, review, stream, trace
from bank_reconciliation_agent.api.dependencies import verify_jwt


api_router = APIRouter(dependencies=[Depends(verify_jwt)])
api_router.include_router(reconcile.router, prefix="/reconcile", tags=["reconcile"])
api_router.include_router(stream.router, prefix="/reconcile", tags=["reconcile"])
api_router.include_router(review.router, prefix="/review", tags=["review"])
api_router.include_router(ledger.router, prefix="/ledger", tags=["ledger"])
api_router.include_router(rag.router, prefix="/rag", tags=["rag"])
api_router.include_router(trace.router, prefix="/traces", tags=["traces"])

api_router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
