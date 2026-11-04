"""Query-parameter parsing and validation for the telemetry search endpoint."""

from typing import Optional

from fastapi import HTTPException, status

from app.schemas.telemetry import DEFAULT_COLUMN_KEYS, VALID_COLUMN_KEYS

SORT_FIELD_MAP = {
    "timestamp": "@timestamp",
    "url": "attributes.url.keyword",
    "latency": "attributes.total_time_ms",
    "status_code": "attributes.status_code",
}


def validate_metadata_and_sort_params(
    metadata_key: Optional[str],
    metadata_value: Optional[str],
    sort_by: Optional[str],
    sort_order: Optional[str],
) -> None:
    if (metadata_key is None) != (metadata_value is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="metadata_key and metadata_value must be given together",
        )
    if sort_by is not None and sort_by not in SORT_FIELD_MAP:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"sort_by must be one of: {', '.join(SORT_FIELD_MAP)}",
        )
    if sort_order is not None and sort_order not in {"asc", "desc"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="sort_order must be 'asc' or 'desc'",
        )


def parse_columns(columns: Optional[str]) -> frozenset:
    if columns:
        requested_keys = {k.strip() for k in columns.split(",") if k.strip()}
        unknown = requested_keys - VALID_COLUMN_KEYS
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown column keys: {', '.join(sorted(unknown))}. Valid keys: {', '.join(sorted(VALID_COLUMN_KEYS))}",
            )
        return frozenset(requested_keys)
    return DEFAULT_COLUMN_KEYS


def parse_status_codes(status_code: Optional[str]) -> list:
    status_code_list: list[int] = []
    if not status_code:
        return status_code_list
    raw_codes = [c.strip() for c in status_code.split(",") if c.strip()]
    if len(raw_codes) > 10:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status_code accepts at most 10 values",
        )
    for c in raw_codes:
        try:
            code_int = int(c)
            if not (100 <= code_int <= 599):
                raise ValueError()
            status_code_list.append(code_int)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status_code value '{c}': must be an integer 100-599",
            )
    return status_code_list
