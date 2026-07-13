# RAG Optimization Comparison Report

## Target

- **Scenario**: BANK_CLEARING
- **Error Type**: SINGLE_SIDE_MISSING
- **Backend**: `bge_m3`
- **Mode**: `dense`

## Trust

- **Trusted**: Yes

## Baseline Source

- case_count: 120
- top_k: 5
- status: measured
- effective_backend: `bge_m3`
- real_backend_policy: auto
- eval_set_sha256: `71fd0db2e02faeccca15bf177e1582b9db0518af9208dc5025ae6481699929c2`
- chunk_corpus_sha256: `b71d67f6a9954a7ee1a3ab0ad40f80ceaf7de0b14fa00dfd7978f14ed2f78018`

## After Source

- case_count: 120
- top_k: 5
- status: measured
- effective_backend: `bge_m3`
- real_backend_policy: auto
- eval_set_sha256: `71fd0db2e02faeccca15bf177e1582b9db0518af9208dc5025ae6481699929c2`
- chunk_corpus_sha256: `b71d67f6a9954a7ee1a3ab0ad40f80ceaf7de0b14fa00dfd7978f14ed2f78018`

## Target Bucket

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| miss_count | 8 | 9 | 1 |
| hit_at_1 | 0.3000 | 0.2000 | -0.1000 |
| recall_at_5 | 0.3500 | 0.2500 | -0.1000 |
| mrr | 0.3833 | 0.2533 | -0.1300 |
| ndcg_at_5 | 0.3113 | 0.1920 | -0.1193 |

- **Improved**: No

## Global

| Metric | Before | After | Delta |
| --- | ---: | ---: | ---: |
| hit_at_1 | 0.6333 | 0.6250 | -0.0083 |
| recall_at_5 | 0.8250 | 0.8167 | -0.0083 |
| mrr | 0.7353 | 0.7244 | -0.0108 |
| ndcg_at_5 | 0.7209 | 0.7110 | -0.0099 |

- **Within Regression Limit**: Yes
- **Max Allowed Regression**: 0.02

## Side Effect Buckets (All Non-Target)

| Scenario | Error Type | Δ Recall@5 | Δ MRR | Δ NDCG@5 | Δ Miss |
| --- | --- | ---: | ---: | ---: | ---: |
| BANK_CLEARING | AMOUNT_MISMATCH | 0.0000 | 0.0000 | 0.0000 | 0 |
| BANK_CLEARING | CLEARING_FILE_EXCEPTION | 0.0000 | 0.0000 | 0.0000 | 0 |
| BANK_CLEARING | CUTOFF_T1 | 0.0000 | 0.0000 | 0.0000 | 0 |
| BANK_CLEARING | QUERY_REPLY | 0.0000 | 0.0000 | 0.0000 | 0 |
| BANK_CLEARING | REFERENCE_MATCH | 0.0000 | 0.0000 | 0.0000 | 0 |
| BANK_ENTERPRISE | AMOUNT_MISMATCH | 0.0000 | 0.0000 | 0.0000 | 0 |
| BANK_ENTERPRISE | BANK_UNARRIVED | 0.0000 | 0.0000 | 0.0000 | 0 |
| BANK_ENTERPRISE | BOOK_UNRECORDED | 0.0000 | 0.0000 | 0.0000 | 0 |
| BANK_ENTERPRISE | DUPLICATE_BOOKING | 0.0000 | 0.0000 | 0.0000 | 0 |
| BANK_ENTERPRISE | NARRATIVE_NAME_MISMATCH | 0.0000 | 0.0000 | 0.0000 | 0 |

## Verdict

- **Success**: No
- **Failure Reasons**:
  - target bucket BANK_CLEARING/SINGLE_SIDE_MISSING did not improve (recall: 0.35 -> 0.25, miss_count: 8 -> 9)
