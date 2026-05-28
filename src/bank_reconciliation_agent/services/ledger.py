from __future__ import annotations

from bank_reconciliation_agent.schemas.common import Page
from bank_reconciliation_agent.schemas.ledger import LedgerQuery, LedgerRow


class LedgerService:
    def __init__(self) -> None:
        self._rows: list[LedgerRow] = []
        self._next_id = 1

    def replace_task_rows(self, task_id: str, rows: list[LedgerRow]) -> None:
        """用同一任务的最新异常结果覆盖旧台账，避免重复上传/查询产生重复行。"""
        self._rows = [row for row in self._rows if row.task_id != task_id]
        for row in rows:
            self._rows.append(row.model_copy(update={"id": self._next_id}))
            self._next_id += 1

    def list(self, query: LedgerQuery) -> Page[LedgerRow]:
        """根据查询条件返回差错台账分页结果。"""
        rows = self._filter_rows(query)
        start = (query.page - 1) * query.page_size
        end = start + query.page_size
        return Page(
            items=rows[start:end],
            total=len(rows),
            page=query.page,
            page_size=query.page_size,
        )

    def _filter_rows(self, query: LedgerQuery) -> list[LedgerRow]:
        rows = self._rows
        if query.task_id:
            rows = [row for row in rows if row.task_id == query.task_id]
        if query.error_type:
            rows = [row for row in rows if row.error_type == query.error_type]
        if query.handle_status:
            rows = [row for row in rows if row.handle_status == query.handle_status]
        return rows


ledger_service = LedgerService()
