"""Configuração global da suíte de testes com PostgreSQL real e Alembic."""

import os
from collections.abc import Generator

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import BASE_DIR, settings
from app.database import get_db
from app.main import app
from app.models.user import User
from app.security import hash_password


TEST_DB_URL = settings.TEST_DATABASE_URL

test_engine = create_engine(TEST_DB_URL, pool_pre_ping=True, future=True)
TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


@pytest.fixture(scope="session", autouse=True)
def apply_test_migrations() -> None:
    """Garante que o banco de testes esteja migrado via Alembic antes dos testes."""
    prev_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DB_URL
    try:
        alembic_cfg = Config(str(BASE_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
        command.upgrade(alembic_cfg, "head")
    finally:
        if prev_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev_db_url


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    """Limpa todas as tabelas entre testes garantindo isolamento real."""
    with test_engine.begin() as conn:
        conn.execute(
            text(
                """
                TRUNCATE TABLE
                    replenishment_states,
                    replenishment_snapshots,
                    replenishment_runs,
                    historical_movements,
                    historical_import_batches,
                    stockout_periods,
                    stock_movements,
                    products,
                    suppliers,
                    categories,
                    revoked_tokens,
                    users
                RESTART IDENTITY CASCADE
                """
            )
        )
    yield


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Sessão de banco dedicada ao teste atual."""
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """Cliente FastAPI conectado ao banco de testes."""

    def override_get_db() -> Generator[Session, None, None]:
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_user(db_session: Session) -> User:
    """Cria usuário Administrador ativo para testes."""
    user = User(
        name="Admin Teste",
        email="admin.teste@empresa.local",
        password_hash=hash_password("Admin123!"),
        role="ADMIN",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def operator_user(db_session: Session) -> User:
    """Cria usuário Operador ativo para testes."""
    user = User(
        name="Operador Teste",
        email="operador.teste@empresa.local",
        password_hash=hash_password("Oper123!"),
        role="OPERATOR",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def admin_headers(client: TestClient, admin_user: User) -> dict[str, str]:
    """Cabeçalho Authorization Bearer para Administrador."""
    res = client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "Admin123!"},
    )
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def operator_headers(client: TestClient, operator_user: User) -> dict[str, str]:
    """Cabeçalho Authorization Bearer para Operador."""
    res = client.post(
        "/api/auth/login",
        json={"email": operator_user.email, "password": "Oper123!"},
    )
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
