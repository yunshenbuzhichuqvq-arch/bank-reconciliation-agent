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
