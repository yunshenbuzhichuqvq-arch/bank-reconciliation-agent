import logging

from fastapi.testclient import TestClient

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.core.security import decode_token
from bank_reconciliation_agent.main import app


client = TestClient(app)


def test_api_v1_requires_user_id_header() -> None:
    response = client.post("/api/v1/rag/search", json={"query": "金额差异", "top_k": 1})

    assert response.status_code == 401
    assert response.json()["detail"] == "X-User-ID header is required"


def test_api_v1_rejects_non_demo_user() -> None:
    response = client.post(
        "/api/v1/rag/search",
        headers={"X-User-ID": "other_user"},
        json={"query": "金额差异", "top_k": 1},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "invalid X-User-ID"


def test_api_v1_accepts_demo_user_header() -> None:
    response = client.post(
        "/api/v1/rag/search",
        headers={"X-User-ID": "demo_user"},
        json={"query": "金额差异", "top_k": 1},
    )

    assert response.status_code == 200


def test_login_without_auth_header_returns_decodable_token() -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "demo_user", "password": settings.demo_user_password},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["token_type"] == "bearer"
    assert data["username"] == "demo_user"
    assert decode_token(data["access_token"])["sub"] == "demo_user"


def test_login_rejects_wrong_password_and_unknown_user_identically() -> None:
    wrong_password_response = client.post(
        "/api/v1/auth/login",
        json={"username": "demo_user", "password": "wrong-password"},
    )
    unknown_user_response = client.post(
        "/api/v1/auth/login",
        json={"username": "unknown-user", "password": "wrong-password"},
    )

    assert wrong_password_response.status_code == 401
    assert unknown_user_response.status_code == 401
    assert wrong_password_response.json()["detail"] == "用户名或密码错误"
    assert unknown_user_response.json()["detail"] == wrong_password_response.json()["detail"]


def test_login_audit_logs_result_without_password(caplog) -> None:
    password = "audit-secret-password"
    caplog.set_level(logging.INFO)

    client.post(
        "/api/v1/auth/login",
        json={"username": "demo_user", "password": settings.demo_user_password},
    )
    client.post(
        "/api/v1/auth/login",
        json={"username": "demo_user", "password": password},
    )

    assert "login_succeeded" in caplog.text
    assert "login_failed" in caplog.text
    assert password not in caplog.text
    assert settings.demo_user_password not in caplog.text
