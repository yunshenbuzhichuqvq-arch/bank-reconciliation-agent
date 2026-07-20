from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Literal


BreakerState = Literal["CLOSED", "OPEN", "HALF_OPEN"]


@dataclass(frozen=True, slots=True)
class BreakerPermit:
    generation: int
    state_before: BreakerState


@dataclass(frozen=True, slots=True)
class BreakerAdmission:
    state_before: BreakerState
    permit: BreakerPermit | None

    @property
    def allowed(self) -> bool:
        return self.permit is not None


class CircuitBreaker:
    def __init__(
        self,
        *,
        fail_threshold: int,
        open_seconds: int,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self.fail_threshold = max(1, fail_threshold)
        self.open_seconds = max(0, open_seconds)
        self._time_fn = time_fn or time.monotonic
        self._state: BreakerState = "CLOSED"
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False
        self._generation = 0
        self._lock = Lock()

    @property
    def state(self) -> BreakerState:
        with self._lock:
            return self._state_now()

    def _state_now(self) -> BreakerState:
        if self._state == "OPEN" and self._opened_at is not None:
            if self._time_fn() - self._opened_at >= self.open_seconds:
                self._state = "HALF_OPEN"
                self._opened_at = None
                self._half_open_probe_in_flight = False
                self._generation += 1
        return self._state

    def acquire(self) -> BreakerAdmission:
        """Atomically admit one request and bind it to the current generation."""

        with self._lock:
            state = self._state_now()
            if state == "OPEN":
                return BreakerAdmission(state_before=state, permit=None)
            if state == "HALF_OPEN":
                if self._half_open_probe_in_flight:
                    return BreakerAdmission(state_before=state, permit=None)
                self._half_open_probe_in_flight = True
            return BreakerAdmission(
                state_before=state,
                permit=BreakerPermit(
                    generation=self._generation,
                    state_before=state,
                ),
            )

    def allow_request(self) -> bool:
        """Compatibility API; concurrent callers should use :meth:`acquire`."""

        return self.acquire().allowed

    def record_success(self, permit: BreakerPermit | None = None) -> BreakerState:
        with self._lock:
            self._state_now()
            if permit is not None:
                if permit.generation != self._generation:
                    return self._state
                if permit.state_before == "HALF_OPEN":
                    if self._state != "HALF_OPEN" or not self._half_open_probe_in_flight:
                        return self._state
                    self._generation += 1
                elif self._state != "CLOSED":
                    return self._state

            self._failure_count = 0
            self._opened_at = None
            self._half_open_probe_in_flight = False
            self._state = "CLOSED"
            return self._state

    def record_failure(self, permit: BreakerPermit | None = None) -> BreakerState:
        with self._lock:
            state = self._state_now()
            if permit is not None:
                if permit.generation != self._generation:
                    return self._state
                if permit.state_before == "HALF_OPEN":
                    if state != "HALF_OPEN" or not self._half_open_probe_in_flight:
                        return self._state
                    return self._open()
                if state != "CLOSED":
                    return self._state
            elif state == "HALF_OPEN":
                return self._open()
            elif state == "OPEN":
                return self._state

            self._failure_count += 1
            if self._failure_count >= self.fail_threshold:
                return self._open()
            return self._state

    def release_permit(self, permit: BreakerPermit) -> BreakerState:
        """Finish a request whose outcome must not affect breaker failures."""

        with self._lock:
            state = self._state_now()
            if permit.generation != self._generation:
                return self._state
            if permit.state_before == "HALF_OPEN" and state == "HALF_OPEN":
                self._half_open_probe_in_flight = False
                self._generation += 1
            return self._state

    def _open(self) -> BreakerState:
        self._state = "OPEN"
        self._opened_at = self._time_fn()
        self._half_open_probe_in_flight = False
        self._generation += 1
        return self._state
