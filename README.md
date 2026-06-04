# Bank Reconciliation Agent

MVP-0 backend skeleton for a multi-agent bank reconciliation and audit system.

The first development phase focuses on a backend-only loop:

1. Upload simulated Source A enterprise-book and Source B bank-statement Excel files.
2. Validate and clean rows with deterministic Python code.
3. Run basic reconciliation rules.
4. Send abnormal items through a simplified AuditAgent with RAG evidence.
5. Persist tasks, transactions, queues, ledger rows, and retrieval logs in MySQL.
6. Query task status and error ledger details through FastAPI.

This repository uses only simulated or desensitized data. It must not contain real customer data, real bank transactions, or internal bank documents.

## MVP-0 Structure

- `src/bank_reconciliation_agent/api`: FastAPI route layer.
- `src/bank_reconciliation_agent/services`: deterministic business orchestration.
- `src/bank_reconciliation_agent/agents`: simplified audit agent boundary.
- `src/bank_reconciliation_agent/rag`: rule retrieval boundary.
- `src/bank_reconciliation_agent/db/schema.sql`: MVP-0 MySQL schema.
- `mock_data`: simulated Source A/B Excel data.
- `rules`: Markdown rule documents for RAG indexing.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn bank_reconciliation_agent.main:app --reload
```

## MVP-0 Verification

MVP-0 is considered ready when the backend-only reconciliation loop can be
reproduced locally:

1. Prepare MySQL and create the MVP-0 tables.

```bash
mysql -uroot -p AI_agent < src/bank_reconciliation_agent/db/schema.sql
```

2. Configure the application DSN without committing secrets.

```bash
cat > .env <<'EOF'
MYSQL_DSN=mysql+pymysql://root:<password>@127.0.0.1:3306/AI_agent
EOF
```

3. Use the simulated Excel files in `mock_data`, or regenerate them.

```bash
uv run python -m scripts.generate_mock_excel
```

The fixed MVP-0 sample covers:

- normal matched transactions: 8 rows
- amount mismatch: `F1004`
- `BANK_UNARRIVED`: `F1005`
- `BOOK_UNRECORDED`: `F1006`

4. Start the API.

```bash
uv run uvicorn bank_reconciliation_agent.main:app --reload
```

5. Upload both Excel files and capture the returned `task_id`.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/reconcile/upload \
  -H 'X-User-ID: demo_user' \
  -F scenario_type=BANK_ENTERPRISE \
  -F source_a_file=@mock_data/source_a_enterprise_book.xlsx \
  -F source_b_file=@mock_data/source_b_bank_statement.xlsx
```

Expected MVP-0 statistics for the bundled sample:

- `scenario_type`: `BANK_ENTERPRISE`
- `total_source_a_rows`: 10
- `total_source_b_rows`: 10
- `auto_fixed_rows`: 8
- `pending_ai_rows`: 1
- `pending_human_rows`: 2

6. Query task status and ledger details.

```bash
curl http://127.0.0.1:8000/api/v1/reconcile/<task_id>/status \
  -H 'X-User-ID: demo_user'

curl 'http://127.0.0.1:8000/api/v1/ledger?task_id=<task_id>&scenario_type=BANK_ENTERPRISE' \
  -H 'X-User-ID: demo_user'
```

The ledger response should include `AMOUNT_MISMATCH`, `BANK_UNARRIVED`, and
`BOOK_UNRECORDED` items with AI audit opinions and RAG sources.

7. Verify MySQL persistence.

```sql
SELECT task_id, scenario_type, total_source_a_rows, total_source_b_rows, auto_fixed_rows,
       pending_ai_rows, pending_human_rows, unresolved_rows, status
FROM t_reconciliation_task
ORDER BY created_at DESC
LIMIT 1;

SELECT flow_id, error_type, status
FROM t_reconciliation_queue
WHERE task_id = '<task_id>'
ORDER BY flow_id;

SELECT flow_id, scenario_type, error_type, discrepancy_amount, handle_status, rag_source
FROM t_error_ledger
WHERE task_id = '<task_id>'
ORDER BY flow_id;

SELECT task_id, scenario_type, top_k, best_score, sources
FROM t_rag_retrieval_log
WHERE task_id = '<task_id>';
```

MVP-0 writes the task, Source A transactions, Source B transactions, exception queue,
error ledger, and RAG retrieval logs to MySQL.

8. Generate the local trace sample and run the RAG smoke evaluation.

```bash
uv run python -m scripts.dump_trace
uv run python -m scripts.eval_rag_smoke
```

`scripts.dump_trace` writes `local_traces/F1004.json` with the input exception,
RAG query and hits, AuditAgent output, and persisted ledger result. The smoke
eval uses `data/rag/smoke_eval.json` and exits non-zero if any query misses its
expected chunk prefix.

## Automated Checks

```bash
uv run pytest -q
uv run ruff check .
```
