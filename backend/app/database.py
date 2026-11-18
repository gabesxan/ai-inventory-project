"""Configuração da conexão com PostgreSQL via SQLAlchemy 2.0."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Classe base declarativa para todos os modelos ORM."""


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Fornece uma sessão de banco de dados por requisição HTTP."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
