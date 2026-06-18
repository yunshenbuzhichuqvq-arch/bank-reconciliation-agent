from __future__ import annotations

from threading import Lock
from time import monotonic

from bank_reconciliation_agent.services.stream_emitter import QueueEmitter


LIVE_EMITTER_TTL_SECONDS = 60
LIVE_EMITTER_MAX_AGE_SECONDS = 30

_emitters: dict[str, QueueEmitter] = {}
_lock = Lock()


def register(task_id: str) -> QueueEmitter:
    with _lock:
        now = monotonic()
        _sweep(now)
        emitter = QueueEmitter(created_at=now)
        _emitters[task_id] = emitter
    return emitter


def get_emitter(task_id: str) -> QueueEmitter | None:
    with _lock:
        _sweep(monotonic())
        return _emitters.get(task_id)


def mark_finished(task_id: str) -> None:
    with _lock:
        emitter = _emitters.get(task_id)
        if emitter is not None:
            emitter.mark_finished(finished_at=monotonic())


def unregister(task_id: str) -> None:
    with _lock:
        _emitters.pop(task_id, None)


def _sweep(now: float) -> None:
    expired = [
        task_id
        for task_id, emitter in _emitters.items()
        if (
            emitter.finished_at is not None
            and now - emitter.finished_at >= LIVE_EMITTER_TTL_SECONDS
        )
        or (
            emitter.finished_at is None
            and emitter.created_at is not None
            and now - emitter.created_at >= LIVE_EMITTER_MAX_AGE_SECONDS
        )
    ]
    for task_id in expired:
        _emitters.pop(task_id, None)
