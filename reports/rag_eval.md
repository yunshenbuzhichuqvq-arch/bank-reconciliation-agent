# RAG Evaluation Report

## Metadata

| Key | Value |
|---|---|
| Embedding Backend | `hash` |
| Top K | 5 |
| Case Count | 120 |
| Evaluated At | 2026-07-06T10:14:15.151090Z |

## Global Metrics

| Metric | Value |
|---|---|
| Hit@1 | 0.1667 |
| Recall@5 | 0.3875 |
| MRR | 0.2750 |
| NDCG@5 | 0.2824 |

## By Scenario

| Scenario | Cases | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| BANK_CLEARING | 60 | 0.2000 | 0.4500 | 0.3106 | 0.3283 |
| BANK_ENTERPRISE | 60 | 0.1333 | 0.3250 | 0.2394 | 0.2365 |

## By Scenario × Error Type

| Scenario | Error Type | Cases | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| BANK_CLEARING | AMOUNT_MISMATCH | 10 | 0.2000 | 0.3500 | 0.2667 | 0.2657 |
| BANK_CLEARING | CLEARING_FILE_EXCEPTION | 10 | 0.3000 | 0.5000 | 0.3833 | 0.4131 |
| BANK_CLEARING | CUTOFF_T1 | 10 | 0.3000 | 0.6000 | 0.4233 | 0.4562 |
| BANK_CLEARING | QUERY_REPLY | 10 | 0.1000 | 0.3500 | 0.2500 | 0.2546 |
| BANK_CLEARING | REFERENCE_MATCH | 10 | 0.3000 | 0.7000 | 0.4400 | 0.4723 |
| BANK_CLEARING | SINGLE_SIDE_MISSING | 10 | 0.0000 | 0.2000 | 0.1000 | 0.1082 |
| BANK_ENTERPRISE | AMOUNT_MISMATCH | 12 | 0.0000 | 0.1250 | 0.0903 | 0.0798 |
| BANK_ENTERPRISE | BANK_UNARRIVED | 12 | 0.0833 | 0.3333 | 0.2222 | 0.2294 |
| BANK_ENTERPRISE | BOOK_UNRECORDED | 12 | 0.3333 | 0.4167 | 0.3889 | 0.3522 |
| BANK_ENTERPRISE | DUPLICATE_BOOKING | 12 | 0.2500 | 0.4583 | 0.3889 | 0.3750 |
| BANK_ENTERPRISE | NARRATIVE_NAME_MISMATCH | 12 | 0.0000 | 0.2917 | 0.1069 | 0.1463 |

## Notes

- Recall@5 is evaluated on desaturated bank-enterprise and bank-clearing corpora; use MRR, NDCG@5, and Hit@1 for ranking quality.
