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

MVP-2a3 clearing fixture:

| flow_id | Scenario | Expected error_type | Expected exception_branch | Disposition |
|---------|----------|---------------------|---------------------------|-------------|
| BC3001 | Clearing exact match | None | None | AUTO_FIXED |
| BC3002 | Clearing-side-only in daytime window | CLEARING_SINGLE_SIDE | BC-R001 | PENDING_HUMAN |
| BC3003 | Cutoff cross-day with T+1 core candidate | CUTOFF_CROSS_DAY | BC-R003 | PENDING_HUMAN |
| BC3004 | Cutoff cross-day without T+1 candidate | CUTOFF_CROSS_DAY | BC-R003 | PENDING_HUMAN |
| CORE3003 | Supporting core-side T+1 candidate row | UNCLASSIFIED | None | PENDING_HUMAN |

The authoritative mapping for the MVP-2a3 clearing files is
`BANK_CLEARING_EXPECTED_BRANCHES` in `scripts/generate_mock_excel.py`. The
generated files are `mvp2a3_core.xlsx` and `mvp2a3_clearing.xlsx`.

All sample rows in this directory are fully fabricated for testing. They are
not derived from real customers, real merchants, or real bank/clearing
transactions.

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
