from bank_reconciliation_agent.services.hooks import memory_hook


class FakeMemoryManager:
    def __init__(self, context: str | None = "memory context") -> None:
        self.context = context
        self.calls: list[dict[str, object]] = []

    def build_context(self, **kwargs: object) -> str | None:
        self.calls.append(kwargs)
        return self.context


class FailingMemoryManager:
    def build_context(self, **kwargs: object) -> str:
        del kwargs
        raise RuntimeError("memory unavailable")


def test_memory_hook_builds_context_from_state() -> None:
    manager = FakeMemoryManager(context="remember FLOW-001")
    state = {
        "user_id": "user-001",
        "thread_id": "thread-001",
        "error_type": "AMOUNT_MISMATCH",
        "source_a_item": {"flow_id": "FLOW-001", "summary": "bank side"},
        "source_b_item": {"flow_id": "FLOW-001", "summary": "clear side"},
        "math_result": {"amount_diff": "10.00"},
    }

    result = memory_hook(state, memory_manager=manager)

    assert result["memory_context"] == "remember FLOW-001"
    assert manager.calls == [
        {
            "user_id": "user-001",
            "thread_id": "thread-001",
            "error_type": "AMOUNT_MISMATCH",
            "current_item": {
                "amount_diff": "10.00",
                "summary": "bank side clear side",
            },
        }
    ]


def test_memory_hook_degrades_to_none_when_manager_fails() -> None:
    state = {
        "user_id": "user-001",
        "thread_id": "thread-001",
        "error_type": "AMOUNT_MISMATCH",
        "source_a_item": {},
        "source_b_item": {},
        "math_result": {},
    }

    result = memory_hook(state, memory_manager=FailingMemoryManager())

    assert result["memory_context"] is None
