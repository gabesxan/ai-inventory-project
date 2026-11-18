"""Dependências compartilhadas de autenticação e autorização (RBAC)."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.security import decode_access_token
from app.services.auth_service import is_token_revoked


bearer_scheme = HTTPBearer(auto_error=False)


def get_token_payload(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Extrai e valida o JWT do cabeçalho Authorization Bearer."""
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária. Faça login para continuar.",
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    jti = str(payload.get("jti", ""))
    if not jti or is_token_revoked(db, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão encerrada ou token revogado. Faça login novamente.",
        )
    return payload


def get_current_user(
    payload: Annotated[dict, Depends(get_token_payload)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Retorna o usuário autenticado a partir do token válido."""
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação inválido.",
        ) from exc

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário da sessão não encontrado.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sua conta está inativa. Procure um administrador.",
        )
    return user


def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Exige perfil de Administrador no backend."""
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return current_user


def token_expiration_datetime(payload: dict) -> datetime:
    """Converte o campo exp do JWT para datetime UTC."""
    exp_ts = int(payload.get("exp", 0))
    return datetime.fromtimestamp(exp_ts, tz=timezone.utc)
