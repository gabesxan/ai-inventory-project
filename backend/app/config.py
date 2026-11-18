"""Configurações da aplicação carregadas a partir de variáveis de ambiente."""

from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Configurações centralizadas do backend."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Sistema de Gestão de Estoque"
    API_PREFIX: str = "/api"
    DATABASE_URL: str = (
        "postgresql+psycopg://inventory:inventory_dev_pwd@localhost:5432/ai_inventory"
    )
    TEST_DATABASE_URL: str = (
        "postgresql+psycopg://inventory:inventory_dev_pwd@localhost:5432/ai_inventory_test"
    )
    SECRET_KEY: str = "dev-secret-change-in-production-at-least-32-chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        """Retorna a lista de origens CORS configuradas."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        """Garante que a chave secreta não esteja vazia."""
        if not value or len(value.strip()) < 16:
            raise ValueError("SECRET_KEY deve possuir ao menos 16 caracteres.")
        return value


settings = Settings()
