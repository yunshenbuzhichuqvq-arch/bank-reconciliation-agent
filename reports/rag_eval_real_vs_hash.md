# RAG Real Embedding vs Hash Evaluation

## Scope

- Eval set: `data/rag_eval_set.json`
- Cases: 120 total, with 60 bank-enterprise cases and 60 bank-clearing cases.
- Query rewrite: keyword-stuffed queries were replaced with natural-language operator questions. `EvalCase` schema was unchanged.
- Gate policy: report only. No recall hard gate was added.

## Hash Baseline

Command:

```bash
uv run python -m scripts.eval_rag --embedding-backend hash --report reports/rag_eval.md --json-report reports/rag_eval_metrics.json
```

| Backend | Scenario | Cases | Hit@1 | Recall@5 | MRR | NDCG@5 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| hash | BANK_CLEARING | 60 | 0.1333 | 0.3583 | 0.2281 | 0.2515 |
| hash | BANK_ENTERPRISE | 60 | 0.0500 | 0.0667 | 0.0617 | 0.0541 |
| hash | weighted total | 120 | 0.0917 | 0.2125 | 0.1449 | 0.1528 |

## bge-m3 Opt-in Result

Not run in this environment. `sentence_transformers` is not installed, so the real embedding path cannot load `BAAI/bge-m3`.

Observed dependency check:

```text
ModuleNotFoundError: No module named 'sentence_transformers'
```

Because the retriever has a fallback chain, running `--embedding-backend bge_m3` here would fall back to hash and would not be a valid real-model comparison. The bge-m3 column is intentionally left blank until the optional embedding extra and model cache are available.

## Saturation Notes

Recall@5 is not saturated after the semantic rewrite:

- BANK_ENTERPRISE: 0.0667
- BANK_CLEARING: 0.3583

Hit@1, MRR, and NDCG@5 remain the primary ranking-quality metrics for the follow-up bge-m3 run.

## Follow-up

Run the real comparison in an environment with the embedding extra and cached model:

```bash
uv sync --extra dev --extra embedding
uv run python -m scripts.eval_rag --embedding-backend bge_m3 --report reports/rag_eval_bge_m3.md --json-report reports/rag_eval_bge_m3_metrics.json
```
