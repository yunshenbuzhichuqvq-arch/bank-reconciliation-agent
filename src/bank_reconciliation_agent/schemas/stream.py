from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class StreamEventType(StrEnum):
    TASK_STARTED = "task_started"
    HOOK = "hook"
    RAG_RETRIEVED = "rag_retrieved"
    AGENT_DECISION = "agent_decision"
    FALLBACK = "fallback"
    ITEM_DONE = "item_done"
    TASK_DONE = "task_done"


class AgentStreamEvent(BaseModel):
    """Versioned SSE event contract for agent execution streams.

    Payload keys are intentionally aligned with agent_log semantics:
    - task_started: scenario_type, total_rows
    - hook: hook_name, agent_name, status
    - rag_retrieved: agent_name, chunk_ids, best_score, query
    - agent_decision: agent_name, decision, confidence, evidence, next_action, prompt_version
    - fallback: agent_name, fallback_level, reason, next_action
    - item_done: flow_id, status, decision, confidence
    - task_done: status, ai_processed_rows, fallback_l2_rows, fallback_l3_rows
    """

    schema_version: str = "1.0"
    event_type: StreamEventType
    seq: int
    task_id: str
    flow_id: str | None = None
    ts: datetime
    payload: dict[str, Any]
