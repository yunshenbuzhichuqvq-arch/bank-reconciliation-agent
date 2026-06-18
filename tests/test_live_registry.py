from bank_reconciliation_agent.services import live_registry
from bank_reconciliation_agent.services.live_registry import (
    get_emitter,
    register,
    unregister,
)
from bank_reconciliation_agent.services.stream_emitter import QueueEmitter


def test_live_registry_register_get_unregister_lifecycle() -> None:
    task_id = "TASK_V1_3_2_REGISTRY"

    emitter = register(task_id)

    assert isinstance(emitter, QueueEmitter)
    assert get_emitter(task_id) is emitter

    unregister(task_id)

    assert get_emitter(task_id) is None


def test_finished_emitter_is_retained_until_ttl_expires(monkeypatch) -> None:
    task_id = "TASK_V1_3_2_REGISTRY_FINISHED_TTL"
    now = 100.0
    monkeypatch.setattr(live_registry, "monotonic", lambda: now)

    emitter = register(task_id)
    live_registry.mark_finished(task_id)

    now += live_registry.LIVE_EMITTER_TTL_SECONDS - 1
    assert emitter.finished
    assert get_emitter(task_id) is emitter

    now += 1
    assert get_emitter(task_id) is None


def test_unfinished_emitter_is_removed_after_max_age(monkeypatch) -> None:
    task_id = "TASK_V1_3_2_REGISTRY_MAX_AGE"
    now = 200.0
    monkeypatch.setattr(live_registry, "monotonic", lambda: now)
    assert live_registry.LIVE_EMITTER_MAX_AGE_SECONDS == 3600

    register(task_id)

    now += live_registry.LIVE_EMITTER_MAX_AGE_SECONDS
    assert get_emitter(task_id) is None
