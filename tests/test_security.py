from datetime import UTC, datetime, timedelta

import jwt
import pytest

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_access_token_round_trip_preserves_subject() -> None:
    token = create_access_token("demo_user")

    assert decode_token(token)["sub"] == "demo_user"


def test_decode_token_rejects_expired_token() -> None:
    token = jwt.encode(
        {"sub": "demo_user", "exp": datetime.now(UTC) - timedelta(seconds=1)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token)


def test_decode_token_rejects_tampered_token() -> None:
    token = create_access_token("demo_user")
    replacement = "a" if token[-1] != "a" else "b"

    with pytest.raises(jwt.InvalidTokenError):
        decode_token(f"{token[:-1]}{replacement}")


def test_password_hash_verification() -> None:
    hashed = hash_password("demo12345")

    assert verify_password("demo12345", hashed) is True
    assert verify_password("wrong-password", hashed) is False
