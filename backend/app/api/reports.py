"""Rotas de relatórios e exportações CSV filtradas (exclusivas de Administrador)."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.catalog import PaginatedResponse, ProductOut
from app.schemas.inventory import MovementOut
from app.schemas.reports import ComparisonRow, ModelSource, ReplenishmentRow, VersionedReport
from app.services.inventory_service import list_movements
from app.services.replenishment_reports import stored_comparison, stored_replenishment
from app.services.report_service import (
    export_below_minimum_csv,
    export_current_stock_csv,
    export_movements_csv,
    get_below_minimum_report,
    get_current_stock_report,
)
from app.services.versioned_reports import report_csv, report_page


router = APIRouter(prefix="/reports", tags=["Relatórios"])


@router.get("/replenishment", response_model=VersionedReport[ReplenishmentRow])
def report_replenishment(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    sku: str | None = Query(default=None, min_length=1, max_length=64),
    warehouse: str | None = Query(default=None, min_length=1, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> VersionedReport[ReplenishmentRow]:
    """Lê as sugestões persistidas pelo processo de reposição."""
    return stored_replenishment(db, sku, warehouse, page, page_size)


@router.get("/comparison", response_model=VersionedReport[ComparisonRow])
def report_comparison(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    source: ModelSource | None = Query(default=None),
    model_run_id: str | None = Query(default=None, min_length=1, max_length=36),
    scenario: str | None = Query(default=None, min_length=1, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    export: Literal["json", "csv"] = Query(default="json"),
):
    """Compara resultados persistidos e exporta o mesmo recorte."""
    rows = stored_comparison(db, source, model_run_id, scenario)
    if export == "csv":
        return report_csv(ComparisonRow, rows, "relatorio_comparacao.csv")
    return report_page(ComparisonRow, rows, page, page_size)


@router.get("/current-stock")
def report_current_stock(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    search: str | None = Query(default=None),
    category_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=True),
    stock_status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    export: Literal["json", "csv"] = Query(default="json"),
):
    """Relatório de estoque atual (JSON paginado ou download CSV)."""
    if export == "csv":
        content = export_current_stock_csv(
            db,
            search=search,
            category_id=category_id,
            is_active=is_active,
            stock_status=stock_status,
        )
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="relatorio_estoque_atual.csv"'
            },
        )
    data = get_current_stock_report(
        db,
        search=search,
        category_id=category_id,
        is_active=is_active,
        stock_status=stock_status,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse[ProductOut](**data)


@router.get("/below-minimum")
def report_below_minimum(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    search: str | None = Query(default=None),
    category_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    export: Literal["json", "csv"] = Query(default="json"),
):
    """Relatório de produtos ativos abaixo do estoque mínimo (JSON ou CSV)."""
    if export == "csv":
        content = export_below_minimum_csv(
            db, search=search, category_id=category_id
        )
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="relatorio_abaixo_minimo.csv"'
            },
        )
    data = get_below_minimum_report(
        db,
        search=search,
        category_id=category_id,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse[ProductOut](**data)


@router.get("/movements")
def report_movements(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    product_id: int | None = Query(default=None),
    movement_type: str | None = Query(default=None),
    reason_code: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    export: Literal["json", "csv"] = Query(default="json"),
):
    """Relatório de histórico de movimentações (JSON ou CSV)."""
    if export == "csv":
        content = export_movements_csv(
            db,
            product_id=product_id,
            movement_type=movement_type,
            reason_code=reason_code,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            search=search,
        )
        return Response(
            content=content,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="relatorio_movimentacoes.csv"'
            },
        )
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
