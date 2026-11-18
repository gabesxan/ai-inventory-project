"""Regras de unidades de medida, validação de precisão e política de arredondamento."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import TypedDict


class UnitSpec(TypedDict):
    """Definição de uma unidade de medida suportada."""

    code: str
    label: str
    allow_decimal: bool


UNIT_SPECS: dict[str, UnitSpec] = {
    "UN": {"code": "UN", "label": "Unidade", "allow_decimal": False},
    "CX": {"code": "CX", "label": "Caixa", "allow_decimal": False},
    "PCT": {"code": "PCT", "label": "Pacote", "allow_decimal": False},
    "PAR": {"code": "PAR", "label": "Par", "allow_decimal": False},
    "FD": {"code": "FD", "label": "Fardo", "allow_decimal": False},
    "RL": {"code": "RL", "label": "Rolo", "allow_decimal": False},
    "KG": {"code": "KG", "label": "Quilograma", "allow_decimal": True},
    "G": {"code": "G", "label": "Grama", "allow_decimal": True},
    "L": {"code": "L", "label": "Litro", "allow_decimal": True},
    "ML": {"code": "ML", "label": "Mililitro", "allow_decimal": True},
    "M": {"code": "M", "label": "Metro", "allow_decimal": True},
    "M2": {"code": "M2", "label": "Metro Quadrado", "allow_decimal": True},
}

MONEY_QUANTIZER = Decimal("0.01")
QTY_QUANTIZER = Decimal("0.001")


def normalize_unit(unit: str) -> str:
    """Normaliza e valida o código da unidade de medida."""
    code = (unit or "").strip().upper()
    if code not in UNIT_SPECS:
        allowed = ", ".join(UNIT_SPECS.keys())
        raise ValueError(f"Unidade de medida inválida '{unit}'. Permitidas: {allowed}.")
    return code


def is_discrete_unit(unit: str) -> bool:
    """Indica se a unidade exige quantidades inteiras."""
    code = normalize_unit(unit)
    return not UNIT_SPECS[code]["allow_decimal"]


def quantize_money(value: Decimal | int | float | str) -> Decimal:
    """Arredonda valor monetário para 2 casas decimais com ROUND_HALF_UP."""
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Valor monetário inválido.") from exc
    if not dec.is_finite():
        raise ValueError("Valor monetário deve ser finito.")
    return dec.quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)


def quantize_qty(value: Decimal | int | float | str) -> Decimal:
    """Arredonda quantidade para 3 casas decimais com ROUND_HALF_UP."""
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Quantidade inválida.") from exc
    if not dec.is_finite():
        raise ValueError("Quantidade deve ser finita.")
    return dec.quantize(QTY_QUANTIZER, rounding=ROUND_HALF_UP)


def validate_quantity_for_unit(
    value: Decimal | int | float | str,
    unit: str,
    *,
    allow_zero: bool = False,
) -> Decimal:
    """Valida quantidade quanto a sinal, escala decimal e regra discreta/contínua."""
    code = normalize_unit(unit)
    try:
        raw = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Quantidade numérica inválida.") from exc

    if not raw.is_finite():
        raise ValueError("Quantidade deve ser um número válido.")

    if allow_zero:
        if raw < Decimal("0"):
            raise ValueError("O valor não pode ser negativo.")
    else:
        if raw <= Decimal("0"):
            raise ValueError("A quantidade deve ser maior que zero.")

    if is_discrete_unit(code):
        if raw % Decimal("1") != Decimal("0"):
            raise ValueError(
                f"A unidade '{code}' ({UNIT_SPECS[code]['label']}) aceita apenas quantidades inteiras."
            )
        return raw.quantize(QTY_QUANTIZER, rounding=ROUND_HALF_UP)

    # Unidades fracionárias permitem até 3 casas decimais exatas
    rounded = raw.quantize(QTY_QUANTIZER, rounding=ROUND_HALF_UP)
    if (raw - rounded) != Decimal("0"):
        raise ValueError(
            f"A unidade '{code}' aceita no máximo 3 casas decimais."
        )
    return rounded


def format_quantity(value: Decimal, unit: str) -> str:
    """Formata quantidade respeitando se a unidade é inteira ou fracionária."""
    code = normalize_unit(unit)
    if is_discrete_unit(code):
        return str(int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))
    normalized = value.quantize(QTY_QUANTIZER, rounding=ROUND_HALF_UP)
    text = f"{normalized:.3f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")
