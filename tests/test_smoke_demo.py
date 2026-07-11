from __future__ import annotations

import json
import os
from pathlib import Path

import httpx


def _signup_response(username: str = "demo_user") -> dict:
    return {
        "code": 200,
        "message": "success",
        "data": {
            "access_token": "fake-jwt-token",
            "token_type": "bearer",
            "username": username,
        },
    }


def _health_ok() -> dict:
    return {"status": "ok", "service": "test", "db": "ok"}


def _health_degraded() -> dict:
    return {"status": "degraded", "service": "test", "db": "unavailable"}


def _async_upload_response(task_id: str, status: str = "QUEUED") -> dict:
    return {
        "code": 200,
        "message": "upload queued",
        "data": {
            "task_id": task_id,
            "status": status,
            "total_bank_rows": 100,
            "total_clear_rows": 100,
            "auto_fixed_rows": 10,
            "pending_ai_rows": 5,
            "pending_human_rows": 3,
        },
    }


def _status_response(task_id: str, status: str) -> dict:
    return {
        "code": 200,
        "data": {
            "task_id": task_id,
            "status": status,
            "auto_fixed_rows": 10,
            "pending_ai_rows": 5,
            "ai_processed_rows": 3,
            "pending_human_rows": 2,
            "unresolved_rows": 0,
        },
    }


def _exceptions_response(task_id: str, total: int = 1) -> dict:
    return {
        "code": 200,
        "data": {
            "task_id": task_id,
            "total": total,
            "items": [
                {
                    "flow_id": "FLOW-001",
                    "status": "PENDING_HUMAN",
                    "error_type": "AMOUNT_MISMATCH",
                    "exception_branch": "STATUS_CHECK",
                    "bank_amount": "100.00",
                    "clear_amount": "80.00",
                    "amount_diff": "20.00",
                    "rag_evidence": [],
                    "audit_decision": {
                        "flow_id": "FLOW-001",
                        "decision": "HOLD",
                        "risk_level": "HIGH",
                        "reason": "amount mismatch",
                        "evidence": [],
                        "confidence": 0.95,
                    },
                }
            ],
        },
    }


def _pending_response(task_id: str, queue_id: int = 1, total: int = 1) -> dict:
    return {
        "code": 200,
        "data": {
            "scenario_type": "BANK_ENTERPRISE",
            "total": total,
            "items": [
                {
                    "queue_id": queue_id,
                    "error_type": "AMOUNT_MISMATCH",
                    "exception_branch": "STATUS_CHECK",
                    "risk_level": "HIGH",
                    "ai_suggestion": "HOLD",
                    "ai_confidence": 0.95,
                    "ai_reason": "amount mismatch",
                    "rag_sources": [],
                    "similar_historical_cases": 0,
                    "historical_approve_rate": "0%",
                }
            ],
        },
    }


def _approve_response(queue_id: int) -> dict:
    return {
        "code": 200,
        "data": {"queue_id": queue_id, "current_status": "APPROVED_MATCH"},
    }


def _report_response(task_id: str) -> dict:
    return {
        "code": 200,
        "data": {
            "task_id": task_id,
            "generated_at": "2026-01-01T00:00:00",
            "llm_used": False,
            "metrics": {},
            "narrative": {},
            "markdown": "# Report",
        },
    }


def _build_sse_frame(event_type: str, task_id: str, status: str = "COMPLETED") -> str:
    payload = {
        "schema_version": "1.1",
        "event_type": event_type,
        "seq": 1,
        "task_id": task_id,
        "ts": "2026-01-01T00:00:00",
        "payload": {"status": status},
    }
    return f"data: {json.dumps(payload)}\n\n"


def _build_bad_sse_frame() -> str:
    return "data: not-json\n\n"


# ---------------------------------------------------------------------------
# Step order & success path tests
# ---------------------------------------------------------------------------


class TestStepOrder:
    def test_success_path_step_order_matches_spec(self) -> None:
        from scripts.smoke_demo import STEP_NAMES

        expected = [
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
        assert STEP_NAMES == expected, f"STEP_NAMES mismatch: {STEP_NAMES}"

    def test_summary_schema_fields(self) -> None:
        from scripts.smoke_demo import _build_summary

        summary = _build_summary()
        assert "schema_version" in summary
        assert summary["schema_version"] == "1.0"
        assert "success" in summary
        assert "boundary" in summary
        assert "task_ids" in summary
        assert "steps" in summary
        assert "failure_step" in summary
        assert summary["boundary"]["llm_provider"] == "fake"
        assert summary["boundary"]["embedding_backend"] == "hash"
        assert summary["boundary"]["external_credentials_required"] is False


# ---------------------------------------------------------------------------
# HTTP handler seam tests
# ---------------------------------------------------------------------------


def _mock_transport_handler(
    task_id_async: str = "task-async-001", task_id_sse: str = "task-sse-001"
):
    poll_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)

        if "/health" in url:
            return httpx.Response(200, json=_health_ok())

        if "/api/v1/auth/login" in url:
            return httpx.Response(200, json=_signup_response())

        if "/api/v1/reconcile/upload-async" in url:
            assert request.headers.get("authorization") == "Bearer fake-jwt-token", (
                "upload-async must carry Bearer token"
            )
            return httpx.Response(200, json=_async_upload_response(task_id_async))

        if "/upload" in url and request.method == "POST":
            assert request.headers.get("authorization") == "Bearer fake-jwt-token", (
                "upload must carry Bearer token"
            )
            return httpx.Response(
                200,
                json=_async_upload_response(task_id_sse, "UPLOADED"),
            )

        if "/start-live" in url:
            assert request.headers.get("authorization") == "Bearer fake-jwt-token"
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {"task_id": task_id_sse, "status": "AI_RUNNING"},
                },
            )

        if "/events" in url:
            assert request.headers.get("authorization") == "Bearer fake-jwt-token"
            sse_body = (
                'data: {"event_type": "task_progress", "seq": 0, "task_id": "'
                + task_id_sse
                + '", "payload": {}}\n\n'
                + _build_sse_frame("TASK_DONE", task_id_sse, "COMPLETED")
            )
            return httpx.Response(
                200,
                content=sse_body.encode(),
                headers={"content-type": "text/event-stream"},
            )

        if "/status" in url:
            if task_id_sse and task_id_sse in url:
                return httpx.Response(200, json=_status_response(task_id_sse, "COMPLETED"))
            poll_count[0] += 1
            if poll_count[0] <= 2:
                status = "RUNNING" if poll_count[0] == 1 else "QUEUED"
            else:
                status = "UPLOADED"
            return httpx.Response(200, json=_status_response(task_id_async, status))

        if "/exceptions" in url:
            return httpx.Response(200, json=_exceptions_response(task_id_async, 1))

        if "/review/pending" in url:
            return httpx.Response(200, json=_pending_response(task_id_async, 1, 1))

        if "/approve" in url:
            return httpx.Response(200, json=_approve_response(1))

        if "/report" in url:
            if task_id_sse and task_id_sse in url:
                return httpx.Response(200, json=_report_response(task_id_sse))
            return httpx.Response(200, json=_report_response(task_id_async))

        return httpx.Response(404, json={"code": 404, "message": "not found"})

    return handler


def _run_smoke_with_mock(tmp_path: Path, **overrides) -> tuple[int, dict]:
    from scripts.smoke_demo import run_smoke

    summary_file = tmp_path / "summary.json"
    handler = _mock_transport_handler(**overrides)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    exit_code, summary = run_smoke(
        base_url="http://test:8000",
        summary_json=str(summary_file),
        request_timeout=30,
        task_timeout=60,
        client=client,
    )
    return exit_code, summary


class TestSmokeSuccess:
    def test_successful_smoke_exit_zero(self, tmp_path: Path) -> None:
        exit_code, summary = _run_smoke_with_mock(tmp_path)
        assert exit_code == 0
        assert summary["success"] is True
        assert summary["failure_step"] is None

    def test_success_summary_has_nine_steps(self, tmp_path: Path) -> None:
        _, summary = _run_smoke_with_mock(tmp_path)
        assert len(summary["steps"]) == 9

    def test_each_step_has_required_fields(self, tmp_path: Path) -> None:
        _, summary = _run_smoke_with_mock(tmp_path)
        for step in summary["steps"]:
            assert step["outcome"] in ("passed", "failed")
            assert isinstance(step["duration_ms"], (int, float))
            assert step["duration_ms"] >= 0

    def test_task_ids_present(self, tmp_path: Path) -> None:
        _, summary = _run_smoke_with_mock(tmp_path)
        assert summary["task_ids"]["async"] == "task-async-001"
        assert summary["task_ids"]["sse"] == "task-sse-001"

    def test_boundary_fields(self, tmp_path: Path) -> None:
        _, summary = _run_smoke_with_mock(tmp_path)
        assert summary["boundary"] == {
            "llm_provider": "fake",
            "embedding_backend": "hash",
            "external_credentials_required": False,
        }


class TestAuthAndHeaders:
    def test_auth_uses_bearer_token(self) -> None:
        requests_sent = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_sent.append(request)
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "/api/v1/reconcile/upload-async" in url:
                return httpx.Response(200, json=_async_upload_response("tid-1"))
            if "/status" in url:
                if "tsse-1" in url:
                    return httpx.Response(200, json=_status_response("tsse-1", "COMPLETED"))
                return httpx.Response(200, json=_status_response("tid-1", "UPLOADED"))
            if "/exceptions" in url:
                return httpx.Response(200, json=_exceptions_response("tid-1", 1))
            if "/review/pending" in url:
                return httpx.Response(200, json=_pending_response("tid-1", 1, 1))
            if "/approve" in url:
                return httpx.Response(200, json=_approve_response(1))
            if "/report" in url:
                if "tsse-1" in url:
                    return httpx.Response(200, json=_report_response("tsse-1"))
                return httpx.Response(200, json=_report_response("tid-1"))
            if "/upload" in url:
                return httpx.Response(200, json=_async_upload_response("tsse-1", "UPLOADED"))
            if "/start-live" in url:
                return httpx.Response(200, json={"code": 200, "data": {"task_id": "tsse-1", "status": "AI_RUNNING"}})
            if "/events" in url:
                return httpx.Response(200, content=_build_sse_frame("TASK_DONE", "tsse-1", "COMPLETED").encode(),
                                      headers={"content-type": "text/event-stream"})
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, _ = run_smoke(
            base_url="http://test:8000",
            summary_json="/dev/null",
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code == 0
        business_requests = [
            r for r in requests_sent
            if "/health" not in str(r.url) and "/auth/login" not in str(r.url)
        ]
        for req in business_requests:
            assert req.headers.get("authorization") == "Bearer fake-jwt-token", (
                f"Missing Bearer token on {req.method} {req.url}"
            )


class TestArqForceRequeue:
    def test_smoke_sends_force_true(self) -> None:
        upload_calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                upload_calls.append(request)
                return httpx.Response(200, json=_async_upload_response("tid-force"))
            if "/status" in url:
                if "tsse-f" in url:
                    return httpx.Response(200, json=_status_response("tsse-f", "COMPLETED"))
                return httpx.Response(200, json=_status_response("tid-force", "UPLOADED"))
            if "/exceptions" in url:
                return httpx.Response(200, json=_exceptions_response("tid-force", 1))
            if "/review/pending" in url:
                return httpx.Response(200, json=_pending_response("tid-force", 1, 1))
            if "/approve" in url:
                return httpx.Response(200, json=_approve_response(1))
            if "/report" in url:
                if "tsse-f" in url:
                    return httpx.Response(200, json=_report_response("tsse-f"))
                return httpx.Response(200, json=_report_response("tid-force"))
            if "/upload" in url:
                return httpx.Response(200, json=_async_upload_response("tsse-f", "UPLOADED"))
            if "/start-live" in url:
                return httpx.Response(200, json={"code": 200, "data": {"task_id": "tsse-f", "status": "AI_RUNNING"}})
            if "/events" in url:
                return httpx.Response(200, content=_build_sse_frame("TASK_DONE", "tsse-f", "COMPLETED").encode(),
                                      headers={"content-type": "text/event-stream"})
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, _ = run_smoke(
            base_url="http://test:8000",
            summary_json="/dev/null",
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code == 0
        assert len(upload_calls) == 1
        content = upload_calls[0].content
        found_force = b'name="force"' in content and content.split(b'name="force"')[1][:100].find(b"true") != -1
        assert found_force, "async upload must send force=true"

    def test_smoke_fails_if_async_upload_skips_queued(self, tmp_path: Path) -> None:
        handler = _mock_transport_handler()

        def handler_skip(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "upload-async" in url:
                return httpx.Response(200, json=_async_upload_response("tid-skip", "UPLOADED"))
            return handler(request)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler_skip))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["success"] is False
        assert summary["failure_step"] == "async_upload"


class TestFailures:
    def test_readiness_failure(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"detail": "unavailable"})

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["success"] is False
        assert summary["failure_step"] == "readiness"

    def test_auth_failure(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(401, json={"code": 401, "message": "invalid"})
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["failure_step"] == "auth"

    def test_missing_api_response_data_fails(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                return httpx.Response(200, json={"code": 500, "message": "error"})
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["failure_step"] == "async_upload"

    def test_polling_failed_status_fails(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                return httpx.Response(200, json=_async_upload_response("tid-fail"))
            if "/status" in url:
                return httpx.Response(200, json=_status_response("tid-fail", "FAILED"))
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["failure_step"] == "queue_completion"


class TestSSEPath:
    def test_sse_success_path(self, tmp_path: Path) -> None:
        from scripts.smoke_demo import run_smoke

        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(_mock_transport_handler()))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code == 0
        sse_step = summary["steps"][8]
        assert sse_step["name"] == "sse_terminal"
        assert sse_step["outcome"] == "passed"

    def test_sse_bad_json_fails(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                return httpx.Response(200, json=_async_upload_response("tid-a"))
            if "/status" in url:
                return httpx.Response(200, json=_status_response("tid-a", "UPLOADED"))
            if "/exceptions" in url:
                return httpx.Response(200, json=_exceptions_response("tid-a", 1))
            if "/review/pending" in url:
                return httpx.Response(200, json=_pending_response("tid-a", 1, 1))
            if "/approve" in url:
                return httpx.Response(200, json=_approve_response(1))
            if "/report" in url:
                return httpx.Response(200, json=_report_response("tid-a"))
            if "/upload" in url:
                return httpx.Response(200, json=_async_upload_response("tsse-b", "UPLOADED"))
            if "/start-live" in url:
                return httpx.Response(200, json={"code": 200, "data": {"task_id": "tsse-b", "status": "AI_RUNNING"}})
            if "/events" in url:
                return httpx.Response(
                    200,
                    content=_build_bad_sse_frame().encode(),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["failure_step"] == "sse_terminal"

    def test_sse_failed_termination(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                return httpx.Response(200, json=_async_upload_response("tid-a"))
            if "/status" in url:
                return httpx.Response(200, json=_status_response("tid-a", "UPLOADED"))
            if "/exceptions" in url:
                return httpx.Response(200, json=_exceptions_response("tid-a", 1))
            if "/review/pending" in url:
                return httpx.Response(200, json=_pending_response("tid-a", 1, 1))
            if "/approve" in url:
                return httpx.Response(200, json=_approve_response(1))
            if "/report" in url:
                return httpx.Response(200, json=_report_response("tid-a"))
            if "/upload" in url:
                return httpx.Response(200, json=_async_upload_response("tsse-fail", "UPLOADED"))
            if "/start-live" in url:
                return httpx.Response(200, json={"code": 200, "data": {"task_id": "tsse-fail", "status": "AI_RUNNING"}})
            if "/events" in url:
                return httpx.Response(
                    200,
                    content=_build_sse_frame("TASK_DONE", "tsse-fail", "FAILED").encode(),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["failure_step"] == "sse_terminal"


class TestRedaction:
    def test_summary_does_not_contain_sensitive_data(self, tmp_path: Path) -> None:
        _, summary = _run_smoke_with_mock(tmp_path)
        text = json.dumps(summary)
        assert "fake-jwt-token" not in text
        assert "Bearer" not in text
        assert "Authorization" not in text
        assert "mysql+pymysql" not in text
        assert "demo_root_pw" not in text

    def test_summary_redacts_dsn_userinfo(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise RuntimeError(
                "db unavailable: mysql+pymysql://root:secret123@mysql:3306/AI_agent"
            )

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        text = json.dumps(summary)
        assert "secret123" not in text
        assert "root" not in text
        assert "mysql:3306" not in text

    def test_summary_redacts_redis_dsn(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                raise RuntimeError("login failed: redis://redis:6379/0 connection refused")
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        text = json.dumps(summary)
        assert "redis://" not in text

    def test_summary_redacts_dynamic_password(self, tmp_path: Path) -> None:
        old_pw = os.environ.get("DEMO_USER_PASSWORD")
        os.environ["DEMO_USER_PASSWORD"] = "secret-dynamic-pw"
        try:
            def handler(request: httpx.Request) -> httpx.Response:
                url = str(request.url)
                if "/health" in url:
                    return httpx.Response(200, json=_health_ok())
                if "/api/v1/auth/login" in url:
                    raise RuntimeError("auth: backend error")
                return httpx.Response(404)

            from scripts.smoke_demo import run_smoke
            summary_file = tmp_path / "summary.json"
            client = httpx.Client(transport=httpx.MockTransport(handler))
            exit_code, summary = run_smoke(
                base_url="http://test:8000",
                summary_json=str(summary_file),
                request_timeout=30,
                task_timeout=60,
                client=client,
            )
            assert exit_code != 0
            text = json.dumps(summary)
            assert "secret-dynamic-pw" not in text
        finally:
            if old_pw is not None:
                os.environ["DEMO_USER_PASSWORD"] = old_pw
            else:
                os.environ.pop("DEMO_USER_PASSWORD", None)


class TestSecondRun:
    def test_two_runs_both_use_force(self, tmp_path: Path) -> None:
        from scripts.smoke_demo import run_smoke

        upload_calls = [0]

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                upload_calls[0] += 1
                return httpx.Response(200, json=_async_upload_response(f"tid-run{upload_calls[0]}"))
            if "/status" in url:
                if "tsse-run" in url:
                    return httpx.Response(200, json=_status_response(f"tsse-run{upload_calls[0]}", "COMPLETED"))
                return httpx.Response(200, json=_status_response(f"tid-run{upload_calls[0]}", "UPLOADED"))
            if "/exceptions" in url:
                return httpx.Response(200, json=_exceptions_response(f"tid-run{upload_calls[0]}", 1))
            if "/review/pending" in url:
                return httpx.Response(200, json=_pending_response(f"tid-run{upload_calls[0]}", 1, 1))
            if "/approve" in url:
                return httpx.Response(200, json=_approve_response(1))
            if "/report" in url:
                if "tsse-run" in url:
                    return httpx.Response(200, json=_report_response(f"tsse-run{upload_calls[0]}"))
                return httpx.Response(200, json=_report_response(f"tid-run{upload_calls[0]}"))
            if "/upload" in url:
                return httpx.Response(200, json=_async_upload_response(f"tsse-run{upload_calls[0]}", "UPLOADED"))
            if "/start-live" in url:
                return httpx.Response(200, json={"code": 200, "data": {"task_id": f"tsse-run{upload_calls[0]}", "status": "AI_RUNNING"}})
            if "/events" in url:
                return httpx.Response(200, content=_build_sse_frame("TASK_DONE", f"tsse-run{upload_calls[0]}", "COMPLETED").encode(),
                                      headers={"content-type": "text/event-stream"})
            return httpx.Response(404)

        client = httpx.Client(transport=httpx.MockTransport(handler))

        exit1, _ = run_smoke(
            base_url="http://test:8000",
            summary_json=str(tmp_path / "run1.json"),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit1 == 0
        assert upload_calls[0] == 1

        exit2, _ = run_smoke(
            base_url="http://test:8000",
            summary_json=str(tmp_path / "run2.json"),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit2 == 0
        assert upload_calls[0] == 2, "Second run must trigger a new async upload"


class TestTimeout:
    def test_truncated_sse_times_out(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                return httpx.Response(200, json=_async_upload_response("tid-a"))
            if "/status" in url:
                return httpx.Response(200, json=_status_response("tid-a", "UPLOADED"))
            if "/exceptions" in url:
                return httpx.Response(200, json=_exceptions_response("tid-a", 1))
            if "/review/pending" in url:
                return httpx.Response(200, json=_pending_response("tid-a", 1, 1))
            if "/approve" in url:
                return httpx.Response(200, json=_approve_response(1))
            if "/report" in url:
                return httpx.Response(200, json=_report_response("tid-a"))
            if "/upload" in url:
                return httpx.Response(200, json=_async_upload_response("tsse-p", "UPLOADED"))
            if "/start-live" in url:
                return httpx.Response(200, json={"code": 200, "data": {"task_id": "tsse-p", "status": "AI_RUNNING"}})
            if "/events" in url:
                return httpx.Response(
                    200,
                    content='data: {"event_type": "task_progress", "seq": 0, "task_id": "tsse-p", "payload": {}}\n\n'.encode(),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=1,
            client=client,
        )
        assert exit_code != 0
        assert summary["failure_step"] == "sse_terminal"


# ---------------------------------------------------------------------------
# TASK-27.5 Response correlation tests
# ---------------------------------------------------------------------------


class TestExceptionValidation:
    def test_exceptions_total_zero_fails(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                return httpx.Response(200, json=_async_upload_response("tid-a"))
            if "/status" in url:
                return httpx.Response(200, json=_status_response("tid-a", "UPLOADED"))
            if "/exceptions" in url:
                return httpx.Response(
                    200, json=_exceptions_response("tid-a", 0)
                )
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["failure_step"] == "exceptions"

    def test_exceptions_task_id_mismatch_fails(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                return httpx.Response(200, json=_async_upload_response("tid-real"))
            if "/status" in url:
                return httpx.Response(200, json=_status_response("tid-real", "UPLOADED"))
            if "/exceptions" in url:
                return httpx.Response(200, json=_exceptions_response("tid-wrong", 1))
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["failure_step"] == "exceptions"

    def test_exceptions_items_empty_fails(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                return httpx.Response(200, json=_async_upload_response("tid-e"))
            if "/status" in url:
                return httpx.Response(200, json=_status_response("tid-e", "UPLOADED"))
            if "/exceptions" in url:
                return httpx.Response(
                    200,
                    json={
                        "code": 200,
                        "data": {"task_id": "tid-e", "total": 1, "items": []},
                    },
                )
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["failure_step"] == "exceptions"


class TestAsyncStatusCorrelation:
    def test_async_status_task_id_mismatch_fails(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                return httpx.Response(200, json=_async_upload_response("tid-a"))
            if "/status" in url:
                return httpx.Response(200, json=_status_response("tid-wrong", "UPLOADED"))
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["failure_step"] == "queue_completion"


class TestReportCorrelation:
    def test_report_task_id_mismatch_fails(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                return httpx.Response(200, json=_async_upload_response("tid-a"))
            if "/status" in url:
                return httpx.Response(200, json=_status_response("tid-a", "UPLOADED"))
            if "/exceptions" in url:
                return httpx.Response(200, json=_exceptions_response("tid-a", 1))
            if "/review/pending" in url:
                return httpx.Response(200, json=_pending_response("tid-a", 1, 1))
            if "/approve" in url:
                return httpx.Response(200, json=_approve_response(1))
            if "/report" in url:
                return httpx.Response(200, json=_report_response("tid-wrong"))
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["failure_step"] == "report"


class TestSSEStartLive:
    def test_start_live_data_missing_fails(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                return httpx.Response(200, json=_async_upload_response("tid-a"))
            if "/status" in url:
                return httpx.Response(200, json=_status_response("tid-a", "UPLOADED"))
            if "/exceptions" in url:
                return httpx.Response(200, json=_exceptions_response("tid-a", 1))
            if "/review/pending" in url:
                return httpx.Response(200, json=_pending_response("tid-a", 1, 1))
            if "/approve" in url:
                return httpx.Response(200, json=_approve_response(1))
            if "/report" in url:
                return httpx.Response(200, json=_report_response("tid-a"))
            if "/upload" in url:
                return httpx.Response(200, json=_async_upload_response("tsse-s", "UPLOADED"))
            if "/start-live" in url:
                return httpx.Response(200, json={"code": 200, "message": "ok"})
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["failure_step"] == "sse_terminal"


class TestSSETaskIdCorrelation:
    def test_sse_task_done_task_id_mismatch_fails(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                return httpx.Response(200, json=_async_upload_response("tid-a"))
            if "/status" in url:
                return httpx.Response(200, json=_status_response("tid-a", "UPLOADED"))
            if "/exceptions" in url:
                return httpx.Response(200, json=_exceptions_response("tid-a", 1))
            if "/review/pending" in url:
                return httpx.Response(200, json=_pending_response("tid-a", 1, 1))
            if "/approve" in url:
                return httpx.Response(200, json=_approve_response(1))
            if "/report" in url:
                return httpx.Response(200, json=_report_response("tid-a"))
            if "/upload" in url:
                return httpx.Response(200, json=_async_upload_response("tsse-real", "UPLOADED"))
            if "/start-live" in url:
                return httpx.Response(
                    200,
                    json={"code": 200, "data": {"task_id": "tsse-real", "status": "AI_RUNNING"}},
                )
            if "/events" in url:
                return httpx.Response(
                    200,
                    content=_build_sse_frame("TASK_DONE", "tsse-wrong", "COMPLETED").encode(),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["failure_step"] == "sse_terminal"

    def test_sse_final_status_task_id_mismatch_fails(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                return httpx.Response(200, json=_async_upload_response("tid-a"))
            if "/status" in url:
                if "tsse-final" in url:
                    return httpx.Response(200, json=_status_response("tsse-wrong", "COMPLETED"))
                return httpx.Response(200, json=_status_response("tid-a", "UPLOADED"))
            if "/exceptions" in url:
                return httpx.Response(200, json=_exceptions_response("tid-a", 1))
            if "/review/pending" in url:
                return httpx.Response(200, json=_pending_response("tid-a", 1, 1))
            if "/approve" in url:
                return httpx.Response(200, json=_approve_response(1))
            if "/report" in url:
                return httpx.Response(200, json=_report_response("tid-a"))
            if "/upload" in url:
                return httpx.Response(200, json=_async_upload_response("tsse-final", "UPLOADED"))
            if "/start-live" in url:
                return httpx.Response(
                    200,
                    json={"code": 200, "data": {"task_id": "tsse-final", "status": "AI_RUNNING"}},
                )
            if "/events" in url:
                return httpx.Response(
                    200,
                    content=_build_sse_frame("TASK_DONE", "tsse-final", "COMPLETED").encode(),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["failure_step"] == "sse_terminal"

    def test_sse_final_status_not_completed_fails(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "/health" in url:
                return httpx.Response(200, json=_health_ok())
            if "/api/v1/auth/login" in url:
                return httpx.Response(200, json=_signup_response())
            if "upload-async" in url:
                return httpx.Response(200, json=_async_upload_response("tid-a"))
            if "/status" in url:
                if "tsse-nc" in url:
                    return httpx.Response(200, json=_status_response("tsse-nc", "RUNNING"))
                return httpx.Response(200, json=_status_response("tid-a", "UPLOADED"))
            if "/exceptions" in url:
                return httpx.Response(200, json=_exceptions_response("tid-a", 1))
            if "/review/pending" in url:
                return httpx.Response(200, json=_pending_response("tid-a", 1, 1))
            if "/approve" in url:
                return httpx.Response(200, json=_approve_response(1))
            if "/report" in url:
                return httpx.Response(200, json=_report_response("tid-a"))
            if "/upload" in url:
                return httpx.Response(200, json=_async_upload_response("tsse-nc", "UPLOADED"))
            if "/start-live" in url:
                return httpx.Response(
                    200,
                    json={"code": 200, "data": {"task_id": "tsse-nc", "status": "AI_RUNNING"}},
                )
            if "/events" in url:
                return httpx.Response(
                    200,
                    content=_build_sse_frame("TASK_DONE", "tsse-nc", "COMPLETED").encode(),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(404)

        from scripts.smoke_demo import run_smoke
        summary_file = tmp_path / "summary.json"
        client = httpx.Client(transport=httpx.MockTransport(handler))
        exit_code, summary = run_smoke(
            base_url="http://test:8000",
            summary_json=str(summary_file),
            request_timeout=30,
            task_timeout=60,
            client=client,
        )
        assert exit_code != 0
        assert summary["failure_step"] == "sse_terminal"
