"""Rotas de cadastro de categorias."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.auth import StatusToggleRequest
from app.schemas.catalog import CategoryCreate, CategoryOut, PaginatedResponse
from app.services.catalog_service import (
    create_category,
    list_categories,
    set_category_status,
    update_category,
)


router = APIRouter(prefix="/categories", tags=["Categorias"])


@router.get("", response_model=PaginatedResponse[CategoryOut])
def get_categories(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    search: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> PaginatedResponse[CategoryOut]:
    """Lista categorias para consulta e seleção em cadastros."""
    data = list_categories(
        db, search=search, is_active=is_active, page=page, page_size=page_size
    )
    return PaginatedResponse[CategoryOut](
        items=[CategoryOut.model_validate(c) for c in data["items"]],
        total=data["total"],
        page=data["page"],
        page_size=data["page_size"],
        total_pages=data["total_pages"],
    )


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def post_category(
    payload: CategoryCreate,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> CategoryOut:
    """Cadastra nova categoria (apenas Administrador)."""
    return CategoryOut.model_validate(create_category(db, payload))


@router.put("/{category_id}", response_model=CategoryOut)
def put_category(
    category_id: int,
    payload: CategoryCreate,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> CategoryOut:
    """Edita categoria existente (apenas Administrador)."""
    return CategoryOut.model_validate(update_category(db, category_id, payload))


@router.patch("/{category_id}/status", response_model=CategoryOut)
def patch_category_status(
    category_id: int,
    payload: StatusToggleRequest,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> CategoryOut:
    """Ativa ou inativa uma categoria (apenas Administrador)."""
    return CategoryOut.model_validate(
        set_category_status(db, category_id, is_active=payload.is_active)
    )
