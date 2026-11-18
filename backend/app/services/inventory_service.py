"""Motor transacional de movimentações de estoque com bloqueio concorrente."""

from datetime import date, datetime, time, timezone
from decimal import Decimal
import math
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.catalog import Product, Supplier
from app.models.inventory import StockMovement, StockoutPeriod
from app.models.user import User
from app.schemas.inventory import (
    AdjustmentMovementCreate,
    EntryMovementCreate,
    ExitMovementCreate,
    MovementOut,
)
from app.services.exceptions import DomainError
from app.services.units import format_quantity, quantize_money, validate_quantity_for_unit


SAO_PAULO_TZ = ZoneInfo("America/Sao_Paulo")


def _update_stockout_tracking(
    db: Session,
    *,
    product: Product,
    balance_before: Decimal,
    balance_after: Decimal,
    movement: StockMovement,
) -> None:
    """Abre ou fecha períodos de ruptura de estoque na mesma transação."""
    if balance_before > Decimal("0") and balance_after == Decimal("0"):
        db.add(
            StockoutPeriod(
                product_id=product.id,
                started_at=movement.created_at,
                start_movement_id=movement.id,
            )
        )
    elif balance_before == Decimal("0") and balance_after > Decimal("0"):
        open_period = db.scalar(
            select(StockoutPeriod)
            .where(
                StockoutPeriod.product_id == product.id,
                StockoutPeriod.ended_at.is_(None),
            )
            .order_by(StockoutPeriod.started_at.desc())
        )
        if open_period:
            open_period.ended_at = movement.created_at
            open_period.end_movement_id = movement.id


def _load_movement_out(db: Session, movement_id: int) -> MovementOut:
    mv = db.scalar(
        select(StockMovement)
        .options(
            joinedload(StockMovement.product),
            joinedload(StockMovement.supplier),
            joinedload(StockMovement.user),
        )
        .where(StockMovement.id == movement_id)
    )
    if not mv:
        raise DomainError(404, "Movimentação não encontrada.")

    reversed_by_id = db.scalar(
        select(StockMovement.id).where(StockMovement.reference_movement_id == mv.id)
    )
    return _to_movement_out(mv, reversed_by_id=reversed_by_id)


def _to_movement_out(mv: StockMovement, *, reversed_by_id: int | None) -> MovementOut:
    actual_lead_time_days = None
    if mv.order_date and mv.received_date:
        actual_lead_time_days = (mv.received_date - mv.order_date).days

    return MovementOut(
        id=mv.id,
        product_id=mv.product_id,
        product_name=mv.product.name,
        product_sku=mv.product.sku,
        product_unit=mv.product.unit,
        movement_type=mv.movement_type,
        reason_code=mv.reason_code,
        is_demand=mv.is_demand,
        quantity=mv.quantity,
        signed_quantity=mv.signed_quantity,
        unit_snapshot=mv.unit_snapshot,
        balance_before=mv.balance_before,
        balance_after=mv.balance_after,
        unit_cost=mv.unit_cost,
        supplier_id=mv.supplier_id,
        supplier_name=mv.supplier.name if mv.supplier else None,
        order_date=mv.order_date,
        received_date=mv.received_date,
        actual_lead_time_days=actual_lead_time_days,
        user_id=mv.user_id,
        user_name=mv.user.name,
        reference_movement_id=mv.reference_movement_id,
        reversed_by_movement_id=reversed_by_id,
        notes=mv.notes,
        is_synthetic=mv.is_synthetic,
        created_at=mv.created_at,
    )


def _lock_active_product(db: Session, product_id: int) -> Product:
    """Bloqueia a linha do produto para evitar condição de corrida em saídas simultâneas."""
    product = db.scalar(
        select(Product).where(Product.id == product_id).with_for_update()
    )
    if not product:
        raise DomainError(404, "Produto não encontrado.")
    if not product.is_active:
        raise DomainError(400, "Não é permitido movimentar um produto inativo.")
    return product


def register_entry(
    db: Session,
    *,
    user: User,
    payload: EntryMovementCreate,
) -> MovementOut:
    """Registra entrada de estoque preservando custo unitário histórico e lead time."""
    if payload.order_date and payload.received_date and payload.received_date < payload.order_date:
        raise DomainError(
            422, "A data de recebimento não pode ser anterior à data do pedido."
        )

    if payload.supplier_id is not None:
        supplier = db.get(Supplier, payload.supplier_id)
        if not supplier:
            raise DomainError(404, "Fornecedor informado não encontrado.")

    try:
        product = _lock_active_product(db, payload.product_id)
        try:
            qty = validate_quantity_for_unit(payload.quantity, product.unit)
            unit_cost = (
                quantize_money(payload.unit_cost)
                if payload.unit_cost is not None
                else product.unit_cost
            )
        except ValueError as exc:
            raise DomainError(422, str(exc)) from exc

        balance_before = product.current_stock
        balance_after = balance_before + qty
        product.current_stock = balance_after
        product.updated_at = datetime.now(timezone.utc)

        mv = StockMovement(
            product_id=product.id,
            movement_type="ENTRADA",
            reason_code=payload.reason_code,
            is_demand=False,
            quantity=qty,
            signed_quantity=qty,
            unit_snapshot=product.unit,
            balance_before=balance_before,
            balance_after=balance_after,
            unit_cost=unit_cost,
            supplier_id=payload.supplier_id,
            order_date=payload.order_date,
            received_date=payload.received_date,
            user_id=user.id,
            notes=payload.notes,
        )
        db.add(mv)
        db.flush()

        _update_stockout_tracking(
            db,
            product=product,
            balance_before=balance_before,
            balance_after=balance_after,
            movement=mv,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _load_movement_out(db, mv.id)


def register_exit(
    db: Session,
    *,
    user: User,
    payload: ExitMovementCreate,
) -> MovementOut:
    """Registra saída de estoque impedindo saldo negativo sob bloqueio de linha."""
    try:
        product = _lock_active_product(db, payload.product_id)
        try:
            qty = validate_quantity_for_unit(payload.quantity, product.unit)
        except ValueError as exc:
            raise DomainError(422, str(exc)) from exc

        balance_before = product.current_stock
        balance_after = balance_before - qty
        if balance_after < Decimal("0"):
            available_fmt = format_quantity(balance_before, product.unit)
            raise DomainError(
                400,
                f"Saldo insuficiente para realizar a saída. Saldo disponível: {available_fmt} {product.unit}.",
            )

        product.current_stock = balance_after
        product.updated_at = datetime.now(timezone.utc)

        is_demand = payload.reason_code in ("VENDA", "CONSUMO")
        mv = StockMovement(
            product_id=product.id,
            movement_type="SAIDA",
            reason_code=payload.reason_code,
            is_demand=is_demand,
            quantity=qty,
            signed_quantity=-qty,
            unit_snapshot=product.unit,
            balance_before=balance_before,
            balance_after=balance_after,
            unit_cost=None,
            user_id=user.id,
            notes=payload.notes,
        )
        db.add(mv)
        db.flush()

        _update_stockout_tracking(
            db,
            product=product,
            balance_before=balance_before,
            balance_after=balance_after,
            movement=mv,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _load_movement_out(db, mv.id)


def register_adjustment(
    db: Session,
    *,
    user: User,
    payload: AdjustmentMovementCreate,
) -> MovementOut:
    """Registra ajuste positivo ou negativo (exclusivo de Administrador)."""
    if user.role != "ADMIN":
        raise DomainError(403, "Apenas administradores podem registrar ajustes de estoque.")

    try:
        product = _lock_active_product(db, payload.product_id)
        try:
            qty = validate_quantity_for_unit(payload.quantity, product.unit)
        except ValueError as exc:
            raise DomainError(422, str(exc)) from exc

        signed_qty = qty if payload.direction == "POSITIVO" else -qty
        reason_code = (
            "AJUSTE_POSITIVO" if payload.direction == "POSITIVO" else "AJUSTE_NEGATIVO"
        )
        balance_before = product.current_stock
        balance_after = balance_before + signed_qty

        if balance_after < Decimal("0"):
            available_fmt = format_quantity(balance_before, product.unit)
            raise DomainError(
                400,
                f"Ajuste negativo bloqueado: o saldo ficaria negativo. Saldo disponível: {available_fmt} {product.unit}.",
            )

        product.current_stock = balance_after
        product.updated_at = datetime.now(timezone.utc)

        mv = StockMovement(
            product_id=product.id,
            movement_type="AJUSTE",
            reason_code=reason_code,
            is_demand=False,
            quantity=qty,
            signed_quantity=signed_qty,
            unit_snapshot=product.unit,
            balance_before=balance_before,
            balance_after=balance_after,
            unit_cost=None,
            user_id=user.id,
            notes=payload.notes,
        )
        db.add(mv)
        db.flush()

        _update_stockout_tracking(
            db,
            product=product,
            balance_before=balance_before,
            balance_after=balance_after,
            movement=mv,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _load_movement_out(db, mv.id)


def reverse_movement(
    db: Session,
    *,
    user: User,
    movement_id: int,
    notes: str,
) -> MovementOut:
    """Estorna uma movimentação concluída gerando lançamento inverso vinculado."""
    if user.role != "ADMIN":
        raise DomainError(403, "Apenas administradores podem estornar movimentações.")

    cleaned_notes = notes.strip()
    if len(cleaned_notes) < 5:
        raise DomainError(422, "A justificativa do estorno deve ter ao menos 5 caracteres.")

    try:
        # Descobrimos o product_id antes para travar o produto primeiro (evita deadlocks)
        target_product_id = db.scalar(
            select(StockMovement.product_id).where(StockMovement.id == movement_id)
        )
        if not target_product_id:
            raise DomainError(404, "Movimentação original não encontrada.")

        product = _lock_active_product(db, target_product_id)

        original = db.scalar(
            select(StockMovement)
            .where(StockMovement.id == movement_id)
            .with_for_update()
        )
        if not original:
            raise DomainError(404, "Movimentação original não encontrada.")

        if original.movement_type == "ESTORNO":
            raise DomainError(
                400, "Não é permitido estornar uma movimentação que já é um estorno."
            )

        already_reversed = db.scalar(
            select(StockMovement.id).where(
                StockMovement.reference_movement_id == original.id
            )
        )
        if already_reversed:
            raise DomainError(409, "Esta movimentação já foi estornada anteriormente.")

        signed_qty = -original.signed_quantity
        balance_before = product.current_stock
        balance_after = balance_before + signed_qty

        if balance_after < Decimal("0"):
            available_fmt = format_quantity(balance_before, product.unit)
            raise DomainError(
                400,
                f"Estorno bloqueado: o saldo resultante ficaria negativo (saldo atual: {available_fmt} {product.unit}).",
            )

        product.current_stock = balance_after
        product.updated_at = datetime.now(timezone.utc)

        reversal = StockMovement(
            product_id=product.id,
            movement_type="ESTORNO",
            reason_code="ESTORNO",
            is_demand=False,
            quantity=original.quantity,
            signed_quantity=signed_qty,
            unit_snapshot=original.unit_snapshot,
            balance_before=balance_before,
            balance_after=balance_after,
            unit_cost=original.unit_cost,
            supplier_id=original.supplier_id,
            user_id=user.id,
            reference_movement_id=original.id,
            notes=cleaned_notes,
        )
        db.add(reversal)
        db.flush()

        _update_stockout_tracking(
            db,
            product=product,
            balance_before=balance_before,
            balance_after=balance_after,
            movement=reversal,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _load_movement_out(db, reversal.id)


def _date_bounds_utc(start_date: date | None, end_date: date | None) -> tuple[datetime | None, datetime | None]:
    start_dt = (
        datetime.combine(start_date, time.min, tzinfo=SAO_PAULO_TZ).astimezone(timezone.utc)
        if start_date
        else None
    )
    end_dt = (
        datetime.combine(end_date, time.max, tzinfo=SAO_PAULO_TZ).astimezone(timezone.utc)
        if end_date
        else None
    )
    return start_dt, end_dt


def list_movements(
    db: Session,
    *,
    product_id: int | None = None,
    movement_type: str | None = None,
    reason_code: str | None = None,
    user_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Consulta o histórico imutável de movimentações com filtros e paginação."""
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

    count_stmt = select(func.count()).select_from(
        stmt.with_only_columns(StockMovement.id).subquery()
    )
    total = db.scalar(count_stmt) or 0
    total_pages = max(1, math.ceil(total / page_size))

    rows = db.scalars(
        stmt.order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    row_ids = [r.id for r in rows]
    reversal_map: dict[int, int] = {}
    if row_ids:
        reversals = db.execute(
            select(StockMovement.reference_movement_id, StockMovement.id).where(
                StockMovement.reference_movement_id.in_(row_ids)
            )
        ).all()
        reversal_map = {ref_id: rev_id for ref_id, rev_id in reversals if ref_id is not None}

    items = [
        _to_movement_out(mv, reversed_by_id=reversal_map.get(mv.id)) for mv in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
