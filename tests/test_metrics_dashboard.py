from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import delete, insert

from bank_reconciliation_agent.db.session import get_engine
from bank_reconciliation_agent.core.llm.cache import CachingLLMProvider
from bank_reconciliation_agent.core.llm.cost import compute_cost
from bank_reconciliation_agent.core.llm.rate_limit import RateLimitedLLMProvider
from bank_reconciliation_agent.main import app
from bank_reconciliation_agent.services.ledger import error_ledger_table
from bank_reconciliation_agent.services.metrics import MetricsService, metrics_service
from bank_reconciliation_agent.services.review import human_review_table
from bank_reconciliation_agent.services.task import reconciliation_task_table


client = TestClient(app)


def test_llm_cache_metrics_exposes_runtime_hit_rate_and_saved_cost(monkeypatch) -> None:
    _reset_llm_cache_metrics(monkeypatch)
    provider = CachingLLMProvider(_MetricsCountingProvider(), _MetricsCache(), ttl_seconds=60)
    messages = [{"role": "user", "content": "reconcile"}]

    provider.complete(messages)
    provider.complete(messages)

    assert MetricsService().get_llm_cache_metrics() == {
        "source": "runtime_memory",
        "hits": 1,
        "misses": 1,
        "hit_rate": 0.5,
        "saved_prompt_tokens": 12,
        "saved_completion_tokens": 4,
        "saved_cost": compute_cost(12, 4),
    }


def test_llm_cache_metrics_returns_honest_zeroes_without_runtime_data(monkeypatch) -> None:
    _reset_llm_cache_metrics(monkeypatch)

    assert MetricsService().get_llm_cache_metrics() == {
        "source": "runtime_memory",
        "hits": 0,
        "misses": 0,
        "hit_rate": 0.0,
        "saved_prompt_tokens": 0,
        "saved_completion_tokens": 0,
        "saved_cost": Decimal("0"),
    }


def test_llm_rate_limit_metrics_exposes_runtime_activity(monkeypatch) -> None:
    _reset_llm_rate_limit_metrics(monkeypatch)
    monkeypatch.setattr(RateLimitedLLMProvider, "_waits", 3)
    monkeypatch.setattr(RateLimitedLLMProvider, "_wait_seconds_total", 1.25)
    monkeypatch.setattr(RateLimitedLLMProvider, "_rejections", 2)
    monkeypatch.setattr(RateLimitedLLMProvider, "_degraded", 1)

    assert MetricsService().get_llm_rate_limit_metrics() == {
        "source": "runtime_memory",
        "waits": 3,
        "wait_seconds_total": 1.25,
        "rejections": 2,
        "degraded": 1,
    }


def test_llm_rate_limit_metrics_returns_honest_zeroes(monkeypatch) -> None:
    _reset_llm_rate_limit_metrics(monkeypatch)

    assert MetricsService().get_llm_rate_limit_metrics() == {
        "source": "runtime_memory",
        "waits": 0,
        "wait_seconds_total": 0.0,
        "rejections": 0,
        "degraded": 0,
    }


class _MetricsCountingProvider:
    model = "metrics-test"

    def complete(self, messages, *, temperature=0.0, response_format="json_object"):
        del messages, temperature, response_format
        from bank_reconciliation_agent.core.llm.provider import LLMResult

        return LLMResult(
            text="cached response",
            prompt_tokens=12,
            completion_tokens=4,
            model=self.model,
        )


class _MetricsCache:
    def __init__(self) -> None:
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl_seconds, value):
        del ttl_seconds
        self.values[key] = value


def _reset_llm_cache_metrics(monkeypatch) -> None:
    monkeypatch.setattr(CachingLLMProvider, "_hits", 0)
    monkeypatch.setattr(CachingLLMProvider, "_misses", 0)
    monkeypatch.setattr(CachingLLMProvider, "_saved_prompt_tokens", 0)
    monkeypatch.setattr(CachingLLMProvider, "_saved_completion_tokens", 0)


def _reset_llm_rate_limit_metrics(monkeypatch) -> None:
    monkeypatch.setattr(RateLimitedLLMProvider, "_waits", 0)
    monkeypatch.setattr(RateLimitedLLMProvider, "_wait_seconds_total", 0.0)
    monkeypatch.setattr(RateLimitedLLMProvider, "_rejections", 0)
    monkeypatch.setattr(RateLimitedLLMProvider, "_degraded", 0)


def test_dashboard_metrics_aggregates_online_rows_for_current_user(tmp_path: Path, monkeypatch) -> None:
    _reset_metrics_tables()
    monkeypatch.setattr(metrics_service, "_rag_snapshot_path", tmp_path / "missing_rag_eval_metrics.json")
    monkeypatch.setattr(
        metrics_service,
        "_schema_snapshot_path",
        tmp_path / "missing_agent_schema_conformance.json",
    )
    _insert_task(
        user_id="demo_user",
        task_id="TASK_METRICS_A",
        status="COMPLETED",
        auto_fixed_rows=3,
        pending_human_rows=1,
        unresolved_rows=1,
        fallback_l2_rows=1,
        fallback_l3_rows=1,
        total_llm_tokens=120,
        total_llm_cost=Decimal("0.0456"),
    )
    _insert_task(
        user_id="demo_user",
        task_id="TASK_METRICS_B",
        status="AI_RUNNING",
        auto_fixed_rows=1,
        pending_human_rows=2,
        unresolved_rows=2,
        fallback_l2_rows=0,
        fallback_l3_rows=0,
        total_llm_tokens=80,
        total_llm_cost=Decimal("0.0100"),
    )
    _insert_ledger(
        user_id="demo_user",
        task_id="TASK_METRICS_A",
        flow_id="FLOW_A1",
        error_type="AMOUNT_MISMATCH",
        fallback_path="L1->L2",
        ai_confidence=Decimal("0.9200"),
    )
    _insert_ledger(
        user_id="demo_user",
        task_id="TASK_METRICS_A",
        flow_id="FLOW_A2",
        error_type="AMOUNT_MISMATCH",
        fallback_path="L1->L2->L3->HUMAN",
        ai_confidence=Decimal("0.6800"),
    )
    _insert_ledger(
        user_id="demo_user",
        task_id="TASK_METRICS_B",
        flow_id="FLOW_B1",
        error_type="BANK_UNARRIVED",
        fallback_path=None,
        ai_confidence=None,
    )
    _insert_review(user_id="demo_user", task_id="TASK_METRICS_A", queue_id=1)
    _insert_review(user_id="other_user", task_id="TASK_OTHER", queue_id=2)

    response = client.get("/api/v1/metrics/dashboard", headers={"X-User-ID": "demo_user"})

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["online"] == {
        "auto_fix_rate": 0.5,
        "pending_human_count": 3,
        "hung_count": 1,
        "exception_dist": {"AMOUNT_MISMATCH": 2, "BANK_UNARRIVED": 1},
        "fallback_dist": {"L1->L2": 1, "L1->L2->L3->HUMAN": 1},
        "total_tokens": 200,
        "total_cost": "0.0556",
        "confidence_dist": {"high": 1, "medium": 1, "low": 0, "unknown": 1},
    }
    assert body["offline"] == {"status": "no_snapshot"}
    assert body["unavailable"] == {
        "latency": "no_data_source",
        "agent_accuracy": "no_ground_truth",
    }


def test_dashboard_metrics_filters_other_users_and_handles_empty_data() -> None:
    _reset_metrics_tables()
    _insert_task(
        user_id="other_user",
        task_id="TASK_OTHER_ONLY",
        status="AI_RUNNING",
        auto_fixed_rows=9,
        pending_human_rows=9,
        unresolved_rows=9,
        fallback_l2_rows=9,
        fallback_l3_rows=9,
        total_llm_tokens=999,
        total_llm_cost=Decimal("9.9999"),
    )
    _insert_ledger(
        user_id="other_user",
        task_id="TASK_OTHER_ONLY",
        flow_id="FLOW_OTHER",
        error_type="AMOUNT_MISMATCH",
        fallback_path="L1->L2",
        ai_confidence=Decimal("0.9900"),
    )

    response = client.get("/api/v1/metrics/dashboard", headers={"X-User-ID": "demo_user"})

    assert response.status_code == 200
    assert response.json()["data"]["online"] == {
        "auto_fix_rate": 0.0,
        "pending_human_count": 0,
        "hung_count": 0,
        "exception_dist": {},
        "fallback_dist": {},
        "total_tokens": 0,
        "total_cost": "0.0000",
        "confidence_dist": {"high": 0, "medium": 0, "low": 0, "unknown": 0},
    }


def test_dashboard_metrics_reads_offline_snapshot_files(tmp_path: Path) -> None:
    _reset_metrics_tables()
    rag_snapshot = tmp_path / "rag_eval_metrics.json"
    schema_snapshot = tmp_path / "agent_schema_conformance.json"
    rag_snapshot.write_text(
        json.dumps(
            {
                "rag_recall_at5": 0.75,
                "rag_mrr": 0.625,
                "evaluated_at": "2026-06-16T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    schema_snapshot.write_text(
        json.dumps(
            {
                "schema_conformance_rate": 1.0,
                "evaluated_at": "2026-06-16T11:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    result = MetricsService(
        rag_snapshot_path=rag_snapshot,
        schema_snapshot_path=schema_snapshot,
    ).get_dashboard(user_id="demo_user")

    assert result.offline.model_dump(mode="json") == {
        "rag_recall_at5": 0.75,
        "rag_mrr": 0.625,
        "schema_conformance_rate": 1.0,
        "evaluated_at": "2026-06-16T11:00:00Z",
    }


def _reset_metrics_tables() -> None:
    engine = get_engine()
    reconciliation_task_table.metadata.create_all(engine, tables=[reconciliation_task_table])
    error_ledger_table.metadata.create_all(engine, tables=[error_ledger_table])
    human_review_table.metadata.create_all(engine, tables=[human_review_table])
    with engine.begin() as connection:
        connection.execute(delete(human_review_table))
        connection.execute(delete(error_ledger_table))
        connection.execute(delete(reconciliation_task_table))


def _insert_task(
    *,
    user_id: str,
    task_id: str,
    status: str,
    auto_fixed_rows: int,
    pending_human_rows: int,
    unresolved_rows: int,
    fallback_l2_rows: int,
    fallback_l3_rows: int,
    total_llm_tokens: int,
    total_llm_cost: Decimal,
) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            insert(reconciliation_task_table).values(
                user_id=user_id,
                task_id=task_id,
                scenario_type="BANK_ENTERPRISE",
                task_name=f"{task_id} reconciliation",
                status=status,
                total_bank_rows=4,
                total_clear_rows=4,
                auto_fixed_rows=auto_fixed_rows,
                pending_ai_rows=0,
                pending_human_rows=pending_human_rows,
                unresolved_rows=unresolved_rows,
                ai_processed_rows=0,
                fallback_l2_rows=fallback_l2_rows,
                fallback_l3_rows=fallback_l3_rows,
                total_llm_tokens=total_llm_tokens,
                total_llm_cost=total_llm_cost,
            )
        )


def _insert_ledger(
    *,
    user_id: str,
    task_id: str,
    flow_id: str,
    error_type: str,
    fallback_path: str | None,
    ai_confidence: Decimal | None,
) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            insert(error_ledger_table).values(
                user_id=user_id,
                task_id=task_id,
                scenario_type="BANK_ENTERPRISE",
                flow_id=flow_id,
                error_type=error_type,
                exception_branch="BE-R001",
                discrepancy_amount=Decimal("1.00"),
                fallback_path=fallback_path,
                handle_status="PENDING_HUMAN",
                ai_confidence=ai_confidence,
            )
        )


def _insert_review(*, user_id: str, task_id: str, queue_id: int) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            insert(human_review_table).values(
                user_id=user_id,
                scenario_type="BANK_ENTERPRISE",
                queue_id=queue_id,
                task_id=task_id,
                ai_suggestion="PENDING_HUMAN",
                ai_fallback_level=0,
                action="APPROVED_MATCH",
                handler_username="reviewer",
            )
        )
