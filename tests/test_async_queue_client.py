import asyncio

from arq.connections import ArqRedis

from bank_reconciliation_agent.services.queue_client import enqueue_reconciliation


def test_enqueue_reconciliation_only_enqueues_task_once(fake_arq_redis: ArqRedis) -> None:
    async def run() -> None:
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

    asyncio.run(run())
