"""Rotas de cadastro de fornecedores."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.auth import StatusToggleRequest
from app.schemas.catalog import PaginatedResponse, SupplierCreate, SupplierOut
from app.services.catalog_service import (
    create_supplier,
    list_suppliers,
    set_supplier_status,
    update_supplier,
)


router = APIRouter(prefix="/suppliers", tags=["Fornecedores"])


@router.get("", response_model=PaginatedResponse[SupplierOut])
def get_suppliers(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    search: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> PaginatedResponse[SupplierOut]:
    """Lista fornecedores cadastrados."""
    data = list_suppliers(
        db, search=search, is_active=is_active, page=page, page_size=page_size
    )
    return PaginatedResponse[SupplierOut](
        items=[SupplierOut.model_validate(s) for s in data["items"]],
        total=data["total"],
        page=data["page"],
        page_size=data["page_size"],
        total_pages=data["total_pages"],
    )


@router.post("", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def post_supplier(
    payload: SupplierCreate,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> SupplierOut:
    """Cadastra novo fornecedor (apenas Administrador)."""
    return SupplierOut.model_validate(create_supplier(db, payload))


@router.put("/{supplier_id}", response_model=SupplierOut)
def put_supplier(
    supplier_id: int,
    payload: SupplierCreate,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> SupplierOut:
    """Edita fornecedor existente (apenas Administrador)."""
    return SupplierOut.model_validate(update_supplier(db, supplier_id, payload))


@router.patch("/{supplier_id}/status", response_model=SupplierOut)
def patch_supplier_status(
    supplier_id: int,
    payload: StatusToggleRequest,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> SupplierOut:
    """Ativa ou inativa um fornecedor (apenas Administrador)."""
    return SupplierOut.model_validate(
        set_supplier_status(db, supplier_id, is_active=payload.is_active)
    )
