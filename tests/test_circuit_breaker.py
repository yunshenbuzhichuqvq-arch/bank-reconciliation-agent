from concurrent.futures import ThreadPoolExecutor

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


def test_circuit_breaker_success_resets_intermittent_failures() -> None:
    """LLM breaker relies on scattered failures not accumulating to OPEN."""
    breaker = CircuitBreaker(fail_threshold=3, open_seconds=30, time_fn=lambda: 0.0)

    assert breaker.record_failure() == "CLOSED"
    assert breaker.record_failure() == "CLOSED"
    assert breaker.record_success() == "CLOSED"

    assert breaker.record_failure() == "CLOSED"
    assert breaker.record_failure() == "CLOSED"
    assert breaker.state == "CLOSED"


def test_stale_success_cannot_close_new_open_generation() -> None:
    breaker = CircuitBreaker(fail_threshold=1, open_seconds=30, time_fn=lambda: 0.0)
    opening = breaker.acquire()
    late_success = breaker.acquire()
    assert opening.permit is not None
    assert late_success.permit is not None

    assert breaker.record_failure(opening.permit) == "OPEN"
    assert breaker.record_success(late_success.permit) == "OPEN"
    assert breaker.state == "OPEN"


def test_stale_failure_does_not_extend_new_open_generation() -> None:
    now = [0.0]
    breaker = CircuitBreaker(fail_threshold=1, open_seconds=10, time_fn=lambda: now[0])
    opening = breaker.acquire()
    late_failure = breaker.acquire()
    assert opening.permit is not None
    assert late_failure.permit is not None

    assert breaker.record_failure(opening.permit) == "OPEN"
    now[0] = 5.0
    assert breaker.record_failure(late_failure.permit) == "OPEN"
    now[0] = 11.0
    assert breaker.state == "HALF_OPEN"


def test_half_open_admission_is_atomic_and_only_probe_can_close() -> None:
    now = [0.0]
    breaker = CircuitBreaker(fail_threshold=1, open_seconds=1, time_fn=lambda: now[0])
    assert breaker.record_failure() == "OPEN"
    denied = breaker.acquire()
    assert denied.allowed is False
    assert denied.state_before == "OPEN"
    now[0] = 2.0

    with ThreadPoolExecutor(max_workers=8) as executor:
        admissions = list(executor.map(lambda _: breaker.acquire(), range(8)))

    allowed = [admission for admission in admissions if admission.allowed]
    assert len(allowed) == 1
    assert {admission.state_before for admission in admissions} == {"HALF_OPEN"}
    permit = allowed[0].permit
    assert permit is not None
    assert breaker.record_success(permit) == "CLOSED"


def test_neutral_half_open_result_releases_probe_for_next_admission() -> None:
    now = [0.0]
    breaker = CircuitBreaker(fail_threshold=1, open_seconds=1, time_fn=lambda: now[0])
    assert breaker.record_failure() == "OPEN"
    now[0] = 2.0
    neutral = breaker.acquire()
    assert neutral.permit is not None

    assert breaker.release_permit(neutral.permit) == "HALF_OPEN"
    retry = breaker.acquire()
    assert retry.allowed is True
    assert retry.state_before == "HALF_OPEN"
    assert retry.permit is not None
    assert breaker.record_success(retry.permit) == "CLOSED"


def test_search_rules_adapter_drives_breaker_state_machine() -> None:
    from bank_reconciliation_agent.schemas.rag import RagSearchRequest, RagSearchResponse
    from bank_reconciliation_agent.schemas.tools import SearchRulesArgs, ToolContext
    from bank_reconciliation_agent.services.tool_adapters import make_search_rules_adapter

    class _FlakyRetriever:
        def __init__(self) -> None:
            self.fail_next = True

        def search(self, request: RagSearchRequest) -> RagSearchResponse:
            if self.fail_next:
                raise RuntimeError("retriever down")
            return RagSearchResponse(items=[], rewritten_query=None)

    breaker = CircuitBreaker(fail_threshold=2, open_seconds=30, time_fn=lambda: 0.0)
    retriever = _FlakyRetriever()
    adapter = make_search_rules_adapter(retriever=retriever, rag_breaker=breaker)
    context = ToolContext(
        user_id="u",
        task_id="t",
        flow_id="f",
        scenario_type="BANK_CLEARING",
        exception_branch="BC-R003",
    )

    try:
        adapter(SearchRulesArgs(query="x"), context)
    except RuntimeError:
        pass
    assert breaker._failure_count == 1

    retriever.fail_next = False
    adapter(SearchRulesArgs(query="x"), context)
    assert breaker.state == "CLOSED"
    assert breaker._failure_count == 0
