from decimal import Decimal

from bank_reconciliation_agent.schemas.metrics import OfflineMetrics, OfflineNoSnapshot
from bank_reconciliation_agent.schemas.report import ReportNarrative, TaskReportMetrics


EXPECTED_NUMBER_SECTIONS = """## 本批次概览
- 任务编号：TASK_REPORT
- 对账日期：2026-06-18T09:30:00
- 来源 A 笔数：10
- 来源 B 笔数：9
- 自动平账笔数：6
- 自动平账率：60.00%
- AI 处理笔数：3
- 待人工笔数：2
- 已复核笔数：2
- 挂账笔数：1
- 差异金额合计：15.75
- Token 消耗：321
- LLM 成本：0.1234

## 异常类型分布
- BE-R001：2
- BE-R002：1

## Agent 决策分布
- FIXED：1
- PENDING_HUMAN：2

## Fallback 分布
- L1->L2：1

## 检索质量摘要
- RAG Recall@5：0.7500
- RAG MRR：0.6250
- Schema 符合率：100.00%
- 评测时间：2026-06-18T08:00:00Z

## RAG 引用列表
- rule-a
- rule-b"""


def test_render_number_sections_matches_golden() -> None:
    from bank_reconciliation_agent.services.report import render_number_sections

    assert render_number_sections(_metrics()) == EXPECTED_NUMBER_SECTIONS


def test_build_report_keeps_number_sections_unchanged_by_agent(monkeypatch) -> None:
    from bank_reconciliation_agent.services import report as report_service

    monkeypatch.setattr(report_service, "metrics_service", StubMetricsService(_metrics()))
    monkeypatch.setattr(report_service, "report_agent", InventedNumbersAgent())

    result = report_service.build_report(user_id="demo_user", task_id="TASK_REPORT")

    number_sections = result.markdown.split("\n\n## 高风险事项", 1)[0]
    assert number_sections == EXPECTED_NUMBER_SECTIONS
    assert "虚构九百九十九笔" in result.markdown
    assert result.llm_used is True


def test_build_report_remains_complete_with_fallback_narrative(monkeypatch) -> None:
    from bank_reconciliation_agent.services import report as report_service

    monkeypatch.setattr(report_service, "metrics_service", StubMetricsService(_metrics()))
    monkeypatch.setattr(report_service, "report_agent", FallbackAgent())

    result = report_service.build_report(user_id="demo_user", task_id="TASK_REPORT")

    assert EXPECTED_NUMBER_SECTIONS in result.markdown
    assert "## 高风险事项\n模板风险摘要" in result.markdown
    assert "## 人工复核建议\n模板复核建议" in result.markdown
    assert "## 后续建议\n模板后续建议" in result.markdown
    assert result.llm_used is False
    assert result.generated_at.endswith("+00:00")


def test_render_number_sections_marks_missing_offline_snapshot() -> None:
    from bank_reconciliation_agent.services.report import render_number_sections

    metrics = _metrics().model_copy(update={"offline": OfflineNoSnapshot(status="no_snapshot")})

    assert "## 检索质量摘要\n- 暂无离线评测快照" in render_number_sections(metrics)


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
        exception_dist={"BE-R002": 1, "BE-R001": 2},
        agent_decision_dist={"PENDING_HUMAN": 2, "FIXED": 1},
        fallback_dist={"L1->L2": 1},
        total_tokens=321,
        total_cost=Decimal("0.1234"),
        offline=OfflineMetrics(
            rag_recall_at5=0.75,
            rag_mrr=0.625,
            schema_conformance_rate=1.0,
            evaluated_at="2026-06-18T08:00:00Z",
        ),
        rag_sources=["rule-a", "rule-b"],
    )


class StubMetricsService:
    def __init__(self, metrics: TaskReportMetrics) -> None:
        self.metrics = metrics

    def get_task_report_metrics(self, *, user_id: str, task_id: str) -> TaskReportMetrics:
        assert user_id == "demo_user"
        assert task_id == "TASK_REPORT"
        return self.metrics


class InventedNumbersAgent:
    def narrate(self, metrics: TaskReportMetrics) -> ReportNarrative:
        assert metrics.task_id == "TASK_REPORT"
        return ReportNarrative(
            risk_summary="虚构九百九十九笔高风险事项。",
            review_advice="虚构八十八次人工复核。",
            followup="虚构七十七项后续动作。",
            llm_used=True,
        )


class FallbackAgent:
    def narrate(self, metrics: TaskReportMetrics) -> ReportNarrative:
        assert metrics.task_id == "TASK_REPORT"
        return ReportNarrative(
            risk_summary="模板风险摘要",
            review_advice="模板复核建议",
            followup="模板后续建议",
            llm_used=False,
        )
