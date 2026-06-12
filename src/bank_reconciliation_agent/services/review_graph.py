from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import NotRequired, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.services.review import review_service


class ReviewGraphState(TypedDict):
    task_id: str
    user_id: str
    queue_id: int
    action: NotRequired[str]
    handler_username: NotRequired[str]
    remark: NotRequired[str | None]
    result: NotRequired[dict]


def human_review_node(state: ReviewGraphState) -> ReviewGraphState:
    action = interrupt(
        {
            "task_id": state["task_id"],
            "queue_id": state["queue_id"],
            "handler_username": state.get("handler_username"),
            "remark": state.get("remark"),
        }
    )
    return {"action": action}


def apply_decision_node(state: ReviewGraphState) -> ReviewGraphState:
    result = review_service.apply_checkpoint_decision(
        user_id=state["user_id"],
        task_id=state["task_id"],
        queue_id=state["queue_id"],
        action=state["action"],
        handler_username=state["handler_username"],
        remark=state.get("remark"),
    )
    return {"result": result.model_dump()}


def build_review_graph(checkpointer: SqliteSaver | None = None):
    builder = StateGraph(ReviewGraphState)
    builder.add_node("human_review", human_review_node)
    builder.add_node("apply_decision", apply_decision_node)
    builder.add_edge(START, "human_review")
    builder.add_edge("human_review", "apply_decision")
    builder.add_edge("apply_decision", END)
    return builder.compile(checkpointer=checkpointer or _default_checkpointer())


@lru_cache(maxsize=1)
def get_review_graph():
    return build_review_graph()


def _default_checkpointer() -> SqliteSaver:
    checkpoint_path = Path(settings.checkpoint_sqlite_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
    return SqliteSaver(connection)
