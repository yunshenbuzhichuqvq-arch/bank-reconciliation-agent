# MVP-0 Reconciliation Rules

## Basic Matched Transaction

When `flow_id` exists on both bank-side and clearing-side files and the Decimal-normalized amount is equal, the row can be treated as automatically matched.

## Amount Mismatch

When `flow_id` exists on both sides but the Decimal-normalized amount differs, the discrepancy must be written to the error ledger. The difference must be calculated by deterministic Python code, not by an LLM.

## Single-Sided Transaction

When a row exists on only one side, create a reconciliation queue item and defer the audit decision to the simplified AuditAgent with RAG evidence.

## MVP-0 Audit Boundary

AuditAgent output must include evidence. If no evidence is found, confidence is insufficient, or required fields are missing, the item must remain pending for human review or manual handling in a later phase.

