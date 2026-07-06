# RAG Mode Comparison Report

## Metadata

| Key | Value |
|---|---|
| Embedding Backend | `hash` |
| Top K | 5 |
| Case Count | 120 |
| Evaluated At | 2026-07-06T17:28:57.067014Z |

## Mode Selection

- **Baseline**: dense
- **Selected**: hybrid_rerank
- **Reason**: Highest NDCG@5 among eligible modes with no negative ranking deltas

## Global Metrics by Mode

| Mode | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | ---: | ---: | ---: | ---: |
| dense | 0.1667 | 0.3875 | 0.2750 | 0.2824 |
| hybrid | 0.3083 | 0.5625 | 0.4515 | 0.4448 |
| hybrid_rerank | 0.4333 | 0.6583 | 0.5682 | 0.5528 |

## Deltas vs Dense

| Mode | Δ Hit@1 | Δ MRR | Δ NDCG@5 |
| --- | ---: | ---: | ---: |
| hybrid | +0.1417 | +0.1765 | +0.1623 |
| hybrid_rerank | +0.2667 | +0.2932 | +0.2704 |
