"""Rotas de gestão de usuários (exclusivas de Administrador)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.auth import StatusToggleRequest, UserCreate, UserOut, UserUpdate
from app.schemas.catalog import PaginatedResponse
from app.services.auth_service import (
    create_user,
    list_users,
    set_user_status,
    update_user,
)


router = APIRouter(prefix="/users", tags=["Usuários"])


@router.get("", response_model=PaginatedResponse[UserOut])
def get_users(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedResponse[UserOut]:
    """Lista usuários cadastrados."""
    data = list_users(
        db, search=search, role=role, is_active=is_active, page=page, page_size=page_size
    )
    return PaginatedResponse[UserOut](
        items=[UserOut.model_validate(u) for u in data["items"]],
        total=data["total"],
        page=data["page"],
        page_size=data["page_size"],
        total_pages=data["total_pages"],
    )


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def post_user(
    payload: UserCreate,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> UserOut:
    """Cria um novo usuário."""
    return UserOut.model_validate(create_user(db, payload))


@router.put("/{user_id}", response_model=UserOut)
def put_user(
    user_id: int,
    payload: UserUpdate,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> UserOut:
    """Atualiza um usuário existente."""
    return UserOut.model_validate(
        update_user(db, user_id, payload, acting_admin_id=admin.id)
    )


@router.patch("/{user_id}/status", response_model=UserOut)
def patch_user_status(
    user_id: int,
    payload: StatusToggleRequest,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> UserOut:
    """Ativa ou inativa um usuário."""
    return UserOut.model_validate(
        set_user_status(
            db, user_id, is_active=payload.is_active, acting_admin_id=admin.id
        )
    )
