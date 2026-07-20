from __future__ import annotations

from typing import Callable

from sqlalchemy.engine import Engine

from bank_reconciliation_agent.core.llm.cost import compute_cost
from bank_reconciliation_agent.core.logging import log
from bank_reconciliation_agent.services.agent_log import agent_log_service
from bank_reconciliation_agent.services.ledger import error_ledger_table, ledger_service
from bank_reconciliation_agent.services.queue import queue_service, reconciliation_queue_table
from bank_reconciliation_agent.services.rag_log import rag_log_service
from bank_reconciliation_agent.services.reconciliation_types import ReconciliationWriteBundle
from bank_reconciliation_agent.services.task import reconciliation_task_table, task_service
from bank_reconciliation_agent.services.trace import trace_service


def ensure_core_transaction_tables(engine: Engine) -> None:
    error_ledger_table.metadata.create_all(engine, tables=[error_ledger_table])
    reconciliation_queue_table.metadata.create_all(
        engine,
        tables=[reconciliation_queue_table],
    )
    reconciliation_task_table.metadata.create_all(
        engine,
        tables=[reconciliation_task_table],
    )


def persist_write_bundle(
    *,
    engine: Engine,
    user_id: str,
    task_id: str,
    scenario_type: str,
    queue_rows: list[dict[str, object]],
    write_bundle: ReconciliationWriteBundle,
) -> None:
    with engine.begin() as connection:
        ledger_service.replace_task_rows(
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            rows=write_bundle.ledger_rows,
            connection=connection,
        )
        queue_service.replace_task_rows(
            user_id=user_id,
            task_id=task_id,
            scenario_type=scenario_type,
            rows=queue_rows,
            connection=connection,
        )
        task_service.replace_ai_stats(
            user_id=user_id,
            task_id=task_id,
            ai_processed_rows=write_bundle.ai_processed_rows,
            fallback_l2_rows=write_bundle.fallback_l2_rows,
            fallback_l3_rows=write_bundle.fallback_l3_rows,
            total_llm_tokens=(
                write_bundle.total_prompt_tokens + write_bundle.total_completion_tokens
            ),
            total_llm_cost=compute_cost(
                write_bundle.total_prompt_tokens,
                write_bundle.total_completion_tokens,
            ),
            connection=connection,
        )

    run_side_effect(
        side_effect_name="rag_log",
        operation=lambda: rag_log_service.replace_task_rows(
            user_id=user_id,
            task_id=task_id,
            rows=write_bundle.rag_log_rows,
        ),
        task_id=task_id,
    )
    run_side_effect(
        side_effect_name="agent_log",
        operation=lambda: agent_log_service.replace_task_rows(
            user_id=user_id,
            task_id=task_id,
            rows=write_bundle.agent_log_rows,
        ),
        task_id=task_id,
    )
    for flow_id, trace_id, spans in write_bundle.trace_snapshots:
        del trace_id
        run_side_effect(
            side_effect_name="trace",
            operation=lambda flow_id=flow_id, spans=spans: trace_service.persist_snapshot(
                user_id=user_id,
                task_id=task_id,
                flow_id=flow_id,
                spans=spans,
            ),
            task_id=task_id,
            flow_id=flow_id,
        )


def run_side_effect(
    *,
    side_effect_name: str,
    operation: Callable[[], object],
    task_id: str,
    flow_id: str | None = None,
) -> None:
    try:
        operation()
    except Exception as exc:
        log.warning(
            "reconciliation_side_effect_failed",
            task_id=task_id,
            flow_id=flow_id,
            side_effect_failed=side_effect_name,
            error_type=type(exc).__name__,
        )
