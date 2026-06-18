from datetime import datetime, timezone

from bank_reconciliation_agent.agents.report_agent import report_agent
from bank_reconciliation_agent.schemas.metrics import OfflineMetrics
from bank_reconciliation_agent.schemas.report import TaskReport, TaskReportMetrics
from bank_reconciliation_agent.services.metrics import metrics_service


def render_number_sections(metrics: TaskReportMetrics) -> str:
    sections = [
        "\n".join(
            [
                "## 本批次概览",
                f"- 任务编号：{metrics.task_id}",
                f"- 对账日期：{metrics.recon_date}",
                f"- 来源 A 笔数：{metrics.source_a_rows}",
                f"- 来源 B 笔数：{metrics.source_b_rows}",
                f"- 自动平账笔数：{metrics.auto_fixed_rows}",
                f"- 自动平账率：{metrics.auto_fix_rate:.2%}",
                f"- AI 处理笔数：{metrics.ai_processed_rows}",
                f"- 待人工笔数：{metrics.pending_human_count}",
                f"- 已复核笔数：{metrics.review_count}",
                f"- 挂账笔数：{metrics.hold_count}",
                f"- 差异金额合计：{metrics.discrepancy_amount_total}",
                f"- Token 消耗：{metrics.total_tokens}",
                f"- LLM 成本：{metrics.total_cost}",
            ]
        ),
        _render_distribution("异常类型分布", metrics.exception_dist),
        _render_distribution("Agent 决策分布", metrics.agent_decision_dist),
        _render_distribution("Fallback 分布", metrics.fallback_dist),
        _render_offline_metrics(metrics),
        _render_rag_sources(metrics.rag_sources),
    ]
    return "\n\n".join(sections)


def build_report(*, user_id: str, task_id: str) -> TaskReport:
    metrics = metrics_service.get_task_report_metrics(user_id=user_id, task_id=task_id)
    if metrics is None:
        raise LookupError("reconciliation task not found")

    number_sections = render_number_sections(metrics)
    narrative = report_agent.narrate(metrics)
    markdown = "\n\n".join(
        [
            number_sections,
            f"## 高风险事项\n{narrative.risk_summary}",
            f"## 人工复核建议\n{narrative.review_advice}",
            f"## 后续建议\n{narrative.followup}",
        ]
    )
    return TaskReport(
        task_id=task_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        llm_used=narrative.llm_used,
        metrics=metrics,
        narrative=narrative,
        markdown=markdown,
    )


def _render_distribution(title: str, values: dict[str, int]) -> str:
    rows = [f"- {key}：{values[key]}" for key in sorted(values)] or ["- 暂无"]
    return "\n".join([f"## {title}", *rows])


def _render_offline_metrics(metrics: TaskReportMetrics) -> str:
    if not isinstance(metrics.offline, OfflineMetrics):
        return "## 检索质量摘要\n- 暂无离线评测快照"
    return "\n".join(
        [
            "## 检索质量摘要",
            f"- RAG Recall@5：{metrics.offline.rag_recall_at5:.4f}",
            f"- RAG MRR：{metrics.offline.rag_mrr:.4f}",
            f"- Schema 符合率：{metrics.offline.schema_conformance_rate:.2%}",
            f"- 评测时间：{metrics.offline.evaluated_at}",
        ]
    )


def _render_rag_sources(sources: list[str]) -> str:
    rows = [f"- {source}" for source in sources] or ["- 暂无"]
    return "\n".join(["## RAG 引用列表", *rows])
