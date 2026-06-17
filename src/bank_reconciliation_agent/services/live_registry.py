from __future__ import annotations

from threading import Lock

from bank_reconciliation_agent.services.stream_emitter import QueueEmitter


_emitters: dict[str, QueueEmitter] = {}
_lock = Lock()


def register(task_id: str) -> QueueEmitter:
    emitter = QueueEmitter()
    with _lock:
        _emitters[task_id] = emitter
    return emitter


def get_emitter(task_id: str) -> QueueEmitter | None:
    with _lock:
        return _emitters.get(task_id)


def unregister(task_id: str) -> None:
    with _lock:
        _emitters.pop(task_id, None)
