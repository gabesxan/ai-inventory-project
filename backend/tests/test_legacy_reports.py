import csv
import io

import pytest
from sqlalchemy import text

from app.models.catalog import Category, Product


@pytest.fixture
def legacy_report_data(db_session):
    category = Category(name="Legacy report")
    db_session.add(category)
    db_session.flush()
    product = Product(name="Item histórico", sku="HIST-TEST", unit="UN", category_id=category.id)
    db_session.add(product)
    db_session.flush()
    db_session.execute(text("""
        INSERT INTO legacy_import_batches (batch_id, source_system, warehouse_key, source_fingerprint, status)
        VALUES ('report-test-batch', 'fixture', 'test-warehouse', 'fixture-report', 'imported')
    """))
    db_session.execute(text("""
        INSERT INTO legacy_history_events
            (batch_id, record_id, warehouse_key, product_id, event_date, event_type,
             event_class, is_demand, quantity, signed_quantity, unit, unit_cost)
        VALUES
            ('report-test-batch', 'A', 'test-warehouse', :id, DATE '2025-07-21',
             'pos_sale', 'sale', true, 2.500, -2.500, 'KG', NULL),
            ('report-test-batch', 'B', 'test-warehouse', :id, DATE '2025-07-21',
             'receipt', 'receipt', false, 3.125, 3.125, 'KG', 5.012345),
            ('report-test-batch', 'C', 'test-warehouse', :id, DATE '2025-07-20',
             'supplier_return', 'return', false, 1.000, -1.000, 'UN', NULL)
    """), {"id": product.id})
    db_session.commit()
    yield product.id
    db_session.execute(text("DELETE FROM legacy_history_events WHERE batch_id = 'report-test-batch'"))
    db_session.execute(text("DELETE FROM legacy_import_batches WHERE batch_id = 'report-test-batch'"))
    db_session.commit()


def test_history_filters_and_csv_share_rows_and_precision(
    client, admin_headers, operator_headers, legacy_report_data
):
    path = "/api/reports/imported-history"
    params = {
        "source": "firebird", "sku": "HIST-TEST", "warehouse": "test-warehouse",
        "start_date": "2025-07-21", "end_date": "2025-07-21",
    }
    assert client.get(path, params=params, headers=operator_headers).status_code == 403
    ready = client.get(path, params=params, headers=admin_headers)
    assert ready.status_code == 200
    items = ready.json()["items"]
    assert [row["event_type"] for row in items] == ["sale", "receipt"]
    assert [row["unit"] for row in items] == ["KG", "KG"]
    assert items[0]["unit_cost"] is None
    assert items[0]["source_date"] is None
    assert items[0]["stock_availability"] == "unknown"
    assert items[1]["unit_cost"] == "5.012345"
    export = client.get(path, params={**params, "export": "csv", "page_size": 1}, headers=admin_headers)
    assert export.status_code == 200
    rows = list(csv.DictReader(io.StringIO(export.content.decode("utf-8-sig"))))
    assert rows == [{key: "" if value is None else str(value) for key, value in row.items()} for row in items]
