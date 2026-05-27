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
