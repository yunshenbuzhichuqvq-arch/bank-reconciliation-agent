# RAG Optimization Comparison Report

## Target

- **Scenario**: BANK_CLEARING
- **Error Type**: SINGLE_SIDE_MISSING
- **Backend**: `bge_m3`
- **Mode**: `hybrid`

## Trust

- **Trusted**: No
  - baseline matrix lacks bucket_metrics for bge_m3/hybrid

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
| miss_count | - | 7 | - |
| hit_at_1 | - | 0.3 | - |
| recall_at_5 | - | 0.45 | - |
| mrr | - | 0.395 | - |
| ndcg_at_5 | - | 0.3528136245145182 | - |

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

## Verdict

- **Success**: No
- **Failure Reasons**:
  - baseline matrix lacks bucket_metrics for bge_m3/hybrid
  - target bucket BANK_CLEARING/SINGLE_SIDE_MISSING did not improve (recall: None -> 0.45, miss_count: None -> 7)
