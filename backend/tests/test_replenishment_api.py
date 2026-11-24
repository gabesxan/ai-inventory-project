from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.ai.publication import publish, record_status
from app.models.catalog import Category, Product
from app.models.replenishment import ReplenishmentRun, ReplenishmentSnapshot
from test_replenishment_publication import fixture_suggestion


def test_replenishment_is_admin_only_and_reads_the_last_publication(
    client, db_session, admin_headers, operator_headers
):
    path = "/api/reports/replenishment"
    assert client.get(path).status_code == 401
    denied = client.get(path, headers=operator_headers)
    assert denied.status_code == 403
    assert denied.json() == {"detail": "Acesso restrito a administradores."}
    assert client.get(path, headers=admin_headers).json()["status"] == "empty"

    row = fixture_suggestion()
    record_status(db_session, row.sku, row.warehouse, "calculating")
    db_session.commit()
    assert client.get(path, headers=admin_headers).json()["status"] == "calculating"

    category = Category(name="Suggestion test")
    db_session.add(category)
    db_session.flush()
    product = Product(name=row.product_name, sku=row.sku, unit="UN", category_id=category.id, current_stock=7)
    db_session.add(product)
    db_session.commit()
    row = row.model_copy(update={"generated_at": datetime.now(timezone.utc)})
    run = ReplenishmentRun(
        id=row.model_run_id, sku=row.sku, warehouse=row.warehouse,
        source=row.source, model_version=row.model_version, trained_at=row.trained_at,
        config_sha256="a" * 64, checkpoint_path="/example/checkpoint.pt", configuration={}, evaluation={},
    )
    publish(db_session, run, row, "b" * 64)
    db_session.commit()
    ready = client.get(path, params={"sku": row.sku, "page_size": 1}, headers=admin_headers)
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["items"] == [row.model_dump(mode="json")]
    assert client.get(path, params={"sku": "MISSING"}, headers=admin_headers).json()["total"] == 0
    result_page = client.get(path, params={"page": 2, "page_size": 1}, headers=admin_headers).json()
    assert (result_page["total"], result_page["items"]) == (1, [])
    assert db_session.scalar(select(func.count()).select_from(ReplenishmentSnapshot)) == 1
    db_session.refresh(product)
    assert product.current_stock == Decimal("7.000")

    product.current_stock = Decimal("8")
    db_session.commit()
    stale = client.get(path, headers=admin_headers).json()
    assert stale["status"] == "stale"
    assert stale["items"] == ready.json()["items"]
