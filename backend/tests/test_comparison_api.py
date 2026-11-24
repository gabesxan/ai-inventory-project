import csv
import io
from datetime import datetime, timezone

from app.models.replenishment import ReplenishmentRun


def test_comparison_csv_matches_json_filter_and_order(client, db_session, admin_headers, operator_headers):
    path = "/api/reports/comparison"
    now = datetime.now(timezone.utc)
    for source in ("synthetic", "legacy_calibrated"):
        db_session.add(ReplenishmentRun(
            id=source, sku="DEMO-001", warehouse="1", source=source, model_version="dqn-v1",
            trained_at=now, config_sha256="a" * 64, checkpoint_path="/example/checkpoint.pt",
            configuration={}, evaluation={
                "evaluated_at": now.isoformat(),
                "metrics": [
                    {
                        "scenario": scenario, "seed": 30001, "policy": policy,
                        "total_cost": "200.32", "fill_rate": None, "stockout_days": 0,
                        "mean_inventory": "0.50", "order_days": 3,
                    }
                    for scenario in ("demand_spike", "baseline")
                    for policy in ("s_s", "dqn", "base_stock")
                ],
            },
        ))
    db_session.commit()

    params = {"source": "synthetic", "scenario": "baseline", "model_run_id": "synthetic"}
    assert client.get(path, params=params, headers=operator_headers).status_code == 403
    response = client.get(path, params=params, headers=admin_headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert [row["policy"] for row in items] == ["base_stock", "dqn", "s_s"]
    assert all(row["source"] == "synthetic" and row["fill_rate"] is None for row in items)
    assert all(row["trained_at"].endswith("Z") for row in items)

    export = client.get(path, params={**params, "export": "csv", "page_size": 1}, headers=admin_headers)
    assert export.status_code == 200
    rows = list(csv.DictReader(io.StringIO(export.content.decode("utf-8-sig"))))
    assert rows == [{key: "" if value is None else str(value) for key, value in row.items()} for row in items]
