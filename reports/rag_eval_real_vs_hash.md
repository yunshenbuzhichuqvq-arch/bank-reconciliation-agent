# RAG Real Embedding vs Hash Evaluation

## Scope

- Eval set: `data/rag_eval_set.json`
- Cases: 120 total, with 60 bank-enterprise cases and 60 bank-clearing cases.
- Evaluation口径: `min_score=0.0`, measuring ranking quality only.
- Gate policy: report only. No recall hard gate was added.

## Commands Run

```bash
uv sync --extra dev --extra embedding
uv run pytest -m embedding_real -v
uv run python -m scripts.eval_rag --embedding-backend hash --report reports/rag_eval.md --json-report reports/rag_eval_metrics.json
uv run python -m scripts.eval_rag --embedding-backend bge_m3 --report reports/rag_eval_bge_m3.md --json-report reports/rag_eval_bge_m3_metrics.json
uv run python -m scripts.eval_rag --embedding-backend bge_small --report /tmp/rag_eval_bge_small.md --json-report /tmp/rag_eval_bge_small_metrics.json
```

`embedding_real` result: 3 passed, 373 deselected; no skip after caching `BAAI/bge-small-zh-v1.5`.

## Ranking Metrics

| Backend | Scenario | Cases | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| hash | BANK_CLEARING | 60 | 0.1333 | 0.3583 | 0.2281 | 0.2515 |
| hash | BANK_ENTERPRISE | 60 | 0.0500 | 0.0667 | 0.0617 | 0.0541 |
| hash | weighted total | 120 | 0.0917 | 0.2125 | 0.1449 | 0.1528 |
| bge_m3 | BANK_CLEARING | 60 | 0.1833 | 0.4417 | 0.2961 | 0.3180 |
| bge_m3 | BANK_ENTERPRISE | 60 | 0.0000 | 0.0583 | 0.0292 | 0.0340 |
| bge_m3 | weighted total | 120 | 0.0917 | 0.2500 | 0.1626 | 0.1760 |
| bge_small | BANK_CLEARING | 60 | 0.2833 | 0.4667 | 0.3753 | 0.3735 |
| bge_small | BANK_ENTERPRISE | 60 | 0.0333 | 0.0500 | 0.0400 | 0.0333 |
| bge_small | weighted total | 120 | 0.1583 | 0.2583 | 0.2076 | 0.2034 |

## Comparison Notes

- bge-m3 improved weighted Recall@5, MRR, and NDCG@5 over hash, but weighted Hit@1 was tied at 0.0917 rather than strictly better.
- bge-small improved weighted Hit@1, Recall@5, MRR, and NDCG@5 over hash in this eval set.
- BANK_CLEARING benefits strongly from both real embedding backends.
- BANK_ENTERPRISE remains weak for both bge backends. This points to eval labeling / corpus alignment risk rather than a runtime failure, because real model loading and index dimensions were verified.

## Dense Floor Calibration

Calibration method: for each backend, query all eval cases with `top_k=5` and `min_score=0.0`, collect scores where retrieved chunks match `expected_chunk_ids`, then compare against unrelated queries (`今天天气如何`, `明天北京会不会下雨`, `午饭吃什么比较好`) across both scenarios.

| Backend | Correct hit min | Unrelated max | Chosen floor | Difference from architecture §6.7 `0.5` |
| --- | ---: | ---: | ---: | --- |
| bge_m3 | 0.5529 | 0.4672 | 0.510 | +0.010 |
| bge_small | 0.5600 | 0.4539 | 0.507 | +0.007 |

The calibrated floors sit between unrelated-query maximum scores and correct-hit minimum scores. They are close to the architecture §6.7 placeholder of `0.5`, but now have measured backing.

## Saturation Notes

Recall@5 is not saturated:

- hash weighted Recall@5: 0.2125
- bge-m3 weighted Recall@5: 0.2500
- bge-small weighted Recall@5: 0.2583

Hit@1, MRR, and NDCG@5 remain the primary ranking-quality metrics for future recall gate design.

## Risks / Follow-up

- TASK-RE.8 acceptance expected bge-m3 to beat hash on Hit@1 / MRR / NDCG. The real run shows bge-m3 tied on Hit@1 and better on MRR / NDCG. This is a spec-result deviation, not a skipped run.
- bge-small outperformed bge-m3 on this eval set; before setting any recall gate, review BANK_ENTERPRISE labels and whether bge-m3 needs query prefixing or corpus-side instruction tuning.
- Default CI still does not run real model paths; it relies on opt-in `embedding_real` and manual eval reports.
