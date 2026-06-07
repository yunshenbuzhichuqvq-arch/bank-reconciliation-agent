from __future__ import annotations

import json
from pathlib import Path

from bank_reconciliation_agent.core.config import settings


class TraceWriter:
    def __init__(self, trace_dir: str | None = None) -> None:
        self.trace_dir = Path(trace_dir or settings.trace_dir)

    def write(self, *, task_id: str, flow_id: str, payload: dict) -> Path:
        task_trace_dir = self.trace_dir / task_id
        task_trace_dir.mkdir(parents=True, exist_ok=True)
        trace_path = task_trace_dir / f"{flow_id}.json"
        trace_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return trace_path


trace_writer = TraceWriter()
