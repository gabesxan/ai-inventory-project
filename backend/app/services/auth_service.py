"""Serviços de autenticação, revogação de sessão e gestão de usuários."""

from datetime import datetime, timezone
import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user import RevokedToken, User
from app.schemas.auth import UserCreate, UserUpdate
from app.security import create_access_token, hash_password, verify_password
from app.services.exceptions import DomainError


def authenticate_user(db: Session, email: str, password: str) -> tuple[User, str, datetime]:
    """Autentica um usuário e retorna o registro, JWT e expiração."""
    normalized_email = email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == normalized_email))
    if not user or not verify_password(password, user.password_hash):
        raise DomainError(401, "E-mail ou senha inválidos.")
    if not user.is_active:
        raise DomainError(403, "Usuário inativo. Procure um administrador.")

    token, _jti, expires_at = create_access_token(user_id=user.id, role=user.role)
    return user, token, expires_at


def revoke_token(db: Session, jti: str, expires_at: datetime) -> None:
    """Revoga um token JWT no banco para invalidar a sessão após logout."""
    existing = db.scalar(select(RevokedToken).where(RevokedToken.jti == jti))
    if existing:
        return
    db.add(RevokedToken(jti=jti, expires_at=expires_at))
    db.commit()


def is_token_revoked(db: Session, jti: str) -> bool:
    """Verifica se o token JWT já foi revogado."""
    found = db.scalar(select(RevokedToken.id).where(RevokedToken.jti == jti))
    return found is not None


def list_users(
    db: Session,
    *,
    search: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Lista usuários com paginação e filtros."""
    stmt = select(User)
    if search:
        term = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            func.lower(User.name).like(term) | func.lower(User.email).like(term)
        )
    if role:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    total_pages = max(1, math.ceil(total / page_size))
    items = db.scalars(
        stmt.order_by(User.name.asc(), User.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def create_user(db: Session, payload: UserCreate) -> User:
    """Cadastra um novo usuário com senha criptografada via bcrypt."""
    normalized_email = payload.email.strip().lower()
    existing = db.scalar(select(User).where(func.lower(User.email) == normalized_email))
    if existing:
        raise DomainError(409, "Já existe um usuário cadastrado com este e-mail.")

    user = User(
        name=payload.name,
        email=normalized_email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _count_other_active_admins(db: Session, exclude_user_id: int) -> int:
    return (
        db.scalar(
            select(func.count(User.id)).where(
                User.role == "ADMIN",
                User.is_active.is_(True),
                User.id != exclude_user_id,
            )
        )
        or 0
    )


def update_user(
    db: Session,
    user_id: int,
    payload: UserUpdate,
    *,
    acting_admin_id: int,
) -> User:
    """Atualiza dados cadastrais, perfil e opcionalmente a senha de um usuário."""
    user = db.get(User, user_id)
    if not user:
        raise DomainError(404, "Usuário não encontrado.")

    normalized_email = payload.email.strip().lower()
    conflict = db.scalar(
        select(User).where(
            func.lower(User.email) == normalized_email,
            User.id != user_id,
        )
    )
    if conflict:
        raise DomainError(409, "Já existe outro usuário cadastrado com este e-mail.")

    if user.role == "ADMIN" and payload.role != "ADMIN":
        if user.id == acting_admin_id:
            raise DomainError(400, "Você não pode rebaixar o perfil da própria conta em uso.")
        if _count_other_active_admins(db, user.id) == 0:
            raise DomainError(
                400, "Deve permanecer ao menos um administrador ativo no sistema."
            )

    user.name = payload.name
    user.email = normalized_email
    user.role = payload.role
    if payload.password:
        user.password_hash = hash_password(payload.password)
    user.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(user)
    return user


def set_user_status(
    db: Session,
    user_id: int,
    *,
    is_active: bool,
    acting_admin_id: int,
) -> User:
    """Ativa ou inativa um usuário preservando integridade administrativa."""
    user = db.get(User, user_id)
    if not user:
        raise DomainError(404, "Usuário não encontrado.")

    if not is_active:
        if user.id == acting_admin_id:
            raise DomainError(400, "Você não pode inativar a própria conta autenticada.")
        if user.role == "ADMIN" and _count_other_active_admins(db, user.id) == 0:
            raise DomainError(
                400, "Não é possível inativar o último administrador ativo do sistema."
            )

    user.is_active = is_active
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user
