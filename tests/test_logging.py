import json

import pandas as pd

from bank_reconciliation_agent.core.logging import bind_trace_context, configure_logging, log
from bank_reconciliation_agent.services.hooks import auth_hook, validation_hook
from bank_reconciliation_agent.services.task import TaskService


def test_logging_outputs_json_with_bound_trace_context(capsys) -> None:
    configure_logging()
    bind_trace_context(trace_id="trace-001", user_id="user-001", thread_id="thread-001")

    log.info("llm_call", agent_name="AuditAgent", step="decision", prompt_version="v1")

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["event"] == "llm_call"
    assert payload["trace_id"] == "trace-001"
    assert payload["user_id"] == "user-001"
    assert payload["thread_id"] == "thread-001"
    assert payload["agent_name"] == "AuditAgent"
    assert payload["step"] == "decision"
    assert payload["prompt_version"] == "v1"


def test_validation_hook_logs_structlog_event(capsys) -> None:
    configure_logging()
    bank_df = pd.DataFrame([{"flow_id": "F1", "amount": 1, "debit_amount": 0, "credit_amount": 1, "fee_amount": 0, "balance_after": 1, "bank_serial_no": "b", "accounting_date": "2026-06-10", "accounting_time": "10:00:00", "value_date": "2026-06-10", "self_account_no_masked": "x", "self_account_name_masked": "x", "self_bank_name": "x", "currency": "CNY", "transaction_type": "PAY", "transaction_direction": "IN", "trade_time": "2026-06-10 10:00:00", "account_no_masked": "x", "customer_name_masked": "x", "counterparty_account_no_masked": "x", "counterparty_name_masked": "x", "counterparty_bank_name": "x", "channel": "x", "summary": "x", "purpose": "x", "posting_status": "x", "branch_no": "x", "teller_id": "x", "transaction_code": "x", "source_system": "x", "remark": "x"}])
    clear_df = pd.DataFrame([{"flow_id": "F1", "amount": 1, "transaction_amount": 1, "fee_amount": 0, "net_amount": 1, "clearing_serial_no": "c", "merchant_id": "m", "merchant_name": "m", "store_name": "s", "terminal_id": "t", "channel": "x", "transaction_type": "PAY", "trade_date": "2026-06-10", "trade_time": "10:00:00", "settlement_date": "2026-06-10", "currency": "CNY", "status": "OK", "summary": "x", "batch_no": "x", "voucher_no": "x", "reference_no": "x", "merchant_order_no": "x", "payer_account_no_masked": "x", "payer_name_masked": "x", "payee_account_no_masked": "x", "payee_name_masked": "x", "order_description": "x", "remark": "x"}])

    validation_hook(bank_df, clear_df, scenario_type="BANK_ENTERPRISE")

    payload = json.loads(capsys.readouterr().out)
    assert payload["event"] == "validation_hook_passed"
    assert payload["hook_name"] == "ValidationHook"


def test_auth_hook_logs_structlog_event(capsys) -> None:
    configure_logging()
    TaskService().replace_task(
        user_id="hook_user",
        task_id="TASK_HOOK",
        scenario_type="BANK_ENTERPRISE",
        total_bank_rows=1,
        total_clear_rows=1,
        auto_fixed_rows=0,
        pending_ai_rows=0,
        pending_human_rows=1,
    )

    auth_hook(user_id="hook_user", task_id="TASK_HOOK")

    payload = json.loads(capsys.readouterr().out)
    assert payload["event"] == "auth_hook_passed"
    assert payload["hook_name"] == "AuthHook"
