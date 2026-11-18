"""Regra de cálculo de quantidade recomendada de compra sem dupla contagem."""

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from app.services.units import QTY_QUANTIZER, is_discrete_unit


def compute_effective_coverage_days(horizon_days: int, lead_time_days: int) -> int:
    """
    Calcula a janela efetiva de cobertura sem contar o prazo de reposição duas vezes.

    Como o horizonte de previsão H e o prazo de reposição L começam ambos na data base t0,
    a cobertura necessária é W = max(H, L), evitando somar D(t0..t0+H) + D(t0..t0+L).
    """
    return max(max(1, horizon_days), max(0, lead_time_days))


def compute_replenishment_quantity(
    *,
    predicted_demand_effective_window: Decimal,
    current_stock: Decimal,
    safety_stock: Decimal,
    open_purchase_orders_qty: Decimal,
    unit: str,
) -> Decimal:
    """
    Calcula Q_rec = max(0, D_efetiva + estoque_seguranca - (saldo_atual + pedidos_abertos)).
    """
    raw_target = predicted_demand_effective_window + safety_stock
    available_plus_pending = current_stock + open_purchase_orders_qty
    net_needed = max(Decimal("0.000"), raw_target - available_plus_pending)

    if net_needed == Decimal("0"):
        return Decimal("0.000")

    if is_discrete_unit(unit):
        # Arredonda para cima no inteiro mais próximo para unidades indivisíveis
        whole = net_needed.quantize(Decimal("1"), rounding=ROUND_CEILING)
        return whole.quantize(QTY_QUANTIZER, rounding=ROUND_HALF_UP)

    return net_needed.quantize(QTY_QUANTIZER, rounding=ROUND_CEILING)
