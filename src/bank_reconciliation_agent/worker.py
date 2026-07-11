"""ARQ worker entry point.

Run with: uv run arq bank_reconciliation_agent.worker.WorkerSettings
"""

from typing import Any

from arq import Retry
from arq.connections import RedisSettings
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import OperationalError

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.services.reconciliation import reconciliation_service
from bank_reconciliation_agent.services.task import task_service


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
    raw_attempt = ctx.get("job_try", 1)
    if not isinstance(raw_attempt, int) or isinstance(raw_attempt, bool) or raw_attempt < 1:
        raise ValueError(f"invalid job_try: {raw_attempt!r}")
    attempt = raw_attempt
    max_attempts = settings.arq_job_max_attempts
    if attempt > max_attempts:
        raise RuntimeError(f"attempt {attempt} exceeds max_attempts {max_attempts}")

    started = task_service.mark_attempt_started(
        user_id=user_id, task_id=task_id, attempt=attempt
    )
    if not started:
        log.warning(
            "terminal_noop",
            user_id=user_id,
            task_id=task_id,
            attempt=attempt,
            max_attempts=max_attempts,
            outcome="terminal_noop",
        )
        return

    log.info(
        "attempt_started",
        user_id=user_id,
        task_id=task_id,
        attempt=attempt,
        max_attempts=max_attempts,
        outcome="attempt_started",
    )

    try:
        reconciliation_service.run_reconciliation_job(
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            bank_path=bank_path,
            clear_path=clear_path,
        )
    except (RedisConnectionError, OperationalError) as exc:
        error_type = _failure_type_for(exc)
        failure_summary = _failure_summary_for(exc)
        if attempt < max_attempts:
            log.warning(
                "retry_scheduled",
                user_id=user_id,
                task_id=task_id,
                attempt=attempt,
                max_attempts=max_attempts,
                error_type=error_type,
                outcome="retry_scheduled",
            )
            raise Retry()
        if task_service.mark_failed_if_active(
            user_id=user_id,
            task_id=task_id,
            attempt=attempt,
            failure_type=error_type,
            failure_summary=failure_summary,
        ):
            log.warning(
                "retry_exhausted",
                user_id=user_id,
                task_id=task_id,
                attempt=attempt,
                max_attempts=max_attempts,
                error_type=error_type,
                outcome="retry_exhausted",
            )
        else:
            log.warning(
                "terminal_noop",
                user_id=user_id,
                task_id=task_id,
                attempt=attempt,
                max_attempts=max_attempts,
                error_type=error_type,
                outcome="terminal_noop",
            )
        raise

    success_recorded = task_service.mark_attempt_succeeded(
        user_id=user_id, task_id=task_id, attempt=attempt
    )
    if success_recorded:
        if attempt > 1:
            log.info(
                "retry_recovered",
                user_id=user_id,
                task_id=task_id,
                attempt=attempt,
                max_attempts=max_attempts,
                outcome="retry_recovered",
            )
        log.info("reconciliation_job_completed", task_id=task_id, user_id=user_id)


def _failure_type_for(exc: Exception) -> str:
    if isinstance(exc, RedisConnectionError):
        return "RedisConnectionError"
    return "OperationalError"


def _failure_summary_for(exc: Exception) -> str:
    if isinstance(exc, RedisConnectionError):
        return "redis connection unavailable"
    return "database operation unavailable"


class WorkerSettings:
    functions = [run_reconciliation_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_dsn)
    max_tries = settings.arq_job_max_attempts
    job_timeout = settings.arq_job_timeout_seconds
    on_startup = on_startup
    on_shutdown = on_shutdown
