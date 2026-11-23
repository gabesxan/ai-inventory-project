"""Read a validated DB-04 extract as typed dict rows (shared by DB-05+). Stdlib only."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterator, Optional

from legacy.manifest import iter_rows, load_ready

NULL = "\\N"


class Extract:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser()
        self.manifest = load_ready(self.path)  # rejects incomplete or changed batches

    @property
    def scope(self) -> dict:
        return self.manifest["scope"]

    def columns(self, table: str):
        return self.manifest["tables"][table]["columns"]

    def rows(self, table: str) -> Iterator[Dict[str, str]]:
        names = [c["name"] for c in self.columns(table)]
        for r in iter_rows(self.path, table, self.manifest):
            yield dict(zip(names, r))

    def count(self, table: str) -> int:
        return self.manifest["tables"][table]["row_count"]


def val(v: Optional[str]) -> Optional[str]:
    if v is None or v == NULL:
        return None
    s = v.strip()
    return s if s else None


def dec(v: Optional[str]) -> Optional[Decimal]:
    s = val(v)
    return Decimal(s) if s is not None else None


def num(v: Optional[str]) -> Optional[int]:
    s = val(v)
    return int(s) if s is not None else None
