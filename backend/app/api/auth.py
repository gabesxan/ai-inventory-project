"""Rotas de autenticação (login, logout real e usuário atual)."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_token_payload, token_expiration_datetime
from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserOut
from app.services.auth_service import authenticate_user, revoke_token


router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    """Autentica usuário por e-mail e senha e emite token JWT."""
    user, token, expires_at = authenticate_user(db, payload.email, payload.password)
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        user=UserOut.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    payload: Annotated[dict, Depends(get_token_payload)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Revoga o token JWT atual no servidor."""
    jti = str(payload["jti"])
    expires_at = token_expiration_datetime(payload)
    revoke_token(db, jti=jti, expires_at=expires_at)
    return {"message": "Sessão encerrada com sucesso."}


@router.get("/me", response_model=UserOut)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserOut:
    """Retorna os dados do usuário autenticado."""
    return UserOut.model_validate(current_user)
