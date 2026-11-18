"""Importação segura de séries históricas via CSV para análise e IA."""

import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Product
from app.models.historical import HistoricalImportBatch, HistoricalMovement
from app.models.user import User
from app.schemas.ai import (
    ImportBatchSummaryOut,
    ImportConfirmOut,
    ImportPreviewOut,
    ImportRowErrorOut,
    ImportValidRowPreview,
)
from app.services.exceptions import DomainError
from app.services.units import quantize_money, validate_quantity_for_unit


SAO_PAULO_TZ = ZoneInfo("America/Sao_Paulo")

ALLOWED_REASONS_BY_TYPE: dict[str, set[str]] = {
    "ENTRADA": {"RECEBIMENTO", "SALDO_INICIAL"},
    "SAIDA": {"VENDA", "CONSUMO", "PERDA", "AVARIA", "OUTRO"},
    "AJUSTE": {"AJUSTE_POSITIVO", "AJUSTE_NEGATIVO"},
}


def generate_historical_template_csv() -> bytes:
    """Gera o modelo CSV oficial para importação de histórico analítico."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=",", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(
        [
            "data_hora",
            "sku",
            "tipo_movimentacao",
            "motivo",
            "quantidade",
            "unidade",
            "custo_unitario",
            "fornecedor",
            "data_pedido",
            "data_recebimento",
            "saldo_fechamento_informado",
            "ruptura_dia",
            "sintetico",
        ]
    )
    writer.writerow(
        [
            "2026-09-01 09:00:00",
            "EXEMPLO-SKU-01",
            "ENTRADA",
            "RECEBIMENTO",
            "50",
            "UN",
            "12.50",
            "Fornecedor Exemplo Ltda",
            "2026-08-25",
            "2026-09-01",
            "50",
            "nao",
            "sim",
        ]
    )
    writer.writerow(
        [
            "2026-09-02 15:30:00",
            "EXEMPLO-SKU-01",
            "SAIDA",
            "VENDA",
            "8",
            "UN",
            "",
            "",
            "",
            "",
            "42",
            "nao",
            "sim",
        ]
    )
    return buf.getvalue().encode("utf-8-sig")


def _decode_csv_text(raw_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DomainError(400, "Não foi possível decodificar o arquivo CSV (use UTF-8 ou Latin-1).")


def _parse_datetime(value: str) -> datetime:
    text = value.strip()
    if not text:
        raise ValueError("Data/hora obrigatória.")
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=SAO_PAULO_TZ).astimezone(timezone.utc)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=SAO_PAULO_TZ)
        return dt.astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError(
            f"Formato de data/hora inválido ('{text}'). Use AAAA-MM-DD HH:MM:SS ou DD/MM/AAAA HH:MM."
        ) from exc


def _parse_optional_date(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Data inválida ('{text}'). Use AAAA-MM-DD ou DD/MM/AAAA.")


def _parse_optional_bool(value: str) -> bool | None:
    text = value.strip().lower()
    if not text:
        return None
    if text in ("sim", "s", "true", "1", "yes"):
        return True
    if text in ("nao", "não", "n", "false", "0", "no"):
        return False
    raise ValueError(f"Valor booleano inválido ('{value}'). Use sim ou nao.")


def _parse_decimal(value: str) -> Decimal:
    text = value.strip().replace(",", ".")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Número inválido ('{value}').") from exc


def _compute_row_hash(row_dict: dict) -> str:
    canonical = "|".join(
        [
            row_dict["occurred_at"],
            row_dict["sku"],
            row_dict["movement_type"],
            row_dict["reason_code"],
            row_dict["quantity"],
            row_dict["unit_snapshot"],
            row_dict.get("supplier_name") or "",
            row_dict.get("order_date") or "",
            row_dict.get("received_date") or "",
            row_dict.get("closing_stock_reported") or "",
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def preview_historical_csv(
    db: Session,
    *,
    user: User,
    filename: str,
    content_bytes: bytes,
) -> ImportPreviewOut:
    """Valida um arquivo CSV histórico, gera prévia e detecta duplicidades sem alterar saldos."""
    if not content_bytes:
        raise DomainError(400, "O arquivo CSV enviado está vazio.")

    file_sha256 = hashlib.sha256(content_bytes).hexdigest()
    already_imported = (
        db.scalar(
            select(HistoricalImportBatch.id).where(
                HistoricalImportBatch.file_sha256 == file_sha256,
                HistoricalImportBatch.status == "CONFIRMED",
            )
        )
        is not None
    )

    text = _decode_csv_text(content_bytes)
    first_line = text.splitlines()[0] if text.splitlines() else ""
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    required_cols = {"data_hora", "sku", "tipo_movimentacao", "motivo", "quantidade", "unidade"}
    header_cols = {col.strip().lower() for col in (reader.fieldnames or []) if col}
    missing = sorted(required_cols - header_cols)
    if missing:
        raise DomainError(
            422,
            f"Colunas obrigatórias ausentes no CSV: {', '.join(missing)}. Baixe o modelo oficial.",
        )

    products_by_sku = {
        p.sku: p for p in db.scalars(select(Product)).all()
    }
    existing_hashes = set(db.scalars(select(HistoricalMovement.external_row_hash)).all())
    seen_in_file: set[str] = set()

    valid_rows: list[dict] = []
    errors: list[ImportRowErrorOut] = []
    duplicate_rows = 0
    total_rows = 0
    batch_has_synthetic = False

    for line_idx, raw_row in enumerate(reader, start=2):
        # Ignora linhas totalmente em branco
        if not any((v or "").strip() for v in raw_row.values()):
            continue

        total_rows += 1
        row = {
            (k.strip().lower() if k else ""): (v.strip() if v is not None else "")
            for k, v in raw_row.items()
        }
        sku = row.get("sku", "").upper()

        try:
            occurred_at = _parse_datetime(row.get("data_hora", ""))
            if not sku or sku not in products_by_sku:
                raise ValueError(f"SKU '{sku or '(vazio)'}' não encontrado no cadastro de produtos.")
            product = products_by_sku[sku]

            mv_type = row.get("tipo_movimentacao", "").upper()
            if mv_type not in ALLOWED_REASONS_BY_TYPE:
                raise ValueError(
                    f"tipo_movimentacao inválido ('{mv_type}'). Use ENTRADA, SAIDA ou AJUSTE."
                )

            reason = row.get("motivo", "").upper()
            if reason not in ALLOWED_REASONS_BY_TYPE[mv_type]:
                allowed = ", ".join(sorted(ALLOWED_REASONS_BY_TYPE[mv_type]))
                raise ValueError(
                    f"Motivo '{reason}' incompatível com {mv_type}. Permitidos: {allowed}."
                )

            unit = row.get("unidade", "").upper()
            if unit != product.unit:
                raise ValueError(
                    f"Unidade '{unit}' diverge da unidade cadastrada do produto ({product.unit})."
                )

            qty_raw = _parse_decimal(row.get("quantidade", ""))
            qty = validate_quantity_for_unit(qty_raw, product.unit)

            unit_cost: Decimal | None = None
            if row.get("custo_unitario"):
                cost_dec = quantize_money(_parse_decimal(row["custo_unitario"]))
                if cost_dec < Decimal("0"):
                    raise ValueError("Custo unitário não pode ser negativo.")
                unit_cost = cost_dec

            order_date = _parse_optional_date(row.get("data_pedido", ""))
            received_date = _parse_optional_date(row.get("data_recebimento", ""))
            if order_date and received_date and received_date < order_date:
                raise ValueError("data_recebimento não pode ser anterior a data_pedido.")

            closing_stock_reported: Decimal | None = None
            if row.get("saldo_fechamento_informado"):
                closing_raw = _parse_decimal(row["saldo_fechamento_informado"])
                closing_stock_reported = validate_quantity_for_unit(
                    closing_raw, product.unit, allow_zero=True
                )

            had_stockout = _parse_optional_bool(row.get("ruptura_dia", ""))
            is_synthetic = _parse_optional_bool(row.get("sintetico", ""))
            is_synthetic_flag = bool(is_synthetic) if is_synthetic is not None else False
            if is_synthetic_flag:
                batch_has_synthetic = True

            serialized = {
                "line_number": line_idx,
                "product_id": product.id,
                "sku": product.sku,
                "product_name": product.name,
                "occurred_at": occurred_at.isoformat(),
                "movement_type": mv_type,
                "reason_code": reason,
                "is_demand": mv_type == "SAIDA" and reason in ("VENDA", "CONSUMO"),
                "quantity": str(qty),
                "unit_snapshot": product.unit,
                "unit_cost": str(unit_cost) if unit_cost is not None else None,
                "supplier_name": row.get("fornecedor") or None,
                "order_date": order_date.isoformat() if order_date else None,
                "received_date": received_date.isoformat() if received_date else None,
                "closing_stock_reported": (
                    str(closing_stock_reported) if closing_stock_reported is not None else None
                ),
                "had_stockout": had_stockout,
                "is_synthetic": is_synthetic_flag,
            }
            row_hash = _compute_row_hash(serialized)
            if row_hash in existing_hashes or row_hash in seen_in_file:
                duplicate_rows += 1
                errors.append(
                    ImportRowErrorOut(
                        line_number=line_idx,
                        sku=sku,
                        message="Registro duplicado (já importado anteriormente ou repetido no arquivo).",
                    )
                )
                continue

            seen_in_file.add(row_hash)
            serialized["external_row_hash"] = row_hash
            valid_rows.append(serialized)

        except ValueError as exc:
            errors.append(
                ImportRowErrorOut(
                    line_number=line_idx,
                    sku=sku or None,
                    message=str(exc),
                )
            )

    batch = HistoricalImportBatch(
        filename=filename,
        file_sha256=file_sha256,
        status="PREVIEW",
        total_rows=total_rows,
        valid_rows=len(valid_rows),
        error_rows=len(errors),
        duplicate_rows=duplicate_rows,
        is_synthetic=batch_has_synthetic,
        preview_payload={"rows": valid_rows},
        uploaded_by_id=user.id,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    sample = [
        ImportValidRowPreview(
            line_number=r["line_number"],
            sku=r["sku"],
            product_name=r["product_name"],
            occurred_at=datetime.fromisoformat(r["occurred_at"]),
            movement_type=r["movement_type"],
            reason_code=r["reason_code"],
            quantity=Decimal(r["quantity"]),
            unit_snapshot=r["unit_snapshot"],
            unit_cost=Decimal(r["unit_cost"]) if r["unit_cost"] is not None else None,
            is_demand=r["is_demand"],
            is_synthetic=r["is_synthetic"],
        )
        for r in valid_rows[:20]
    ]

    return ImportPreviewOut(
        batch_id=batch.id,
        filename=batch.filename,
        file_sha256=batch.file_sha256,
        file_already_imported=already_imported,
        status=batch.status,
        total_rows=batch.total_rows,
        valid_rows=batch.valid_rows,
        error_rows=batch.error_rows,
        duplicate_rows=batch.duplicate_rows,
        is_synthetic=batch.is_synthetic,
        errors=errors,
        sample_valid_rows=sample,
        notice=(
            "Importação exclusivamente analítica: a confirmação gravará apenas a base histórica de estudo "
            "e NÃO alterará o saldo atual dos produtos em estoque."
        ),
    )


def confirm_historical_import(db: Session, *, batch_id: int) -> ImportConfirmOut:
    """Persiste as linhas válidas do lote na base analítica sem alterar o saldo operacional."""
    batch = db.get(HistoricalImportBatch, batch_id)
    if not batch:
        raise DomainError(404, "Lote de importação não encontrado.")
    if batch.status == "CONFIRMED":
        raise DomainError(409, "Este lote de importação já foi confirmado anteriormente.")

    rows = batch.preview_payload.get("rows", [])
    if not rows:
        raise DomainError(
            400, "Não há linhas válidas para importar neste lote. Corrija o arquivo e envie novamente."
        )

    existing_hashes = set(db.scalars(select(HistoricalMovement.external_row_hash)).all())
    inserted = 0
    for r in rows:
        row_hash = r["external_row_hash"]
        if row_hash in existing_hashes:
            continue
        existing_hashes.add(row_hash)
        db.add(
            HistoricalMovement(
                batch_id=batch.id,
                external_row_hash=row_hash,
                product_id=r["product_id"],
                occurred_at=datetime.fromisoformat(r["occurred_at"]),
                movement_type=r["movement_type"],
                reason_code=r["reason_code"],
                is_demand=r["is_demand"],
                quantity=Decimal(r["quantity"]),
                unit_snapshot=r["unit_snapshot"],
                unit_cost=Decimal(r["unit_cost"]) if r["unit_cost"] is not None else None,
                supplier_name=r["supplier_name"],
                order_date=date.fromisoformat(r["order_date"]) if r["order_date"] else None,
                received_date=(
                    date.fromisoformat(r["received_date"]) if r["received_date"] else None
                ),
                closing_stock_reported=(
                    Decimal(r["closing_stock_reported"])
                    if r["closing_stock_reported"] is not None
                    else None
                ),
                had_stockout=r["had_stockout"],
                is_synthetic=r["is_synthetic"],
            )
        )
        inserted += 1

    if inserted == 0:
        raise DomainError(
            409, "Todos os registros deste lote já constavam na base histórica."
        )

    now = datetime.now(timezone.utc)
    batch.status = "CONFIRMED"
    batch.confirmed_at = now
    db.commit()
    db.refresh(batch)

    return ImportConfirmOut(
        batch_id=batch.id,
        status=batch.status,
        inserted_rows=inserted,
        confirmed_at=now,
        notice=(
            "Importação histórica concluída com sucesso. "
            "O saldo operacional atual dos produtos permaneceu inalterado."
        ),
    )


def list_import_batches(db: Session, *, limit: int = 20) -> list[ImportBatchSummaryOut]:
    """Lista os lotes de importação recentes."""
    batches = db.scalars(
        select(HistoricalImportBatch)
        .order_by(HistoricalImportBatch.created_at.desc(), HistoricalImportBatch.id.desc())
        .limit(limit)
    ).all()
    return [
        ImportBatchSummaryOut(
            id=b.id,
            filename=b.filename,
            status=b.status,
            total_rows=b.total_rows,
            valid_rows=b.valid_rows,
            error_rows=b.error_rows,
            duplicate_rows=b.duplicate_rows,
            is_synthetic=b.is_synthetic,
            created_at=b.created_at,
            confirmed_at=b.confirmed_at,
        )
        for b in batches
    ]
