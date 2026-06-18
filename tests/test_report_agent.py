from decimal import Decimal

from bank_reconciliation_agent.agents import report_agent as report_agent_module
from bank_reconciliation_agent.agents.report_agent import ReportAgent
from bank_reconciliation_agent.core.llm.provider import FakeLLMProvider, LLMResult, LLMUnavailable
from bank_reconciliation_agent.schemas.metrics import OfflineNoSnapshot
from bank_reconciliation_agent.schemas.report import TaskReportMetrics


def test_report_agent_returns_deterministic_narrative_with_fake_provider() -> None:
    agent = ReportAgent(provider=FakeLLMProvider())

    first = agent.narrate(_metrics())
    second = agent.narrate(_metrics())

    assert first == second
    assert first.llm_used is True
    assert first.risk_summary
    assert first.review_advice
    assert first.followup


def test_report_agent_falls_back_when_provider_is_unavailable() -> None:
    narrative = ReportAgent(provider=UnavailableProvider()).narrate(_metrics())

    assert narrative.llm_used is False
    assert narrative.risk_summary
    assert narrative.review_advice
    assert narrative.followup


def test_report_agent_falls_back_for_invalid_json() -> None:
    narrative = ReportAgent(provider=InvalidJsonProvider()).narrate(_metrics())

    assert narrative.llm_used is False
    assert narrative.risk_summary
    assert narrative.review_advice
    assert narrative.followup


def test_report_agent_logs_agent_name_and_prompt_version(monkeypatch) -> None:
    recorder = LogRecorder()
    monkeypatch.setattr(report_agent_module, "log", recorder)

    ReportAgent(
        provider=UnavailableProvider(),
        prompt_text="report prompt",
        prompt_version="v-test",
    ).narrate(_metrics())

    assert recorder.info_calls == [
        {
            "event": "agent_llm_call",
            "agent_name": "ReportAgent",
            "step": "narrate",
            "prompt_version": "v-test",
        }
    ]
    assert recorder.warning_calls[0]["agent_name"] == "ReportAgent"
    assert recorder.warning_calls[0]["prompt_version"] == "v-test"


def test_report_prompt_forbids_repeating_or_calculating_numbers() -> None:
    agent = ReportAgent(provider=FakeLLMProvider())

    assert agent.prompt_version == "v1"
    assert "禁止复述" in agent.prompt_text
    assert "禁止" in agent.prompt_text and "计算" in agent.prompt_text


def _metrics() -> TaskReportMetrics:
    return TaskReportMetrics(
        task_id="TASK_REPORT",
        user_id="demo_user",
        recon_date="2026-06-18T09:30:00",
        source_a_rows=10,
        source_b_rows=9,
        auto_fixed_rows=6,
        auto_fix_rate=0.6,
        ai_processed_rows=3,
        pending_human_count=2,
        review_count=2,
        hold_count=1,
        discrepancy_amount_total=Decimal("15.75"),
        exception_dist={"BE-R001": 2},
        agent_decision_dist={"PENDING_HUMAN": 2},
        fallback_dist={"L1->L2": 1},
        total_tokens=321,
        total_cost=Decimal("0.1234"),
        offline=OfflineNoSnapshot(status="no_snapshot"),
        rag_sources=["rule-a"],
    )


class UnavailableProvider:
    def complete(self, messages, *, temperature=0.0, response_format="json_object") -> LLMResult:
        del messages, temperature, response_format
        raise LLMUnavailable("provider unavailable")


class InvalidJsonProvider:
    def complete(self, messages, *, temperature=0.0, response_format="json_object") -> LLMResult:
        del messages, temperature, response_format
        return LLMResult(
            text="{not-json",
            prompt_tokens=1,
            completion_tokens=1,
            model="invalid-json",
        )


class LogRecorder:
    def __init__(self) -> None:
        self.info_calls: list[dict[str, object]] = []
        self.warning_calls: list[dict[str, object]] = []

    def info(self, event: str, **kwargs) -> None:
        self.info_calls.append({"event": event, **kwargs})

    def warning(self, event: str, **kwargs) -> None:
        self.warning_calls.append({"event": event, **kwargs})
