"""Schemas de autenticação e gestão de usuários."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import EmailValue


UserRole = Literal["ADMIN", "OPERATOR"]


class LoginRequest(BaseModel):
    """Credenciais para autenticação."""

    email: EmailValue
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    """Representação segura do usuário sem expor hash de senha."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailValue
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    """Resposta de login bem-sucedido."""

    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class UserCreate(BaseModel):
    """Dados para cadastro de novo usuário."""

    name: str = Field(min_length=2, max_length=120)
    email: EmailValue
    password: str = Field(min_length=6, max_length=128)
    role: UserRole = "OPERATOR"

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Informe o nome completo do usuário.")
        return cleaned


class UserUpdate(BaseModel):
    """Dados para atualização de usuário pelo administrador."""

    name: str = Field(min_length=2, max_length=120)
    email: EmailValue
    role: UserRole
    password: str | None = Field(default=None, min_length=6, max_length=128)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Informe o nome completo do usuário.")
        return cleaned


class StatusToggleRequest(BaseModel):
    """Requisição para ativar ou inativar um registro."""

    is_active: bool
