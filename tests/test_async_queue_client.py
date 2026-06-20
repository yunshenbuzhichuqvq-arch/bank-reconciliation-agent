import asyncio

from arq.connections import ArqRedis

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.services.queue_client import enqueue_reconciliation


def test_enqueue_reconciliation_only_enqueues_task_once(
    fake_arq_redis: ArqRedis,
    monkeypatch,
) -> None:
    async def run() -> None:
        monkeypatch.setattr(settings, "job_idempotency_ttl_seconds", 120)
        first = await enqueue_reconciliation(
            "task-1",
            "user-1",
            "bank_enterprise",
            "/tmp/bank.xlsx",
            "/tmp/clear.xlsx",
        )
        second = await enqueue_reconciliation(
            "task-1",
            "user-1",
            "bank_enterprise",
            "/tmp/bank.xlsx",
            "/tmp/clear.xlsx",
        )

        assert first is True
        assert second is False
        assert await fake_arq_redis.zcard("arq:queue") == 1
        assert 0 < await fake_arq_redis.ttl("job:task-1") <= 120

    asyncio.run(run())


def test_force_enqueue_replaces_job_key_with_fresh_ttl(
    fake_arq_redis: ArqRedis,
    monkeypatch,
) -> None:
    async def run() -> None:
        monkeypatch.setattr(settings, "job_idempotency_ttl_seconds", 120)
        await fake_arq_redis.set("job:task-force", "stale", ex=1)

        enqueued = await enqueue_reconciliation(
            "task-force",
            "user-1",
            "bank_enterprise",
            "/tmp/bank.xlsx",
            "/tmp/clear.xlsx",
            force=True,
        )

        assert enqueued is True
        assert await fake_arq_redis.get("job:task-force") == b"1"
        assert 1 < await fake_arq_redis.ttl("job:task-force") <= 120

    asyncio.run(run())
