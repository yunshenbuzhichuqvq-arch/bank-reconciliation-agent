from datetime import datetime

from fastapi import UploadFile

from bank_reconciliation_agent.schemas.reconciliation import (
    ReconciliationStartResponse,
    ReconciliationStatusResponse,
    ReconciliationUploadResponse,
)


class ReconciliationService:
    async def upload(
        self,
        bank_file: UploadFile,
        clear_file: UploadFile,
    ) -> ReconciliationUploadResponse:
        # Placeholder keeps the API contract stable while Excel parsing is added next.
        task_id = f"TASK_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return ReconciliationUploadResponse(
            task_id=task_id,
            total_bank_rows=0,
            total_clear_rows=0,
            auto_fixed_rows=0,
            pending_ai_rows=0,
            pending_human_rows=0,
        )

    def start(self, task_id: str) -> ReconciliationStartResponse:
        return ReconciliationStartResponse(task_id=task_id, status="AI_RUNNING")

    def get_status(self, task_id: str) -> ReconciliationStatusResponse:
        return ReconciliationStatusResponse(
            task_id=task_id,
            status="UPLOADED",
            auto_fixed_rows=0,
            ai_processed_rows=0,
            pending_human_rows=0,
            unresolved_rows=0,
        )


reconciliation_service = ReconciliationService()

