from bank_reconciliation_agent.schemas.common import Page
from bank_reconciliation_agent.schemas.ledger import LedgerQuery, LedgerRow


class LedgerService:
    def list(self, query: LedgerQuery) -> Page[LedgerRow]:
        return Page(items=[], total=0, page=query.page, page_size=query.page_size)


ledger_service = LedgerService()

