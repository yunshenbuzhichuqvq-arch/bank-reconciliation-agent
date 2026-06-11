from __future__ import annotations

import json
import tempfile
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from bank_reconciliation_agent.core.llm.provider import LLMProvider, get_llm_provider
from bank_reconciliation_agent.core.logging import log

from bank_reconciliation_agent.services.memory.long_term import (
    LongTermMemoryService,
    long_term_memory_service,
)
from bank_reconciliation_agent.services.memory.short_term import (
    ShortTermMemoryService,
    short_term_memory_service,
)
from bank_reconciliation_agent.services.memory.summary import (
    SummaryMemoryService,
    summary_memory_service,
)


class MemoryManager:
    def __init__(
        self,
        *,
        long_term_service: LongTermMemoryService | None = None,
        short_term_service: ShortTermMemoryService | None = None,
        summary_service: SummaryMemoryService | None = None,
        llm_provider: LLMProvider | None = None,
        snapshot_dir: str | Path | None = None,
        long_term_token_budget: int = 800,
        short_term_token_budget: int = 600,
        summary_token_budget: int = 300,
    ) -> None:
        self._long_term = long_term_service or long_term_memory_service
        self._short_term = short_term_service or short_term_memory_service
        self._summary = summary_service or summary_memory_service
        self._llm_provider = llm_provider or get_llm_provider()
        self._snapshot_dir = Path(snapshot_dir) if snapshot_dir is not None else Path(tempfile.gettempdir())
        self._long_term_token_budget = long_term_token_budget
        self._short_term_token_budget = short_term_token_budget
        self._summary_token_budget = summary_token_budget

    def build_context(
        self,
        *,
        user_id: str,
        thread_id: str,
        error_type: str,
        current_item: dict[str, object],
    ) -> str:
        keywords = self._query_keywords(error_type=error_type, current_item=current_item)
        long_rows = self._long_term.recall(
            user_id=user_id,
            error_type=error_type,
            keywords=keywords,
            limit=5,
        )
        short_rows = self._short_term.recent(thread_id=thread_id, limit=10)
        summary = self._summary.get(thread_id=thread_id)

        sections: list[str] = []
        long_text = self._format_long_term(long_rows)
        if long_text:
            sections.append(self._truncate_by_tokens(long_text, self._long_term_token_budget))
        short_text = self._format_short_term(short_rows)
        if short_text:
            sections.append(self._truncate_by_tokens(short_text, self._short_term_token_budget))
        summary_text = self._format_summary(summary)
        if summary_text:
            sections.append(self._truncate_by_tokens(summary_text, self._summary_token_budget))
        return "\n\n".join(section for section in sections if section)

    def update_after_decision(
        self,
        *,
        user_id: str,
        thread_id: str,
        error_type: str,
        decision: dict[str, object],
        is_human_confirmed: bool = False,
    ) -> None:
        queue_id = self._int_value(decision.get("queue_id"))
        if queue_id is None:
            return

        if not is_human_confirmed:
            self._short_term.append(
                thread_id=thread_id,
                queue_id=queue_id,
                flow_id=self._string_value(decision.get("flow_id")),
                error_type=error_type,
                risk_level=self._string_value(decision.get("risk_level")),
                decision=str(decision.get("decision") or decision.get("next_action") or "PENDING_HUMAN"),
                confidence=self._decimal_value(decision.get("confidence")) or Decimal("0"),
                expires_at=datetime.utcnow() + timedelta(hours=24),
            )
            self._try_compact_summary(thread_id=thread_id)
            return

        flow_id = decision.get("flow_id")
        if not isinstance(flow_id, str) or not flow_id:
            return

        summary_keywords = self._query_keywords(
            error_type=error_type,
            current_item={
                "amount_diff": decision.get("amount_diff"),
                "summary": decision.get("summary"),
                "description": decision.get("description"),
                "remark": decision.get("remark"),
                "memo": decision.get("memo"),
            },
        )
        self._long_term.append(
            user_id=user_id,
            error_type=error_type,
            exception_branch=self._string_value(decision.get("exception_branch")),
            flow_id=flow_id,
            bank_amount=self._decimal_value(decision.get("bank_amount")),
            clear_amount=self._decimal_value(decision.get("clear_amount")),
            amount_diff=self._decimal_value(decision.get("amount_diff")),
            summary_keywords=summary_keywords,
            human_decision=str(decision.get("human_decision") or decision.get("decision") or ""),
            ai_suggestion=str(decision.get("ai_suggestion") or decision.get("next_action") or ""),
            ai_confidence=self._decimal_value(decision.get("confidence")) or Decimal("0"),
        )

    def _format_long_term(self, rows: list[dict[str, object]]) -> str:
        if not rows:
            return ""
        lines = ["Long-term memory:"]
        for row in rows:
            lines.append(
                " ".join(
                    [
                        f"flow_id={row['flow_id']}",
                        f"branch={row['exception_branch']}",
                        f"bank_amount={row['bank_amount']}",
                        f"clear_amount={row['clear_amount']}",
                        f"amount_diff={row['amount_diff']}",
                        f"human_decision={row['human_decision']}",
                        f"ai_suggestion={row['ai_suggestion']}",
                        f"ai_confidence={row['ai_confidence']}",
                    ]
                )
            )
        return "\n".join(lines)

    def _format_short_term(self, rows: list[dict[str, object]]) -> str:
        if not rows:
            return ""
        lines = ["Short-term memory:"]
        for row in rows:
            lines.append(
                " ".join(
                    [
                        f"queue_id={row['queue_id']}",
                        f"error_type={row['error_type']}",
                        f"decision={row['decision']}",
                        f"confidence={row['confidence']}",
                    ]
                )
            )
        return "\n".join(lines)

    def _format_summary(self, summary: dict[str, object] | None) -> str:
        if summary is None:
            return ""
        return (
            "Summary memory:\n"
            f"compressed_count={summary['compressed_count']} "
            f"summary={summary['summary_text']}"
        )

    def _query_keywords(self, *, error_type: str, current_item: dict[str, object]) -> list[str]:
        keywords: list[str] = [error_type.lower()]
        amount_diff = current_item.get("amount_diff")
        amount_bucket = self._amount_bucket(amount_diff)
        if amount_bucket is not None:
            keywords.append(amount_bucket)
        for field_name in ("summary", "description", "remark", "memo"):
            value = current_item.get(field_name)
            if isinstance(value, str):
                keywords.extend(self._top_words(value))
        return list(dict.fromkeys(keywords))

    def _amount_bucket(self, value: object) -> str | None:
        if value is None:
            return None
        try:
            amount = abs(Decimal(str(value)))
        except Exception:
            return None
        if amount >= Decimal("10000"):
            return "amount_large"
        if amount >= Decimal("1000"):
            return "amount_medium"
        return "amount_small"

    def _top_words(self, value: str, limit: int = 8) -> list[str]:
        words = re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]+", value.lower())
        return [word for word in words if len(word) >= 2][:limit]

    def _truncate_by_tokens(self, text: str, token_budget: int) -> str:
        if token_budget <= 0:
            return ""
        lines = text.splitlines()
        kept_lines: list[str] = []
        used = 0
        for line in lines:
            token_count = len(line.split())
            if used + token_count > token_budget:
                break
            kept_lines.append(line)
            used += token_count
        return "\n".join(kept_lines)

    def _decimal_value(self, value: object) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            decimal_value = Decimal(str(value))
        except Exception:
            return None
        return decimal_value.quantize(Decimal("0.0001"))

    def _int_value(self, value: object) -> int | None:
        try:
            return int(value)
        except Exception:
            return None

    def _string_value(self, value: object) -> str | None:
        if isinstance(value, str) and value:
            return value
        return None

    def _try_compact_summary(self, *, thread_id: str) -> None:
        summary = self._summary.get(thread_id=thread_id)
        compressed_count = int(summary["compressed_count"]) if summary is not None else 0
        total_count = self._short_term.count(thread_id=thread_id)
        if total_count - compressed_count < 20:
            return

        rows = self._short_term.recent(thread_id=thread_id, limit=20)
        if len(rows) < 20:
            return

        snapshot_path = self._write_snapshot(thread_id=thread_id, rows=rows)
        try:
            summary_text = self._summarize_rows(thread_id=thread_id, rows=rows, snapshot_path=snapshot_path)
        except Exception as exc:
            log.warning(
                "memory_summary_compaction_failed",
                thread_id=thread_id,
                error_type=type(exc).__name__,
            )
            return

        if not self._summary_passes_validation(summary_text=summary_text, rows=rows):
            log.warning(
                "memory_summary_validation_failed",
                thread_id=thread_id,
                snapshot_path=str(snapshot_path),
            )
            return

        self._summary.upsert(
            thread_id=thread_id,
            summary_text=summary_text,
            compressed_count=compressed_count + 20,
            last_compressed_at=datetime.utcnow(),
        )

    def _write_snapshot(self, *, thread_id: str, rows: list[dict[str, object]]) -> Path:
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = self._snapshot_dir / f"{thread_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}.json"
        snapshot_path.write_text(
            json.dumps(rows, ensure_ascii=False, default=str, indent=2),
            encoding="utf-8",
        )
        return snapshot_path

    def _summarize_rows(
        self,
        *,
        thread_id: str,
        rows: list[dict[str, object]],
        snapshot_path: Path,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You summarize reconciliation short-term memory into concise text. "
                    "Keep all HIGH risk items, preserve all PENDING_HUMAN items, and mention as many flow_id values as possible."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "memory_summary",
                        "thread_id": thread_id,
                        "snapshot_path": str(snapshot_path),
                        "rows": rows,
                    },
                    ensure_ascii=False,
                    default=str,
                    sort_keys=True,
                ),
            },
        ]
        result = self._llm_provider.complete(
            messages,
            temperature=0.0,
            response_format="json_object",
        )
        payload = json.loads(result.text)
        summary_text = payload.get("summary_text")
        if not isinstance(summary_text, str) or not summary_text.strip():
            raise ValueError("summary_text missing")
        return summary_text.strip()

    def _summary_passes_validation(self, *, summary_text: str, rows: list[dict[str, object]]) -> bool:
        normalized = summary_text.lower()
        high_rows = [row for row in rows if row.get("risk_level") == "HIGH"]
        pending_rows = [row for row in rows if row.get("decision") == "PENDING_HUMAN"]

        for row in high_rows:
            flow_id = self._string_value(row.get("flow_id"))
            if flow_id is None or flow_id.lower() not in normalized:
                return False
        if pending_rows and not any(
            token in normalized for token in ("pending_human", "pending human", "pending")
        ):
            return False

        source_flow_ids = [flow_id for flow_id in (self._string_value(row.get("flow_id")) for row in rows) if flow_id]
        mentioned = sum(1 for flow_id in source_flow_ids if flow_id.lower() in normalized)
        return mentioned >= max(1, int(len(source_flow_ids) * 0.8))


memory_manager = MemoryManager()
