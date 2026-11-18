"""Testes de dashboard, relatórios CSV e preparação de dados para IA."""

from decimal import Decimal
import io

from fastapi.testclient import TestClient
import pandas as pd
from sqlalchemy.orm import Session

from app.ai.replenishment import (
    compute_effective_coverage_days,
    compute_replenishment_quantity,
)
from app.models.inventory import StockoutPeriod


def test_dashboard_reports_and_stockout_and_ai_exports(
    client: TestClient,
    admin_headers: dict[str, str],
    db_session: Session,
) -> None:
    cat = client.post(
        "/api/categories", headers=admin_headers, json={"name": "Geral"}
    ).json()

    p1 = client.post(
        "/api/products",
        headers=admin_headers,
        json={
            "name": "Produto UN",
            "sku": "AI-UN-01",
            "category_id": cat["id"],
            "unit": "UN",
            "unit_cost": "10.00",
            "min_stock": "5",
            "safety_stock": "2",
            "lead_time_days": 10,
        },
    ).json()

    p2 = client.post(
        "/api/products",
        headers=admin_headers,
        json={
            "name": "Produto KG",
            "sku": "AI-KG-02",
            "category_id": cat["id"],
            "unit": "KG",
            "unit_cost": "20.00",
            "min_stock": "10.000",
        },
    ).json()

    # Entrada e ruptura no p1 (entra 4, vende 4 -> saldo 0 abre ruptura, depois entra 3 -> fecha ruptura)
    client.post(
        "/api/movements/entry",
        headers=admin_headers,
        json={"product_id": p1["id"], "quantity": "4", "reason_code": "SALDO_INICIAL"},
    )
    client.post(
        "/api/movements/exit",
        headers=admin_headers,
        json={"product_id": p1["id"], "quantity": "4", "reason_code": "VENDA"},
    )
    # Período de ruptura deve estar aberto
    open_so = db_session.query(StockoutPeriod).filter_by(product_id=p1["id"]).all()
    assert len(open_so) == 1
    assert open_so[0].ended_at is None

    # Nova entrada fecha o período de ruptura
    client.post(
        "/api/movements/entry",
        headers=admin_headers,
        json={
            "product_id": p1["id"],
            "quantity": "3",
            "reason_code": "RECEBIMENTO",
            "unit_cost": "11.50",
            "order_date": "2026-11-01",
            "received_date": "2026-11-10",
        },
    )
    db_session.expire_all()
    closed_so = db_session.query(StockoutPeriod).filter_by(product_id=p1["id"]).all()
    assert closed_so[0].ended_at is not None

    # Perda no p2 não deve contar como demanda
    client.post(
        "/api/movements/entry",
        headers=admin_headers,
        json={"product_id": p2["id"], "quantity": "5.000", "reason_code": "SALDO_INICIAL"},
    )
    client.post(
        "/api/movements/exit",
        headers=admin_headers,
        json={"product_id": p2["id"], "quantity": "1.500", "reason_code": "PERDA"},
    )

    # Dashboard: valor estimado = 3 * 10.00 + 3.5 * 20.00 = 100.00
    dash = client.get("/api/dashboard?days=30", headers=admin_headers).json()
    assert Decimal(dash["estimated_stock_value_brl"]) == Decimal("100.00")
    assert len(dash["unit_summaries"]) == 2
    assert len(dash["replenishment_list"]) == 2

    # Relatório CSV respeitando filtro de busca
    csv_res = client.get(
        "/api/reports/current-stock?search=AI-KG-02&export=csv",
        headers=admin_headers,
    )
    assert csv_res.status_code == 200
    assert "AI-KG-02" in csv_res.text
    assert "AI-UN-01" not in csv_res.text

    # Importação CSV histórica para estudo (NÃO altera saldo operacional)
    csv_content = "\n".join(
        [
            "data_hora,sku,tipo_movimentacao,motivo,quantidade,unidade,custo_unitario,fornecedor,data_pedido,data_recebimento,saldo_fechamento_informado,ruptura_dia,sintetico",
            "2026-10-01 10:00:00,AI-UN-01,SAIDA,VENDA,2,UN,,, , ,5,nao,sim",
            "2026-10-02 10:00:00,AI-UN-01,SAIDA,PERDA,1,UN,,, , ,4,nao,sim",
            "2026-10-02 10:00:00,AI-UN-01,SAIDA,VENDA,1.5,UN,,, , ,4,nao,sim",
            "2026-10-03 10:00:00,SKU-INEXISTENTE,SAIDA,VENDA,1,UN,,, , ,0,nao,sim",
        ]
    )
    preview_res = client.post(
        "/api/ai/imports/preview",
        headers=admin_headers,
        files={"file": ("hist.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert preview_res.status_code == 200
    preview = preview_res.json()
    assert preview["valid_rows"] == 2
    assert preview["error_rows"] == 2

    confirm_res = client.post(
        f"/api/ai/imports/{preview['batch_id']}/confirm",
        headers=admin_headers,
    )
    assert confirm_res.status_code == 200
    assert confirm_res.json()["inserted_rows"] == 2

    # Saldo operacional do produto AI-UN-01 continua exatamente 3
    p1_after = client.get(f"/api/products/{p1['id']}", headers=admin_headers).json()
    assert Decimal(p1_after["current_stock"]) == Decimal("3.000")

    # Exportação da série diária em CSV legível pelo pandas
    daily_csv = client.get("/api/ai/exports/daily-series", headers=admin_headers)
    assert daily_csv.status_code == 200
    df = pd.read_csv(io.BytesIO(daily_csv.content))
    assert "observed_demand_qty" in df.columns
    assert "losses_damages_qty" in df.columns
    assert "availability_status" in df.columns

    # No dia 2026-10-01 só houve VENDA 2 -> observed_demand_qty == 2
    d1 = df[(df["sku"] == "AI-UN-01") & (df["date"] == "2026-10-01")].iloc[0]
    assert d1["observed_demand_qty"] == 2.0
    # No dia 2026-10-02 só houve PERDA 1 -> observed_demand_qty == 0 e losses_damages_qty == 1
    d2 = df[(df["sku"] == "AI-UN-01") & (df["date"] == "2026-10-02")].iloc[0]
    assert d2["observed_demand_qty"] == 0.0
    assert d2["losses_damages_qty"] == 1.0

    # Sugestões de compra: padrão sem modelo vs simulação explícita
    no_model = client.get(
        "/api/ai/purchase-suggestions?horizon_days=30&simulate=false",
        headers=admin_headers,
    ).json()
    assert no_model["model_connected"] is False
    assert no_model["items"] == []

    sim = client.get(
        "/api/ai/purchase-suggestions?horizon_days=30&simulate=true",
        headers=admin_headers,
    ).json()
    assert sim["is_simulated"] is True
    assert len(sim["items"]) == 2
    assert sim["items"][0]["prediction_interval_low"] is None


def test_replenishment_avoids_double_counting() -> None:
    assert compute_effective_coverage_days(horizon_days=30, lead_time_days=10) == 30
    assert compute_effective_coverage_days(horizon_days=10, lead_time_days=18) == 18

    qty = compute_replenishment_quantity(
        predicted_demand_effective_window=Decimal("24.2"),
        current_stock=Decimal("10"),
        safety_stock=Decimal("5"),
        open_purchase_orders_qty=Decimal("4"),
        unit="UN",
    )
    # 24.2 + 5 - (10 + 4) = 15.2 -> ceil para UN = 16
    assert qty == Decimal("16.000")
