"""Rotas de movimentações imutáveis de estoque."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.catalog import PaginatedResponse
from app.schemas.inventory import (
    AdjustmentMovementCreate,
    EntryMovementCreate,
    ExitMovementCreate,
    MovementOut,
    MovementResponsibleOut,
    ReversalCreate,
)
from app.services.inventory_service import (
    list_movements,
    register_adjustment,
    register_entry,
    register_exit,
    reverse_movement,
)


router = APIRouter(prefix="/movements", tags=["Movimentações"])


@router.get("/responsibles", response_model=list[MovementResponsibleOut])
def get_movement_responsibles(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[MovementResponsibleOut]:
    """Lista os usuários para popular o filtro por responsável nas movimentações."""
    users = db.scalars(select(User).order_by(User.name.asc(), User.id.asc())).all()
    return [MovementResponsibleOut.model_validate(u) for u in users]


@router.get("", response_model=PaginatedResponse[MovementOut])
def get_movements(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    product_id: int | None = Query(default=None),
    movement_type: str | None = Query(default=None),
    reason_code: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> PaginatedResponse[MovementOut]:
    """Consulta o histórico imutável de entradas, saídas, ajustes e estornos."""
    data = list_movements(
        db,
        product_id=product_id,
        movement_type=movement_type,
        reason_code=reason_code,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        search=search,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse[MovementOut](**data)


@router.post("/entry", response_model=MovementOut, status_code=status.HTTP_201_CREATED)
def post_entry(
    payload: EntryMovementCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MovementOut:
    """Registra entrada por recebimento ou saldo inicial."""
    return register_entry(db, user=user, payload=payload)


@router.post("/exit", response_model=MovementOut, status_code=status.HTTP_201_CREATED)
def post_exit(
    payload: ExitMovementCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> MovementOut:
    """Registra saída por venda, consumo, perda, avaria ou outro motivo."""
    return register_exit(db, user=user, payload=payload)


@router.post("/adjustment", response_model=MovementOut, status_code=status.HTTP_201_CREATED)
def post_adjustment(
    payload: AdjustmentMovementCreate,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> MovementOut:
    """Registra ajuste positivo ou negativo (exclusivo de Administrador)."""
    return register_adjustment(db, user=admin, payload=payload)


@router.post(
    "/{movement_id}/reverse",
    response_model=MovementOut,
    status_code=status.HTTP_201_CREATED,
)
def post_reverse(
    movement_id: int,
    payload: ReversalCreate,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> MovementOut:
    """Estorna uma movimentação concluída gerando lançamento inverso vinculado."""
    return reverse_movement(db, user=admin, movement_id=movement_id, notes=payload.notes)
