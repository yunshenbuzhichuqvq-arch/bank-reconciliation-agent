# Mock Data

MVP-0 sample Excel files will live here.

All files in this folder must be manually constructed simulation data. Do not add real customer information, real account numbers, real transaction flows, or internal bank documents.

Current sample coverage:

- Normal matched rows.
- Amount mismatch rows.
- Source A only rows: enterprise book has posted, bank statement has not arrived (`BANK_UNARRIVED`).
- Source B only rows: bank statement has arrived, enterprise book has not recorded (`BOOK_UNRECORDED`).

The files intentionally look closer to raw enterprise book and bank statement exports than to database tables.
Parser code normalizes them into the PRD model.

Shared normalized columns:

- `flow_id`
- `amount`
- `trade_time`
- `summary`

Source A enterprise book fields:

- Voucher number, accounting period, accounting date/time, value date.
- Own masked account, own masked customer name, bank name.
- Transaction direction, debit amount, credit amount, fee amount, balance after posting.
- Counterparty masked account/name/bank.
- Channel, purpose, posting status, branch number, teller id, transaction code, source system.

Source B bank statement fields:

- Bank serial number, channel, trade time, settlement date.
- Transaction amount, fee amount, net amount, currency, status.
- Own and counterparty masked accounts and names.
