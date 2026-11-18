"""Serviços de geração de relatórios operacionais e exportação CSV."""

import csv
from datetime import date, datetime, timezone
import io
import math
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.catalog import Product
from app.models.inventory import StockMovement
from app.models.user import User
from app.services.catalog_service import list_products
from app.services.inventory_service import _date_bounds_utc, _to_movement_out
from app.services.units import quantize_money


SAO_PAULO_TZ = ZoneInfo("America/Sao_Paulo")


def _build_csv_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    """Gera CSV UTF-8 com BOM para compatibilidade direta com Excel e Python."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=",", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8-sig")


def get_current_stock_report(
    db: Session,
    *,
    search: str | None = None,
    category_id: int | None = None,
    is_active: bool | None = True,
    stock_status: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """Relatório paginado de estoque atual."""
    return list_products(
        db,
        search=search,
        category_id=category_id,
        is_active=is_active,
        stock_status=stock_status,
        page=page,
        page_size=page_size,
    )


def export_current_stock_csv(
    db: Session,
    *,
    search: str | None = None,
    category_id: int | None = None,
    is_active: bool | None = True,
    stock_status: str | None = None,
) -> bytes:
    """Exporta relatório de estoque atual em CSV respeitando todos os filtros."""
    data = list_products(
        db,
        search=search,
        category_id=category_id,
        is_active=is_active,
        stock_status=stock_status,
        page=1,
        page_size=10000,
    )
    headers = [
        "SKU",
        "Produto",
        "Categoria",
        "Unidade",
        "Saldo Atual",
        "Estoque Minimo",
        "Estoque Seguranca",
        "Custo Unitario Referencia (BRL)",
        "Valor Estimado Referencia (BRL)",
        "Localizacao",
        "Fornecedor Preferencial",
        "Prazo Reposicao (dias)",
        "Status Estoque",
        "Ativo",
    ]
    rows = []
    for item in data["items"]:
        rows.append(
            [
                item.sku,
                item.name,
                item.category_name,
                item.unit,
                f"{item.current_stock}",
                f"{item.min_stock}",
                f"{item.safety_stock}",
                f"{quantize_money(item.unit_cost):.2f}",
                f"{quantize_money(item.estimated_total_value):.2f}",
                item.location or "",
                item.preferred_supplier_name or "",
                item.lead_time_days if item.lead_time_days is not None else "",
                item.stock_status,
                "Sim" if item.is_active else "Nao",
            ]
        )
    return _build_csv_bytes(headers, rows)


def get_below_minimum_report(
    db: Session,
    *,
    search: str | None = None,
    category_id: int | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """Relatório paginado de produtos ativos abaixo do estoque mínimo."""
    return list_products(
        db,
        search=search,
        category_id=category_id,
        is_active=True,
        stock_status="BELOW_MIN",
        page=page,
        page_size=page_size,
    )


def export_below_minimum_csv(
    db: Session,
    *,
    search: str | None = None,
    category_id: int | None = None,
) -> bytes:
    """Exporta produtos abaixo do mínimo em CSV respeitando os filtros."""
    data = list_products(
        db,
        search=search,
        category_id=category_id,
        is_active=True,
        stock_status="BELOW_MIN",
        page=1,
        page_size=10000,
    )
    headers = [
        "SKU",
        "Produto",
        "Categoria",
        "Unidade",
        "Saldo Atual",
        "Estoque Minimo",
        "Deficit para Minimo",
        "Fornecedor Preferencial",
        "Prazo Reposicao (dias)",
        "Situacao",
    ]
    rows = []
    for item in data["items"]:
        deficit = max(item.min_stock - item.current_stock, 0)
        rows.append(
            [
                item.sku,
                item.name,
                item.category_name,
                item.unit,
                f"{item.current_stock}",
                f"{item.min_stock}",
                f"{deficit}",
                item.preferred_supplier_name or "",
                item.lead_time_days if item.lead_time_days is not None else "",
                "Sem estoque" if item.current_stock <= 0 else "Abaixo do minimo",
            ]
        )
    return _build_csv_bytes(headers, rows)


def export_movements_csv(
    db: Session,
    *,
    product_id: int | None = None,
    movement_type: str | None = None,
    reason_code: str | None = None,
    user_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    search: str | None = None,
) -> bytes:
    """Exporta histórico de movimentações em CSV respeitando os filtros aplicados."""
    stmt = (
        select(StockMovement)
        .join(Product, Product.id == StockMovement.product_id)
        .join(User, User.id == StockMovement.user_id)
        .options(
            joinedload(StockMovement.product),
            joinedload(StockMovement.supplier),
            joinedload(StockMovement.user),
        )
    )
    if product_id is not None:
        stmt = stmt.where(StockMovement.product_id == product_id)
    if movement_type:
        stmt = stmt.where(StockMovement.movement_type == movement_type.strip().upper())
    if reason_code:
        stmt = stmt.where(StockMovement.reason_code == reason_code.strip().upper())
    if user_id is not None:
        stmt = stmt.where(StockMovement.user_id == user_id)

    start_dt, end_dt = _date_bounds_utc(start_date, end_date)
    if start_dt:
        stmt = stmt.where(StockMovement.created_at >= start_dt)
    if end_dt:
        stmt = stmt.where(StockMovement.created_at <= end_dt)
    if search:
        term = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            func.lower(Product.name).like(term)
            | func.lower(Product.sku).like(term)
            | func.lower(func.coalesce(StockMovement.notes, "")).like(term)
            | func.lower(User.name).like(term)
        )

    rows_orm = db.scalars(
        stmt.order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
    ).all()

    row_ids = [r.id for r in rows_orm]
    reversal_map: dict[int, int] = {}
    if row_ids:
        revs = db.execute(
            select(StockMovement.reference_movement_id, StockMovement.id).where(
                StockMovement.reference_movement_id.in_(row_ids)
            )
        ).all()
        reversal_map = {ref_id: rev_id for ref_id, rev_id in revs if ref_id is not None}

    headers = [
        "ID",
        "Data e Hora (America/Sao_Paulo)",
        "SKU",
        "Produto",
        "Tipo",
        "Motivo",
        "Representa Demanda",
        "Quantidade",
        "Quantidade Assinada",
        "Unidade",
        "Saldo Anterior",
        "Saldo Posterior",
        "Custo Unitario Entrada (BRL)",
        "Fornecedor",
        "Data Pedido",
        "Data Recebimento",
        "Prazo Real (dias)",
        "Responsavel",
        "Movimentacao Estornada ID",
        "Estornada Por ID",
        "Observacao",
        "Dado Sintetico",
    ]

    csv_rows = []
    for mv_orm in rows_orm:
        mv = _to_movement_out(mv_orm, reversed_by_id=reversal_map.get(mv_orm.id))
        local_dt = mv.created_at.astimezone(SAO_PAULO_TZ).strftime("%d/%m/%Y %H:%M:%S")
        csv_rows.append(
            [
                mv.id,
                local_dt,
                mv.product_sku,
                mv.product_name,
                mv.movement_type,
                mv.reason_code,
                "Sim" if mv.is_demand else "Nao",
                f"{mv.quantity}",
                f"{mv.signed_quantity}",
                mv.unit_snapshot,
                f"{mv.balance_before}",
                f"{mv.balance_after}",
                f"{mv.unit_cost:.2f}" if mv.unit_cost is not None else "",
                mv.supplier_name or "",
                mv.order_date.strftime("%d/%m/%Y") if mv.order_date else "",
                mv.received_date.strftime("%d/%m/%Y") if mv.received_date else "",
                mv.actual_lead_time_days if mv.actual_lead_time_days is not None else "",
                mv.user_name,
                mv.reference_movement_id or "",
                mv.reversed_by_movement_id or "",
                mv.notes or "",
                "Sim" if mv.is_synthetic else "Nao",
            ]
        )
    return _build_csv_bytes(headers, csv_rows)
