# RAG Quality Matrix Report

## Metadata

| Key | Value |
|---|---|
| Case Count | 120 |
| Top K | 5 |
| Real Backend Policy | `skip` |
| Evaluated At | 2026-07-07T07:31:52.775503Z |
| Best Real Backend | `N/A` |

## Row Summary

| Backend | Eff Backend | Status | Selected Mode | Reason |
| --- | --- | --- | --- | --- |
| hash | hash | measured | hybrid_rerank | Highest NDCG@5 among eligible modes with no negative ranking |
| bge_small | - | not_run | - | real backend policy is skip |
| bge_m3 | - | not_run | - | real backend policy is skip |

## Global Metrics by Backend × Mode

### dense | Backend | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| hash | 0.1667 | 0.3875 | 0.2750 | 0.2824 |
| bge_small | - | - | - | - |
| bge_m3 | - | - | - | - |

### hybrid | Backend | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| hash | 0.3083 | 0.5625 | 0.4515 | 0.4448 |
| bge_small | - | - | - | - |
| bge_m3 | - | - | - | - |

### hybrid_rerank | Backend | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| hash | 0.4333 | 0.6583 | 0.5682 | 0.5528 |
| bge_small | - | - | - | - |
| bge_m3 | - | - | - | - |
