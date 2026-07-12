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
