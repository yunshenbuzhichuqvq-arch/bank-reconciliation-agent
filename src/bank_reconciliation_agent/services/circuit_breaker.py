from __future__ import annotations

import time
from typing import Callable, Literal


BreakerState = Literal["CLOSED", "OPEN", "HALF_OPEN"]


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

    @property
    def state(self) -> BreakerState:
        if self._state == "OPEN" and self._opened_at is not None:
            if self._time_fn() - self._opened_at >= self.open_seconds:
                self._state = "HALF_OPEN"
                self._opened_at = None
        return self._state

    def allow_request(self) -> bool:
        return self.state != "OPEN"

    def record_success(self) -> BreakerState:
        self._failure_count = 0
        self._opened_at = None
        self._state = "CLOSED"
        return self._state

    def record_failure(self) -> BreakerState:
        if self.state == "HALF_OPEN":
            self._state = "OPEN"
            self._opened_at = self._time_fn()
            return self._state

        self._failure_count += 1
        if self._failure_count >= self.fail_threshold:
            self._state = "OPEN"
            self._opened_at = self._time_fn()
        return self._state
