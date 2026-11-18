"""Serviços de regras de negócio para categorias, fornecedores e produtos."""

from datetime import datetime, timezone
from decimal import Decimal
import math

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.catalog import Category, Product, Supplier
from app.models.historical import HistoricalMovement
from app.models.inventory import StockMovement
from app.schemas.catalog import CategoryCreate, ProductCreate, ProductOut, SupplierCreate
from app.services.exceptions import DomainError
from app.services.units import (
    UNIT_SPECS,
    is_discrete_unit,
    quantize_money,
    validate_quantity_for_unit,
)


def _compute_stock_status(product: Product) -> str:
    if product.current_stock <= Decimal("0"):
        return "OUT_OF_STOCK"
    if product.current_stock < product.min_stock:
        return "BELOW_MIN"
    return "OK"


def _product_has_movements(db: Session, product_id: int) -> bool:
    has_op = db.scalar(
        select(exists().where(StockMovement.product_id == product_id))
    )
    if has_op:
        return True
    has_hist = db.scalar(
        select(exists().where(HistoricalMovement.product_id == product_id))
    )
    return bool(has_hist)


def to_product_out(db: Session, product: Product, *, has_movements: bool | None = None) -> ProductOut:
    """Converte modelo ORM Product para schema de saída enriquecido."""
    if has_movements is None:
        has_movements = _product_has_movements(db, product.id)

    unit_spec = UNIT_SPECS.get(product.unit, {"label": product.unit, "allow_decimal": True})
    estimated_total = quantize_money(product.current_stock * product.unit_cost)
    return ProductOut(
        id=product.id,
        name=product.name,
        sku=product.sku,
        barcode=product.barcode,
        description=product.description,
        category_id=product.category_id,
        category_name=product.category.name if product.category else "-",
        unit=product.unit,
        unit_label=unit_spec["label"],
        is_discrete_unit=is_discrete_unit(product.unit),
        unit_cost=product.unit_cost,
        min_stock=product.min_stock,
        safety_stock=product.safety_stock,
        current_stock=product.current_stock,
        estimated_total_value=estimated_total,
        location=product.location,
        preferred_supplier_id=product.preferred_supplier_id,
        preferred_supplier_name=product.preferred_supplier.name
        if product.preferred_supplier
        else None,
        lead_time_days=product.lead_time_days,
        is_active=product.is_active,
        has_movements=has_movements,
        stock_status=_compute_stock_status(product),
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def list_categories(
    db: Session,
    *,
    search: str | None = None,
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Lista categorias com pesquisa e paginação."""
    stmt = select(Category)
    if search:
        term = f"%{search.strip().lower()}%"
        stmt = stmt.where(func.lower(Category.name).like(term))
    if is_active is not None:
        stmt = stmt.where(Category.is_active == is_active)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    total_pages = max(1, math.ceil(total / page_size))
    items = db.scalars(
        stmt.order_by(Category.name.asc())
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


def create_category(db: Session, payload: CategoryCreate) -> Category:
    """Cadastra uma nova categoria garantindo unicidade do nome."""
    conflict = db.scalar(
        select(Category).where(func.lower(Category.name) == payload.name.lower())
    )
    if conflict:
        raise DomainError(409, "Já existe uma categoria cadastrada com este nome.")

    cat = Category(name=payload.name, description=payload.description, is_active=True)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def update_category(db: Session, category_id: int, payload: CategoryCreate) -> Category:
    """Atualiza uma categoria existente."""
    cat = db.get(Category, category_id)
    if not cat:
        raise DomainError(404, "Categoria não encontrada.")

    conflict = db.scalar(
        select(Category).where(
            func.lower(Category.name) == payload.name.lower(),
            Category.id != category_id,
        )
    )
    if conflict:
        raise DomainError(409, "Já existe outra categoria cadastrada com este nome.")

    cat.name = payload.name
    cat.description = payload.description
    cat.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cat)
    return cat


def set_category_status(db: Session, category_id: int, *, is_active: bool) -> Category:
    """Ativa ou inativa uma categoria."""
    cat = db.get(Category, category_id)
    if not cat:
        raise DomainError(404, "Categoria não encontrada.")
    cat.is_active = is_active
    cat.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(cat)
    return cat


def list_suppliers(
    db: Session,
    *,
    search: str | None = None,
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Lista fornecedores com pesquisa e paginação."""
    stmt = select(Supplier)
    if search:
        term = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            func.lower(Supplier.name).like(term)
            | func.lower(func.coalesce(Supplier.document, "")).like(term)
            | func.lower(func.coalesce(Supplier.contact_name, "")).like(term)
        )
    if is_active is not None:
        stmt = stmt.where(Supplier.is_active == is_active)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    total_pages = max(1, math.ceil(total / page_size))
    items = db.scalars(
        stmt.order_by(Supplier.name.asc())
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


def create_supplier(db: Session, payload: SupplierCreate) -> Supplier:
    """Cadastra um novo fornecedor validando documento único quando informado."""
    if payload.document:
        conflict = db.scalar(
            select(Supplier).where(Supplier.document == payload.document)
        )
        if conflict:
            raise DomainError(409, "Já existe um fornecedor cadastrado com este documento.")

    sup = Supplier(
        name=payload.name,
        document=payload.document,
        contact_name=payload.contact_name,
        email=str(payload.email) if payload.email else None,
        phone=payload.phone,
        default_lead_time_days=payload.default_lead_time_days,
        notes=payload.notes,
        is_active=True,
    )
    db.add(sup)
    db.commit()
    db.refresh(sup)
    return sup


def update_supplier(db: Session, supplier_id: int, payload: SupplierCreate) -> Supplier:
    """Atualiza um fornecedor existente."""
    sup = db.get(Supplier, supplier_id)
    if not sup:
        raise DomainError(404, "Fornecedor não encontrado.")

    if payload.document:
        conflict = db.scalar(
            select(Supplier).where(
                Supplier.document == payload.document,
                Supplier.id != supplier_id,
            )
        )
        if conflict:
            raise DomainError(409, "Já existe outro fornecedor cadastrado com este documento.")

    sup.name = payload.name
    sup.document = payload.document
    sup.contact_name = payload.contact_name
    sup.email = str(payload.email) if payload.email else None
    sup.phone = payload.phone
    sup.default_lead_time_days = payload.default_lead_time_days
    sup.notes = payload.notes
    sup.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sup)
    return sup


def set_supplier_status(db: Session, supplier_id: int, *, is_active: bool) -> Supplier:
    """Ativa ou inativa um fornecedor."""
    sup = db.get(Supplier, supplier_id)
    if not sup:
        raise DomainError(404, "Fornecedor não encontrado.")
    sup.is_active = is_active
    sup.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sup)
    return sup


def list_products(
    db: Session,
    *,
    search: str | None = None,
    category_id: int | None = None,
    is_active: bool | None = None,
    stock_status: str | None = None,
    unit: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Lista produtos com pesquisa por nome/SKU/código de barras, filtros e paginação."""
    stmt = select(Product).options(
        joinedload(Product.category),
        joinedload(Product.preferred_supplier),
    )

    if search:
        term = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            func.lower(Product.name).like(term)
            | func.lower(Product.sku).like(term)
            | func.lower(func.coalesce(Product.barcode, "")).like(term)
            | func.lower(func.coalesce(Product.location, "")).like(term)
        )
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    if is_active is not None:
        stmt = stmt.where(Product.is_active == is_active)
    if unit:
        stmt = stmt.where(Product.unit == unit.strip().upper())
    if stock_status == "OUT_OF_STOCK":
        stmt = stmt.where(Product.current_stock <= Decimal("0"))
    elif stock_status == "BELOW_MIN":
        stmt = stmt.where(Product.current_stock < Product.min_stock)
    elif stock_status == "OK":
        stmt = stmt.where(
            Product.current_stock > Decimal("0"),
            Product.current_stock >= Product.min_stock,
        )

    count_stmt = select(func.count()).select_from(stmt.with_only_columns(Product.id).subquery())
    total = db.scalar(count_stmt) or 0
    total_pages = max(1, math.ceil(total / page_size))

    products = db.scalars(
        stmt.order_by(Product.name.asc(), Product.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    product_ids = [p.id for p in products]
    movement_ids: set[int] = set()
    if product_ids:
        op_ids = db.scalars(
            select(StockMovement.product_id)
            .where(StockMovement.product_id.in_(product_ids))
            .distinct()
        ).all()
        hist_ids = db.scalars(
            select(HistoricalMovement.product_id)
            .where(HistoricalMovement.product_id.in_(product_ids))
            .distinct()
        ).all()
        movement_ids = set(op_ids) | set(hist_ids)

    items = [
        to_product_out(db, prod, has_movements=(prod.id in movement_ids))
        for prod in products
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def get_product(db: Session, product_id: int) -> ProductOut:
    """Busca um produto específico pelo ID."""
    product = db.scalar(
        select(Product)
        .options(joinedload(Product.category), joinedload(Product.preferred_supplier))
        .where(Product.id == product_id)
    )
    if not product:
        raise DomainError(404, "Produto não encontrado.")
    return to_product_out(db, product)


def _validate_product_references(
    db: Session,
    *,
    category_id: int,
    preferred_supplier_id: int | None,
) -> None:
    category = db.get(Category, category_id)
    if not category:
        raise DomainError(404, "Categoria informada não encontrada.")
    if preferred_supplier_id is not None:
        supplier = db.get(Supplier, preferred_supplier_id)
        if not supplier:
            raise DomainError(404, "Fornecedor preferencial informado não encontrado.")


def create_product(db: Session, payload: ProductCreate) -> ProductOut:
    """Cadastra um produto com saldo inicial obrigatoriamente igual a zero."""
    _validate_product_references(
        db,
        category_id=payload.category_id,
        preferred_supplier_id=payload.preferred_supplier_id,
    )

    if db.scalar(select(Product.id).where(Product.sku == payload.sku)):
        raise DomainError(409, "Já existe um produto cadastrado com este SKU.")

    if payload.barcode:
        if db.scalar(select(Product.id).where(Product.barcode == payload.barcode)):
            raise DomainError(
                409, "Já existe um produto cadastrado com este código de barras."
            )

    try:
        min_stock = validate_quantity_for_unit(
            payload.min_stock, payload.unit, allow_zero=True
        )
        safety_stock = validate_quantity_for_unit(
            payload.safety_stock, payload.unit, allow_zero=True
        )
    except ValueError as exc:
        raise DomainError(422, str(exc)) from exc

    product = Product(
        name=payload.name,
        sku=payload.sku,
        barcode=payload.barcode,
        description=payload.description,
        category_id=payload.category_id,
        unit=payload.unit,
        unit_cost=payload.unit_cost,
        min_stock=min_stock,
        safety_stock=safety_stock,
        current_stock=Decimal("0.000"),
        location=payload.location,
        preferred_supplier_id=payload.preferred_supplier_id,
        lead_time_days=payload.lead_time_days,
        is_active=True,
    )
    db.add(product)
    db.commit()
    return get_product(db, product.id)


def update_product(db: Session, product_id: int, payload: ProductCreate) -> ProductOut:
    """Atualiza dados cadastrais do produto sem alterar saldo diretamente."""
    product = db.get(Product, product_id)
    if not product:
        raise DomainError(404, "Produto não encontrado.")

    _validate_product_references(
        db,
        category_id=payload.category_id,
        preferred_supplier_id=payload.preferred_supplier_id,
    )

    if db.scalar(
        select(Product.id).where(Product.sku == payload.sku, Product.id != product_id)
    ):
        raise DomainError(409, "Já existe outro produto cadastrado com este SKU.")

    if payload.barcode:
        if db.scalar(
            select(Product.id).where(
                Product.barcode == payload.barcode, Product.id != product_id
            )
        ):
            raise DomainError(
                409, "Já existe outro produto cadastrado com este código de barras."
            )

    has_movements = _product_has_movements(db, product_id)
    if has_movements and payload.unit != product.unit:
        raise DomainError(
            400,
            "Não é possível alterar a unidade de medida de um produto que já possui histórico de movimentações.",
        )

    try:
        min_stock = validate_quantity_for_unit(
            payload.min_stock, payload.unit, allow_zero=True
        )
        safety_stock = validate_quantity_for_unit(
            payload.safety_stock, payload.unit, allow_zero=True
        )
    except ValueError as exc:
        raise DomainError(422, str(exc)) from exc

    product.name = payload.name
    product.sku = payload.sku
    product.barcode = payload.barcode
    product.description = payload.description
    product.category_id = payload.category_id
    product.unit = payload.unit
    product.unit_cost = payload.unit_cost
    product.min_stock = min_stock
    product.safety_stock = safety_stock
    product.location = payload.location
    product.preferred_supplier_id = payload.preferred_supplier_id
    product.lead_time_days = payload.lead_time_days
    product.updated_at = datetime.now(timezone.utc)

    db.commit()
    return get_product(db, product.id)


def set_product_status(db: Session, product_id: int, *, is_active: bool) -> ProductOut:
    """Ativa ou inativa um produto preservando todo o histórico."""
    product = db.get(Product, product_id)
    if not product:
        raise DomainError(404, "Produto não encontrado.")
    product.is_active = is_active
    product.updated_at = datetime.now(timezone.utc)
    db.commit()
    return get_product(db, product.id)
