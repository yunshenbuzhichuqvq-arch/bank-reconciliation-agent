from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.services.auth import AuthService, user_table


@pytest.fixture
def auth_service(tmp_path: Path) -> tuple[AuthService, Engine]:
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.sqlite'}")
    return AuthService(engine), engine


def test_initialization_creates_and_seeds_demo_user(
    auth_service: tuple[AuthService, Engine],
) -> None:
    service, engine = auth_service

    service._ensure_initialized()

    with engine.connect() as connection:
        username = connection.execute(select(user_table.c.username)).scalar_one()
    assert username == "demo_user"


def test_initialization_is_idempotent(auth_service: tuple[AuthService, Engine]) -> None:
    service, engine = auth_service

    service._ensure_initialized()
    service._ensure_initialized()

    with engine.connect() as connection:
        user_count = connection.execute(select(func.count()).select_from(user_table)).scalar_one()
    assert user_count == 1


def test_authenticate_accepts_seed_credentials(
    auth_service: tuple[AuthService, Engine],
) -> None:
    service, _ = auth_service

    assert service.authenticate("demo_user", settings.demo_user_password) is True


@pytest.mark.parametrize(
    ("username", "password"),
    [("demo_user", "wrong-password"), ("unknown-user", settings.demo_user_password)],
)
def test_authenticate_rejects_invalid_credentials(
    auth_service: tuple[AuthService, Engine], username: str, password: str
) -> None:
    service, _ = auth_service

    assert service.authenticate(username, password) is False
