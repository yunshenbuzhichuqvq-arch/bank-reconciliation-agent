# Mock Data

MVP-0 sample Excel files will live here.

All files in this folder must be manually constructed simulation data. Do not add real customer information, real account numbers, real transaction flows, or internal bank documents.

Planned sample coverage:

- Normal matched rows.
- Amount mismatch rows.
- Bank-side-only rows.
- Clearing-side-only rows.

Planned shared columns:

- `flow_id`
- `amount`
- `trade_time`
- `summary`
- Bank-side only: `account_no_masked`, `customer_name_masked`
- Clearing-side only: `channel`

