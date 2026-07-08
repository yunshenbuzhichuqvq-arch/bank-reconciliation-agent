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
| miss_count | 7 | 8 | 1 |
| hit_at_1 | 0.1000 | 0.3000 | 0.2000 |
| recall_at_5 | 0.4000 | 0.3500 | -0.0500 |
| mrr | 0.2833 | 0.3833 | 0.1000 |
| ndcg_at_5 | 0.2938 | 0.3113 | 0.0176 |

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
| BANK_ENTERPRISE | NARRATIVE_NAME_MISMATCH | -0.0119 | 0.0250 | -0.0417 |
| BANK_CLEARING | REFERENCE_MATCH | -0.0112 | -0.0250 | 0.0000 |

## Largest Improvements (up to 3)

| Scenario | Error Type | Δ NDCG@5 | Δ MRR | Δ Recall@5 |
| --- | --- | ---: | ---: | ---: |
| BANK_ENTERPRISE | BANK_UNARRIVED | 0.2142 | 0.2361 | 0.1667 |
| BANK_ENTERPRISE | AMOUNT_MISMATCH | 0.1704 | 0.1250 | 0.2083 |
| BANK_ENTERPRISE | DUPLICATE_BOOKING | 0.0965 | 0.1042 | 0.1250 |

## Verdict

- **Success**: No
- **Failure Reasons**:
  - target bucket BANK_CLEARING/SINGLE_SIDE_MISSING did not improve (recall: 0.4 -> 0.35, miss_count: 7 -> 8)
