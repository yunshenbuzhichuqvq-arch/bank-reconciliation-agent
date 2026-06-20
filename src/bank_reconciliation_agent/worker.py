"""ARQ worker entry point.

Run with: uv run arq bank_reconciliation_agent.worker.WorkerSettings
"""

from typing import Any

from arq.connections import RedisSettings

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.services.reconciliation import reconciliation_service


async def on_startup(ctx: dict[str, Any]) -> None:
    reconciliation_service._ensure_core_transaction_tables()


async def on_shutdown(ctx: dict[str, Any]) -> None:
    return None


async def run_reconciliation_job(
    ctx: dict[str, Any],
    *,
    user_id: str,
    task_id: str,
    scenario_type: str,
    bank_path: str,
    clear_path: str,
) -> None:
    reconciliation_service.run_reconciliation_job(
        user_id=user_id,
        task_id=task_id,
        scenario_type=scenario_type,
        bank_path=bank_path,
        clear_path=clear_path,
    )


class WorkerSettings:
    functions = [run_reconciliation_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_dsn)
    max_tries = 3
    on_startup = on_startup
    on_shutdown = on_shutdown
