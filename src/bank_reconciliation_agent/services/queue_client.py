from arq.connections import ArqRedis, RedisSettings, create_pool

from bank_reconciliation_agent.core.config import settings


_redis_pool: ArqRedis | None = None


async def get_redis_pool() -> ArqRedis:
    global _redis_pool

    if _redis_pool is None:
        _redis_pool = await create_pool(RedisSettings.from_dsn(settings.redis_dsn))
    return _redis_pool


async def enqueue_reconciliation(
    task_id: str,
    user_id: str,
    scenario_type: str,
    bank_path: str,
    clear_path: str,
) -> bool:
    redis_pool = await get_redis_pool()
    acquired = await redis_pool.set(f"job:{task_id}", "1", nx=True)
    if not acquired:
        return False

    await redis_pool.enqueue_job(
        "run_reconciliation_job",
        user_id=user_id,
        task_id=task_id,
        scenario_type=scenario_type,
        bank_path=bank_path,
        clear_path=clear_path,
    )
    return True
