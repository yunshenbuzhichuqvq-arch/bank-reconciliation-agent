#!/usr/bin/env python3
"""External HTTP/SSE black-box smoke client demonstrating reproducible delivery.

ARQ path:
  readiness → auth → async_upload(force=true) → queue_completion →
  exceptions → review → report

SSE path:
  sync_upload → sse_terminal (start-live → events → status → report)

Outputs a machine-readable v1.0 summary JSON on stdout and to the specified file.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("smoke_demo")

STEP_NAMES: list[str] = [
    "readiness",
    "auth",
    "async_upload",
    "queue_completion",
    "exceptions",
    "review",
    "report",
    "sync_upload",
    "sse_terminal",
]

DEFAULT_DEMO_PASSWORD = "demo12345"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_REQUEST_TIMEOUT = 30
DEFAULT_TASK_TIMEOUT = 180
POLL_INTERVAL_SECONDS = 1.0

ARQ_BANK_FILE = "mock_data/mvp1_bank.xlsx"
ARQ_CLEAR_FILE = "mock_data/mvp1_clear.xlsx"
SSE_BANK_FILE = "mock_data/mvp2a3_core.xlsx"
SSE_CLEAR_FILE = "mock_data/mvp2a3_clearing.xlsx"

REPO_ROOT = Path(__file__).resolve().parent.parent

_SENSITIVE_PATTERNS: list[str] = [
    "Authorization",
    "Bearer ",
    "access_token",
    "mysql+pymysql://",
    "redis://",
    "DEEPSEEK_API_KEY",
]

_SUMMARY_SCHEMA_VERSION = "1.0"


def _build_summary() -> dict[str, Any]:
    return {
        "schema_version": _SUMMARY_SCHEMA_VERSION,
        "success": True,
        "boundary": {
            "llm_provider": "fake",
            "embedding_backend": "hash",
            "external_credentials_required": False,
        },
        "task_ids": {"async": None, "sse": None},
        "steps": [],
        "failure_step": None,
    }


def _redact_text(text: str) -> str:
    for pattern in _SENSITIVE_PATTERNS:
        text = text.replace(pattern, "[REDACTED]")
    return text


def _extract_data(response: httpx.Response, step_name: str) -> Any:
    try:
        body = response.json()
    except Exception:
        raise RuntimeError(f"{step_name}: invalid JSON response")
    data = body.get("data")
    if data is None:
        raise RuntimeError(f"{step_name}: ApiResponse.data missing")
    return data


def _check_health(base_url: str, client: httpx.Client, timeout: int) -> dict:
    resp = client.get(f"{base_url}/health", timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"readiness: HTTP {resp.status_code}")
    body = resp.json()
    if body.get("status") != "ok" or body.get("db") != "ok":
        raise RuntimeError(f"readiness: status={body.get('status')}, db={body.get('db')}")
    return body


def _authenticate(base_url: str, client: httpx.Client, timeout: int) -> str:
    password = os.environ.get("DEMO_USER_PASSWORD", DEFAULT_DEMO_PASSWORD)
    resp = client.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": "demo_user", "password": password},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"auth: HTTP {resp.status_code}")
    data = _extract_data(resp, "auth")
    token = data.get("access_token")
    if not token:
        raise RuntimeError("auth: no access_token in response")
    return token


def _async_upload(
    base_url: str, client: httpx.Client, token: str, timeout: int
) -> tuple[str, str]:
    bank_path = REPO_ROOT / ARQ_BANK_FILE
    clear_path = REPO_ROOT / ARQ_CLEAR_FILE
    with open(bank_path, "rb") as bf, open(clear_path, "rb") as cf:
        resp = client.post(
            f"{base_url}/api/v1/reconcile/upload-async",
            files={"bank_file": (bank_path.name, bf), "clear_file": (clear_path.name, cf)},
            data={"scenario_type": "BANK_ENTERPRISE", "force": "true"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"async_upload: HTTP {resp.status_code}")
    data = _extract_data(resp, "async_upload")
    task_id = data.get("task_id")
    if not task_id:
        raise RuntimeError("async_upload: no task_id in response")
    status = data.get("status", "")
    if status != "QUEUED":
        raise RuntimeError(
            f"async_upload: expected QUEUED but got {status} (bypassed worker)"
        )
    return task_id, status


def _poll_until_terminal(
    base_url: str, client: httpx.Client, token: str, task_id: str, timeout: int
) -> str:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        resp = client.get(
            f"{base_url}/api/v1/reconcile/{task_id}/status",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"queue_completion: HTTP {resp.status_code}")
        data = _extract_data(resp, "queue_completion")
        status = data.get("status", "")
        if status in ("UPLOADED", "COMPLETED"):
            return status
        if status == "FAILED":
            raise RuntimeError("queue_completion: task FAILED")
        if status not in ("QUEUED", "RUNNING"):
            raise RuntimeError(f"queue_completion: unknown status {status}")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"queue_completion: timeout after {timeout}s")


def _check_exceptions(
    base_url: str, client: httpx.Client, token: str, task_id: str, timeout: int
) -> int:
    resp = client.get(
        f"{base_url}/api/v1/reconcile/{task_id}/exceptions",
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"exceptions: HTTP {resp.status_code}")
    data = _extract_data(resp, "exceptions")
    total = data.get("total", 0)
    return total


def _get_pending_review(
    base_url: str, client: httpx.Client, token: str, task_id: str, timeout: int
) -> list[dict]:
    resp = client.get(
        f"{base_url}/api/v1/review/pending",
        params={"task_id": task_id},
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"review: HTTP {resp.status_code}")
    data = _extract_data(resp, "review")
    items = data.get("items", [])
    total = data.get("total", 0)
    if total == 0 or not items:
        raise RuntimeError("review: no pending review items")
    return items


def _approve_first(
    base_url: str,
    client: httpx.Client,
    token: str,
    queue_id: int,
    timeout: int,
) -> None:
    resp = client.post(
        f"{base_url}/api/v1/review/{queue_id}/approve",
        json={
            "action": "APPROVED_MATCH",
            "handler_username": "demo_user",
            "remark": "smoke automated approval",
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"review: approve HTTP {resp.status_code}")
    _extract_data(resp, "review")


def _get_report(
    base_url: str, client: httpx.Client, token: str, task_id: str, timeout: int
) -> dict:
    resp = client.get(
        f"{base_url}/api/v1/reconcile/{task_id}/report",
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"report: HTTP {resp.status_code}")
    data = _extract_data(resp, "report")
    return data


def _sync_upload(
    base_url: str, client: httpx.Client, token: str, timeout: int
) -> str:
    bank_path = REPO_ROOT / SSE_BANK_FILE
    clear_path = REPO_ROOT / SSE_CLEAR_FILE
    with open(bank_path, "rb") as bf, open(clear_path, "rb") as cf:
        resp = client.post(
            f"{base_url}/api/v1/reconcile/upload",
            files={"bank_file": (bank_path.name, bf), "clear_file": (clear_path.name, cf)},
            data={"scenario_type": "BANK_CLEARING"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"sync_upload: HTTP {resp.status_code}")
    data = _extract_data(resp, "sync_upload")
    task_id = data.get("task_id")
    if not task_id:
        raise RuntimeError("sync_upload: no task_id in response")
    return task_id


def _sse_terminal(
    base_url: str,
    client: httpx.Client,
    token: str,
    task_id: str,
    request_timeout: int,
    task_timeout: int,
) -> None:
    start_live_resp = client.post(
        f"{base_url}/api/v1/reconcile/{task_id}/start-live",
        headers={"Authorization": f"Bearer {token}"},
        timeout=request_timeout,
    )
    if start_live_resp.status_code != 200:
        raise RuntimeError(f"sse_terminal: start-live HTTP {start_live_resp.status_code}")

    events_url = f"{base_url}/api/v1/reconcile/{task_id}/events"
    sse_start = time.monotonic()
    got_task_done = False
    sse_task_id = task_id
    final_status = None

    with client.stream(
        "GET",
        events_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=request_timeout,
    ) as response:
        if response.status_code != 200:
            raise RuntimeError(f"sse_terminal: events HTTP {response.status_code}")
        for line in response.iter_lines():
            if time.monotonic() - sse_start > task_timeout:
                raise RuntimeError("sse_terminal: timeout")
            if not line.startswith("data:"):
                continue
            data_part = line[len("data:"):].strip()
            if not data_part:
                continue
            try:
                frame = json.loads(data_part)
            except json.JSONDecodeError:
                raise RuntimeError("sse_terminal: invalid SSE data frame")
            event_type = frame.get("event_type", "")
            sse_task_id = frame.get("task_id", sse_task_id)
            if event_type == "TASK_DONE":
                payload = frame.get("payload", {})
                final_status = payload.get("status", "")
                if final_status != "COMPLETED":
                    raise RuntimeError(f"sse_terminal: TASK_DONE status={final_status}")
                got_task_done = True
                break

    if not got_task_done:
        raise RuntimeError("sse_terminal: stream ended without TASK_DONE")

    status_resp = client.get(
        f"{base_url}/api/v1/reconcile/{sse_task_id}/status",
        headers={"Authorization": f"Bearer {token}"},
        timeout=request_timeout,
    )
    if status_resp.status_code != 200:
        raise RuntimeError(f"sse_terminal: status HTTP {status_resp.status_code}")
    _extract_data(status_resp, "sse_terminal")

    report_resp = client.get(
        f"{base_url}/api/v1/reconcile/{sse_task_id}/report",
        headers={"Authorization": f"Bearer {token}"},
        timeout=request_timeout,
    )
    if report_resp.status_code != 200:
        raise RuntimeError(f"sse_terminal: report HTTP {report_resp.status_code}")
    _extract_data(report_resp, "sse_terminal")


def _add_step(
    summary: dict,
    name: str,
    outcome: str,
    duration_ms: float,
    error_type: str | None = None,
    message: str | None = None,
) -> None:
    step: dict[str, Any] = {
        "name": name,
        "outcome": outcome,
        "duration_ms": round(duration_ms),
    }
    if error_type:
        step["error_type"] = error_type
    if message:
        step["message"] = _redact_text(message)
    summary["steps"].append(step)


def _fail_summary(
    summary: dict, step_name: str, error_msg: str
) -> dict:
    summary["success"] = False
    summary["failure_step"] = step_name
    summary["steps"][-1]["outcome"] = "failed"
    summary["steps"][-1]["error_type"] = "SMOKE_ERROR"
    summary["steps"][-1]["message"] = _redact_text(error_msg)
    return summary


def run_smoke(
    *,
    base_url: str = DEFAULT_BASE_URL,
    summary_json: str,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    task_timeout: int = DEFAULT_TASK_TIMEOUT,
    client: httpx.Client | None = None,
) -> int:
    if client is None:
        client = httpx.Client(timeout=httpx.Timeout(request_timeout))

    summary = _build_summary()
    token: str | None = None
    async_task_id: str | None = None
    sse_task_id: str | None = None

    def _run_step(name: str, fn):
        nonlocal token, async_task_id, sse_task_id, summary
        t0 = time.monotonic()
        try:
            if name == "readiness":
                _check_health(base_url, client, request_timeout)
            elif name == "auth":
                token = _authenticate(base_url, client, request_timeout)
            elif name == "async_upload":
                async_task_id, _ = _async_upload(base_url, client, token, request_timeout)
                summary["task_ids"]["async"] = async_task_id
            elif name == "queue_completion":
                _poll_until_terminal(base_url, client, token, async_task_id, task_timeout)
            elif name == "exceptions":
                _check_exceptions(base_url, client, token, async_task_id, request_timeout)
            elif name == "review":
                items = _get_pending_review(base_url, client, token, async_task_id, request_timeout)
                _approve_first(base_url, client, token, items[0]["queue_id"], request_timeout)
            elif name == "report":
                _get_report(base_url, client, token, async_task_id, request_timeout)
            elif name == "sync_upload":
                sse_task_id = _sync_upload(base_url, client, token, request_timeout)
                summary["task_ids"]["sse"] = sse_task_id
            elif name == "sse_terminal":
                _sse_terminal(base_url, client, token, sse_task_id, request_timeout, task_timeout)
                status_resp = client.get(
                    f"{base_url}/api/v1/reconcile/{sse_task_id}/status",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=request_timeout,
                )
                if status_resp.status_code != 200:
                    raise RuntimeError(f"sse_terminal: status HTTP {status_resp.status_code}")
                report_resp = client.get(
                    f"{base_url}/api/v1/reconcile/{sse_task_id}/report",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=request_timeout,
                )
                if report_resp.status_code != 200:
                    raise RuntimeError(f"sse_terminal: report HTTP {report_resp.status_code}")
            else:
                return
            duration_ms = (time.monotonic() - t0) * 1000
            _add_step(summary, name, "passed", duration_ms)
            return
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            err_msg = str(exc)
            _add_step(summary, name, "passed", duration_ms)
            summary = _fail_summary(summary, name, err_msg)
            raise _SmokeAbort()

    try:
        for step_name in STEP_NAMES:
            _run_step(step_name, None)
    except _SmokeAbort:
        pass

    export_summary = json.dumps(summary, ensure_ascii=False, indent=2, default=str)

    try:
        out_path = Path(summary_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(export_summary, encoding="utf-8")
    except OSError as exc:
        logger.error("failed to write summary: %s", exc)
        print(export_summary)
        return 1, summary

    print(export_summary)
    return (0 if summary["success"] else 1), summary


class _SmokeAbort(Exception):
    pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproducible delivery smoke demo")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Backend API base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--summary-json",
        default="artifacts/smoke-summary.json",
        help="Output path for machine-readable summary JSON",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=int,
        default=DEFAULT_REQUEST_TIMEOUT,
        help="Per-request HTTP timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--task-timeout-seconds",
        type=int,
        default=DEFAULT_TASK_TIMEOUT,
        help="Total timeout for ARQ polling / SSE in seconds (default: %(default)s)",
    )
    args = parser.parse_args()

    if args.request_timeout_seconds <= 0:
        parser.error("--request-timeout-seconds must be positive")
    if args.task_timeout_seconds <= 0:
        parser.error("--task-timeout-seconds must be positive")

    exit_code, _summary = run_smoke(
        base_url=args.base_url.rstrip("/"),
        summary_json=args.summary_json,
        request_timeout=args.request_timeout_seconds,
        task_timeout=args.task_timeout_seconds,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
