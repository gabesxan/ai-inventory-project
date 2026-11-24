"""Pagination and CSV serialization for the shared report row contracts."""

import csv
import io
import json
from collections.abc import Iterator
from typing import TypeVar

from fastapi import Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.schemas.reports import VersionedReport
from app.services.report_service import build_csv_bytes


Row = TypeVar("Row", bound=BaseModel)


def report_page(row_type: type[Row], rows: list[Row], page: int, page_size: int) -> VersionedReport[Row]:
    total = len(rows)
    offset = (page - 1) * page_size
    return VersionedReport[row_type](
        items=rows[offset:offset + page_size], total=total, page=page, page_size=page_size,
        total_pages=max(1, (total + page_size - 1) // page_size),
        status="ready" if total else "empty", status_message=None,
    )


def report_csv(row_type: type[Row], rows: list[Row], filename: str) -> Response:
    headers = list(row_type.model_fields)
    values = []
    for row in rows:
        data = row.model_dump(mode="json")
        values.append([
            json.dumps(data[key], ensure_ascii=False, sort_keys=True) if isinstance(data[key], dict) else data[key]
            for key in headers
        ])
    return Response(
        content=build_csv_bytes(headers, values),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def stream_report_csv(row_type: type[Row], rows: Iterator[Row], filename: str) -> StreamingResponse:
    headers = list(row_type.model_fields)

    def encode():
        with io.StringIO() as buffer:
            writer = csv.writer(buffer)
            writer.writerow(headers)
            yield buffer.getvalue().encode("utf-8-sig")
            buffer.seek(0)
            buffer.truncate()
            for row in rows:
                data = row.model_dump(mode="json")
                writer.writerow(data[key] for key in headers)
                if buffer.tell() >= 32_768:
                    yield buffer.getvalue().encode("utf-8")
                    buffer.seek(0)
                    buffer.truncate()
            if buffer.tell():
                yield buffer.getvalue().encode("utf-8")

    return StreamingResponse(
        encode(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
