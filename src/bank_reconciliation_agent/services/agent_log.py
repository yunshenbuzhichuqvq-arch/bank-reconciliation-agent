from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
    delete,
    func,
    insert,
    select,
)
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.db.session import get_engine


metadata = MetaData()

agent_execution_log_table = Table(
    "t_agent_execution_log",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("user_id", String(64), nullable=False, server_default="demo_user"),
    Column("scenario_type", String(32), nullable=False, server_default="BANK_ENTERPRISE"),
    Column("task_id", String(64), nullable=False),
    Column("queue_id", BigInteger, nullable=True),
    Column("agent_name", String(64), nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("input_payload", JSON().with_variant(Text, "sqlite"), nullable=False),
    Column("output_payload", JSON().with_variant(Text, "sqlite"), nullable=False),
    Column("pre_hook_results", JSON().with_variant(Text, "sqlite"), nullable=True),
    Column("post_hook_results", JSON().with_variant(Text, "sqlite"), nullable=True),
    Column("rag_retrieval_id", BigInteger, nullable=True),
    Column("prompt_version", String(16), nullable=True),
    Column("fallback_level", Integer, nullable=False, server_default="0"),
    Column("llm_tokens", Integer, nullable=False, server_default="0"),
    Column("error_message", Text, nullable=True),
    Column("created_at", DateTime, server_default=func.now()),
    Index("idx_user_task_queue", "user_id", "task_id", "queue_id"),
    Index("idx_agent_event", "agent_name", "event_type"),
)


class AgentLogService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    def replace_task_rows(
        self,
        *,
        user_id: str,
        task_id: str,
        rows: list[dict[str, object]],
    ) -> None:
        self._ensure_initialized()
        with self._engine.begin() as connection:
            connection.execute(
                delete(agent_execution_log_table).where(
                    agent_execution_log_table.c.user_id == user_id,
                    agent_execution_log_table.c.task_id == task_id,
                )
            )
            if rows:
                connection.execute(
                    insert(agent_execution_log_table),
                    [self._to_insert_values(user_id, row) for row in rows],
                )

    def build_row(
        self,
        *,
        user_id: str,
        task_id: str,
        queue_id: int | None,
        agent_name: str,
        event_type: str,
        input_payload: dict,
        output_payload: dict,
        pre_hook_results: dict[str, object] | None = None,
        post_hook_results: dict[str, object] | None = None,
        rag_retrieval_id: int | None = None,
        prompt_version: str | None = None,
        fallback_level: int = 0,
        llm_tokens: int = 0,
        error_message: str | None = None,
    ) -> dict[str, object]:
        return {
            "user_id": user_id,
            "task_id": task_id,
            "queue_id": queue_id,
            "agent_name": agent_name,
            "event_type": event_type,
            "input_payload": input_payload,
            "output_payload": output_payload,
            "pre_hook_results": pre_hook_results,
            "post_hook_results": post_hook_results,
            "rag_retrieval_id": rag_retrieval_id,
            "prompt_version": prompt_version,
            "fallback_level": fallback_level,
            "llm_tokens": llm_tokens,
            "error_message": error_message,
        }

    def count_rows(self, *, user_id: str, task_id: str) -> int:
        self._ensure_initialized()
        statement = (
            select(func.count())
            .select_from(agent_execution_log_table)
            .where(
                agent_execution_log_table.c.user_id == user_id,
                agent_execution_log_table.c.task_id == task_id,
            )
        )
        with self._engine.connect() as connection:
            return connection.execute(statement).scalar_one()

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        metadata.create_all(self._engine, tables=[agent_execution_log_table])
        self._initialized = True

    def _to_insert_values(self, user_id: str, row: dict[str, object]) -> dict[str, object]:
        return {
            "user_id": user_id,
            "task_id": row["task_id"],
            "queue_id": row["queue_id"],
            "agent_name": row["agent_name"],
            "event_type": row["event_type"],
            "input_payload": self._payload_for_storage(row["input_payload"]),
            "output_payload": self._payload_for_storage(row["output_payload"]),
            "pre_hook_results": self._payload_for_storage(row["pre_hook_results"]),
            "post_hook_results": self._payload_for_storage(row["post_hook_results"]),
            "rag_retrieval_id": row["rag_retrieval_id"],
            "prompt_version": row["prompt_version"],
            "fallback_level": row["fallback_level"],
            "llm_tokens": row["llm_tokens"],
            "error_message": row["error_message"],
        }

    def _payload_for_storage(self, value: object) -> object:
        if value is None:
            return None
        if self._engine.dialect.name == "sqlite":
            return self._json_dumps(value)
        return value

    def _json_dumps(self, value: object) -> str:
        return json.dumps(value, ensure_ascii=False, default=self._json_default)

    def _json_default(self, value: object) -> object:
        if isinstance(value, Decimal):
            return str(value)
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


agent_log_service = AgentLogService()
