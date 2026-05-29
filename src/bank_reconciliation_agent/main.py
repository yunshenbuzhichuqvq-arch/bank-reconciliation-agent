from fastapi import FastAPI

from bank_reconciliation_agent.api.v1.router import api_router
from bank_reconciliation_agent.core.config import settings


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例，并统一挂载当前版本的 API 路由。"""
    app = FastAPI(title=settings.app_name)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        """返回服务健康状态，用于本地调试和部署后的存活检查。"""
        return {"status": "ok", "service": settings.app_name}

    return app


app = create_app()
