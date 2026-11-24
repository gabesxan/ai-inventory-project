"""Check the shared API-01 fixtures without connecting to a database."""

import json
from pathlib import Path

import pytest

from app.schemas.reports import (
    ComparisonRow,
    ImportedHistoryRow,
    ImportQualityRow,
    InventoryExceptionRow,
    LegacyImportPreview,
    ReplenishmentRow,
    ReportError,
    VersionedReport,
)


FIXTURES_PATH = Path(__file__).resolve().parents[2] / "docs/contracts/report-v1/fixtures.json"
FIXTURES = json.loads(FIXTURES_PATH.read_text())


@pytest.mark.parametrize(
    ("name", "schema"),
    [
        ("ready", VersionedReport[ReplenishmentRow]),
        ("calculating", VersionedReport[ReplenishmentRow]),
        ("insufficient_data", VersionedReport[ReplenishmentRow]),
        ("stale", VersionedReport[ReplenishmentRow]),
        ("empty", VersionedReport[ReplenishmentRow]),
        ("forbidden", ReportError),
        ("imported_history", VersionedReport[ImportedHistoryRow]),
        ("comparison", VersionedReport[ComparisonRow]),
        ("inventory_exceptions", VersionedReport[InventoryExceptionRow]),
        ("import_quality", VersionedReport[ImportQualityRow]),
        ("import_preview", LegacyImportPreview),
    ],
)
def test_shared_fixture_round_trips_without_losing_precision_or_fields(name, schema):
    fixture = FIXTURES[name]
    body = fixture["body"]
    result = schema.model_validate(body)
    assert result.model_dump(mode="json") == body
    if isinstance(result, VersionedReport):
        assert fixture["status_code"] == 200
        assert result.total == len(result.items)
    if schema is ReportError:
        assert fixture["status_code"] == 403


def test_replenishment_fixtures_preserve_provenance_across_statuses():
    states = ("ready", "calculating", "insufficient_data", "stale", "empty")
    path = "/api/reports/replenishment"
    for state in states:
        assert FIXTURES[state]["path"] == path
        assert FIXTURES[state]["body"]["status"] == state
    assert FIXTURES["forbidden"]["path"] == path
    assert FIXTURES["stale"]["body"]["items"] == FIXTURES["ready"]["body"]["items"]
    assert FIXTURES["ready"]["body"]["items"][0]["source"] == "synthetic"
    for state in ("calculating", "insufficient_data", "empty"):
        assert FIXTURES[state]["body"]["items"] == []
