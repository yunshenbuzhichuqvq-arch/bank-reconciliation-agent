# Bank Reconciliation Agent

MVP-0 backend skeleton for a multi-agent bank reconciliation and audit system.

The first development phase focuses on a backend-only loop:

1. Upload simulated bank-side and clearing-side Excel files.
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
- `mock_data`: simulated Excel data notes and future sample files.
- `rules`: Markdown rule documents for RAG indexing.

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn bank_reconciliation_agent.main:app --reload
```

Current scaffold verification without third-party dependencies:

```bash
python -m unittest tests.test_project_skeleton -v
python -m compileall src
```

