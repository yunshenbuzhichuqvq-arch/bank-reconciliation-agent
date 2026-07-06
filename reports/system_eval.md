# System Evaluation Report

## Metadata

| Key | Value |
|---|---|
| Seed | `20260706` |
| Scenario | `BANK_ENTERPRISE` |
| Normal Rows | 1000 |
| Total Cases | 1007 |
| Normal Cases | 1001 |
| Anomaly Cases | 6 |
| Evaluated At | 2026-07-06T09:54:17.149099+00:00 |

## Metrics

| Metric | Value |
|---|---|
| case_count | 1007 |
| auto_fix_rate | 0.994042 |
| classification_accuracy | 1.0 |
| branch_accuracy | 1.0 |
| pending_human_rate | 0.005958 |
| fallback_trigger_rate | 0.0 |
| unsafe_auto_fix_rate | 0.0 |
| hard_constraint_violation_rate | 0.0 |

## Gates

| Gate | Value | Threshold | Pass |
|---|---|---|---|
| unsafe_auto_fix_rate | 0.0 | 0 | ✅ |
| hard_constraint_violation_rate | 0.0 | 0 | ✅ |

## Anomaly Distribution

| Error Type | Count |
|---|---|
| AMOUNT_MISMATCH | 1 |
| BANK_UNARRIVED | 1 |
| BOOK_UNRECORDED | 1 |
| DUPLICATE_BOOKING | 2 |
| NARRATIVE_NAME_MISMATCH | 1 |
