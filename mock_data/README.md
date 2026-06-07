# Mock Data

MVP-0 sample Excel files will live here.

All files in this folder must be manually constructed simulation data. Do not add real customer information, real account numbers, real transaction flows, or internal bank documents.

Current sample coverage:

- Normal matched rows.
- Amount mismatch rows.
- Bank-side-only rows.
- Clearing-side-only rows.

The files intentionally look closer to raw bank and clearing exports than to database tables.
Parser code normalizes them into the PRD model.

MVP-1 branch fixture:

| flow_id | Scenario | Expected error_type | Expected exception_branch | Disposition |
|---------|----------|---------------------|---------------------------|-------------|
| F2001 | Auto fixed exact match | None | None | AUTO_FIXED |
| F2002 | Auto fixed exact match | None | None | AUTO_FIXED |
| F2003 | Amount mismatch | AMOUNT_MISMATCH | BE-R002 | PENDING_HUMAN |
| F2004 | Narrative/name mismatch with refund keyword | NARRATIVE_NAME_MISMATCH | BE-R004 | PENDING_HUMAN |
| F2005 | Enterprise book exists, bank missing | BANK_UNARRIVED | BE-R005 | PENDING_HUMAN |
| F2006 | Bank exists, enterprise book missing | BOOK_UNRECORDED | BE-R006 | PENDING_HUMAN |
| F2007 | Duplicate booking candidate with clear match | DUPLICATE_BOOKING | BE-R008 | PENDING_HUMAN |
| F2008 | Duplicate booking candidate without clear match | DUPLICATE_BOOKING | BE-R008 | PENDING_HUMAN |

The authoritative mapping for the MVP-1 files is `EXPECTED_BRANCHES` in
`scripts/generate_mock_excel.py`. The generated files are `mvp1_bank.xlsx` and
`mvp1_clear.xlsx`.

Shared normalized columns:

- `flow_id`
- `amount`
- `trade_time`
- `summary`

Bank-side realistic fields:

- Bank serial number, accounting date/time, value date.
- Own masked account, own masked customer name, bank name.
- Transaction direction, debit amount, credit amount, fee amount, balance after posting.
- Counterparty masked account/name/bank.
- Channel, purpose, posting status, branch number, teller id, transaction code, source system.

Clearing-side realistic fields:

- Clearing serial number, merchant/store/terminal identifiers.
- Channel, transaction type, trade time, settlement date.
- Transaction amount, fee amount, net amount, currency, status.
- Batch, voucher, reference and merchant order numbers.
- Payer/payee masked accounts and names.
