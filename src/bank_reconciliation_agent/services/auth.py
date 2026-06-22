from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    func,
    insert,
    select,
)
from sqlalchemy.engine import Engine

from bank_reconciliation_agent.core.config import settings
from bank_reconciliation_agent.core.security import hash_password, verify_password
from bank_reconciliation_agent.db.session import get_engine


metadata = MetaData()

user_table = Table(
    "t_user",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True),
    Column("username", String(64), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("created_at", DateTime, server_default=func.now()),
)


class AuthService:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        metadata.create_all(self._engine, tables=[user_table])
        with self._engine.begin() as connection:
            existing_user = connection.execute(
                select(user_table.c.id).where(user_table.c.username == "demo_user")
            ).first()
            if existing_user is None:
                connection.execute(
                    insert(user_table).values(
                        username="demo_user",
                        password_hash=hash_password(settings.demo_user_password),
                    )
                )
        self._initialized = True

    def authenticate(self, username: str, password: str) -> bool:
        self._ensure_initialized()
        with self._engine.connect() as connection:
            password_hash = connection.execute(
                select(user_table.c.password_hash).where(user_table.c.username == username)
            ).scalar_one_or_none()
        if password_hash is None:
            return False
        return verify_password(password, password_hash)


auth_service = AuthService()
