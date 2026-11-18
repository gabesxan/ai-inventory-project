"""Utilitários de criptografia de senha (bcrypt) e tokens JWT com revogação."""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import bcrypt
import jwt
from jwt import InvalidTokenError

from app.config import settings


def hash_password(password: str) -> str:
    """Gera o hash seguro de uma senha usando bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verifica se a senha em texto plano corresponde ao hash armazenado."""
    if not plain_password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, role: str) -> tuple[str, str, datetime]:
    """Cria um token JWT assinado contendo identificador único (jti) e expiração."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    jti = str(uuid4())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    """Decodifica e valida assinatura e expiração do token JWT."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except InvalidTokenError as exc:
        raise ValueError("Token inválido ou expirado.") from exc
    if "sub" not in payload or "jti" not in payload:
        raise ValueError("Token sem campos obrigatórios.")
    return payload
