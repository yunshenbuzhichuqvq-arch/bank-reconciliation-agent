from fastapi.testclient import TestClient

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
