# RAG Optimization Comparison Report

## Target

- **Scenario**: BANK_CLEARING
- **Error Type**: SINGLE_SIDE_MISSING
- **Backend**: `bge_m3`
- **Mode**: `hybrid`

## Trust

- **Trusted**: Yes

## Baseline Source

- case_count: 120
- top_k: 5
- status: measured
- effective_backend: `bge_m3`
- real_backend_policy: auto

## After Source

- case_count: 120
- top_k: 5
- status: measured
- effective_backend: `bge_m3`
- real_backend_policy: auto

## Target Bucket

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| miss_count | 7 | 7 | 0 |
| hit_at_1 | 0.1000 | 0.3000 | 0.2000 |
| recall_at_5 | 0.4000 | 0.4500 | 0.0500 |
| mrr | 0.2833 | 0.3950 | 0.1117 |
| ndcg_at_5 | 0.2938 | 0.3528 | 0.0591 |

- **Improved**: No

## Global

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| hit_at_1 | 0.5583 | 0.6167 | 0.0583 |
| recall_at_5 | 0.7542 | 0.7875 | 0.0333 |
| mrr | 0.6675 | 0.7221 | 0.0546 |
| ndcg_at_5 | 0.6552 | 0.7007 | 0.0455 |

- **Within Regression Limit**: Yes
- **Max Allowed Regression**: 0.02

## Largest Regressions (up to 3)

| Scenario | Error Type | Δ NDCG@5 | Δ MRR | Δ Recall@5 |
| --- | --- | ---: | ---: | ---: |
| BANK_CLEARING | AMOUNT_MISMATCH | -0.0361 | 0.0133 | -0.1000 |

## Largest Improvements (up to 3)

| Scenario | Error Type | Δ NDCG@5 | Δ MRR | Δ Recall@5 |
| --- | --- | ---: | ---: | ---: |
| BANK_CLEARING | CLEARING_FILE_EXCEPTION | 0.1160 | 0.0833 | 0.1500 |
| BANK_ENTERPRISE | AMOUNT_MISMATCH | 0.1000 | 0.0833 | 0.0833 |
| BANK_ENTERPRISE | BANK_UNARRIVED | 0.0734 | 0.0486 | 0.0417 |

## Verdict

- **Success**: No
- **Failure Reasons**:
  - target bucket BANK_CLEARING/SINGLE_SIDE_MISSING did not improve (recall: 0.4 -> 0.45, miss_count: 7 -> 7)
