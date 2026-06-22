from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from sqlalchemy import text

from bank_reconciliation_agent.api.v1.auth import router as auth_router
from bank_reconciliation_agent.api.v1.router import api_router
from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.core.logging import configure_logging
from bank_reconciliation_agent.db.session import get_engine


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title=settings.app_name)
    app.include_router(auth_router, prefix=settings.api_v1_prefix)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        db_status = "ok"
        try:
            engine = get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            db_status = "unavailable"
        return {
            "status": "ok" if db_status == "ok" else "degraded",
            "service": settings.app_name,
            "db": db_status,
        }

    return app


app = create_app()
