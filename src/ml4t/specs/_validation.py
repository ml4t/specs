"""Shared validation helpers for portable contract values."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime


def require_fields(value: Mapping[str, object], *names: str) -> None:
    missing = sorted(name for name in names if name not in value)
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")


def non_empty(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{name} must be a number")
    try:
        result = float(value)
    except OverflowError:
        raise ValueError(f"{name} must be finite") from None
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(UTC)
