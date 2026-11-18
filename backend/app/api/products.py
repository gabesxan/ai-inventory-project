"""Rotas de cadastro e consulta de produtos."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.auth import StatusToggleRequest
from app.schemas.catalog import (
    PaginatedResponse,
    ProductCreate,
    ProductOut,
    UnitSpecOut,
)
from app.services.catalog_service import (
    create_product,
    get_product,
    list_products,
    set_product_status,
    update_product,
)
from app.services.units import UNIT_SPECS


router = APIRouter(prefix="/products", tags=["Produtos"])


@router.get("/units", response_model=list[UnitSpecOut])
def get_supported_units(
    _user: Annotated[User, Depends(get_current_user)],
) -> list[UnitSpecOut]:
    """Retorna as unidades de medida suportadas e suas regras decimais."""
    return [UnitSpecOut(**spec) for spec in UNIT_SPECS.values()]


@router.get("", response_model=PaginatedResponse[ProductOut])
def get_products(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    search: str | None = Query(default=None),
    category_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    stock_status: str | None = Query(default=None),
    unit: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> PaginatedResponse[ProductOut]:
    """Lista produtos com pesquisa, filtros e paginação."""
    data = list_products(
        db,
        search=search,
        category_id=category_id,
        is_active=is_active,
        stock_status=stock_status,
        unit=unit,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse[ProductOut](**data)


@router.get("/{product_id}", response_model=ProductOut)
def get_product_detail(
    product_id: int,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProductOut:
    """Retorna os detalhes de um produto."""
    return get_product(db, product_id)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def post_product(
    payload: ProductCreate,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ProductOut:
    """Cadastra novo produto com saldo inicial igual a zero (apenas Administrador)."""
    return create_product(db, payload)


@router.put("/{product_id}", response_model=ProductOut)
def put_product(
    product_id: int,
    payload: ProductCreate,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ProductOut:
    """Edita informações cadastrais do produto (apenas Administrador)."""
    return update_product(db, product_id, payload)


@router.patch("/{product_id}/status", response_model=ProductOut)
def patch_product_status(
    product_id: int,
    payload: StatusToggleRequest,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> ProductOut:
    """Ativa ou inativa produto sem perder histórico (apenas Administrador)."""
    return set_product_status(db, product_id, is_active=payload.is_active)
