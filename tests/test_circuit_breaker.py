from bank_reconciliation_agent.services.circuit_breaker import CircuitBreaker


def test_circuit_breaker_opens_after_threshold_and_recovers_after_half_open_success() -> None:
    now = 0.0

    def fake_time() -> float:
        return now

    breaker = CircuitBreaker(fail_threshold=2, open_seconds=30, time_fn=fake_time)

    assert breaker.state == "CLOSED"

    assert breaker.record_failure() == "CLOSED"
    assert breaker.state == "CLOSED"

    assert breaker.record_failure() == "OPEN"
    assert breaker.state == "OPEN"
    assert breaker.allow_request() is False

    now = 31.0
    assert breaker.state == "HALF_OPEN"
    assert breaker.allow_request() is True

    assert breaker.record_success() == "CLOSED"
    assert breaker.state == "CLOSED"


def test_circuit_breaker_reopens_when_half_open_probe_fails() -> None:
    now = 0.0

    def fake_time() -> float:
        return now

    breaker = CircuitBreaker(fail_threshold=1, open_seconds=10, time_fn=fake_time)

    assert breaker.record_failure() == "OPEN"
    assert breaker.allow_request() is False

    now = 11.0
    assert breaker.allow_request() is True
    assert breaker.state == "HALF_OPEN"

    assert breaker.record_failure() == "OPEN"
    assert breaker.state == "OPEN"
    assert breaker.allow_request() is False
