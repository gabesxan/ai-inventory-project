"""DB-04 · manifest validation on FIXTURE extracts (synthetic, same layout as db04_export.py)."""
import csv
import hashlib
import io
import json
import shutil
from pathlib import Path

import pytest

from legacy.manifest import ManifestError, compare, load_ready, validate


def _write_extract(d: Path, rows_by_table, chunk_rows=2):
    tables = {}
    for table, (cols, rows) in rows_by_table.items():
        (d / table).mkdir(parents=True)
        chunks, kh = [], hashlib.sha256()
        parts = [rows[i:i + chunk_rows] for i in range(0, len(rows), chunk_rows)] or [[]]
        for n, part in enumerate(parts, 1):
            rel = f"{table}/part-{n:05d}.csv"
            buf = io.StringIO()
            w = csv.writer(buf, lineterminator="\n")
            w.writerow(cols)
            w.writerows(part)
            data = buf.getvalue().encode("utf-8")
            (d / rel).write_bytes(data)
            for r in part:
                kh.update(f"{r[0]}\n".encode("ascii"))
            chunks.append({"file": rel, "rows": len(part), "sha256": hashlib.sha256(data).hexdigest(),
                           "bytes": len(data), "first_key": part[0][0] if part else None,
                           "last_key": part[-1][0] if part else None})
        tables[table] = {"order_key": cols[0], "columns": [{"name": c, "type": "integer" if c == "ID" else "varchar"} for c in cols],
                         "row_count": len(rows), "key_digest": kh.hexdigest(), "chunks": chunks}
    (d / "manifest.json").write_text(json.dumps({"format_version": 1, "tables": tables}))
    return d


FIXTURE = {
    "PRODUTOS": (["ID", "DESCRICAO"], [["1", "AÇÚCAR 1KG"], ["2", "CAFÉ"], ["10", "LEITE"]]),
    "PEDIDOS": (["ID", "S_STATUS"], []),
}


@pytest.fixture
def extract(tmp_path):
    return _write_extract(tmp_path / "run", FIXTURE)


def test_valid_fixture_passes_and_gate_returns_manifest(extract):
    m = load_ready(extract)
    assert m["tables"]["PRODUTOS"]["row_count"] == 3
    assert m["tables"]["PEDIDOS"]["row_count"] == 0  # empty table proven by a header-only chunk


def test_missing_file_is_named(extract):
    (extract / "PRODUTOS/part-00002.csv").unlink()
    with pytest.raises(ManifestError) as e:
        validate(extract)
    assert "missing: PRODUTOS/part-00002.csv" in e.value.errors


def test_changed_file_is_named(extract):
    p = extract / "PRODUTOS/part-00001.csv"
    p.write_text(p.read_text(encoding="utf-8").replace("CAFÉ", "CAFE"), encoding="utf-8")
    with pytest.raises(ManifestError) as e:
        validate(extract)
    assert any(err.startswith("changed: PRODUTOS/part-00001.csv") for err in e.value.errors)


def test_unexpected_file_is_named(extract):
    (extract / "PRODUTOS/part-00099.csv").write_text("ID,DESCRICAO\n")
    with pytest.raises(ManifestError) as e:
        validate(extract)
    assert "unexpected file: PRODUTOS/part-00099.csv" in e.value.errors


def test_incomplete_export_without_manifest_is_rejected(extract):
    (extract / "manifest.json").unlink()
    with pytest.raises(ManifestError) as e:
        load_ready(extract)
    assert e.value.errors[0].startswith("missing: manifest.json")


def test_manifest_row_count_tampering_is_named(extract):
    m = json.loads((extract / "manifest.json").read_text())
    m["tables"]["PRODUTOS"]["chunks"][1]["rows"] = 5
    (extract / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(ManifestError) as e:
        validate(extract)
    assert any("row count mismatch: PRODUTOS/part-00002.csv" in err for err in e.value.errors)


def test_out_of_order_keys_are_rejected(tmp_path):
    bad = {"PRODUTOS": (["ID", "DESCRICAO"], [["2", "B"], ["1", "A"]])}
    d = _write_extract(tmp_path / "bad", bad)
    with pytest.raises(ManifestError) as e:
        validate(d)
    assert any("order key not increasing in PRODUTOS/part-00001.csv" in err for err in e.value.errors)


def test_numeric_keys_compare_numerically_across_chunks(extract):
    validate(extract)  # "10" after "2" is increasing as an integer key


def test_compare_identical_exports(tmp_path, extract):
    other = tmp_path / "run2"
    shutil.copytree(extract, other)
    res = compare(extract, other)
    assert all(same_keys and same_sums for _, same_keys, same_sums in res.values())


def test_decimal_without_declared_scale_is_rejected(tmp_path):
    d = _write_extract(tmp_path / "dec", {"ITENS": (["ID", "QTD"], [["1", "2.5000"], ["2", "3.5"]])})
    m = json.loads((d / "manifest.json").read_text())
    m["tables"]["ITENS"]["columns"][1] = {"name": "QTD", "type": "decimal", "scale": 4}
    (d / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(ManifestError) as e:
        validate(d)
    assert e.value.errors == ["decimal scale violated in ITENS/part-00001.csv column QTD at key 2"]
