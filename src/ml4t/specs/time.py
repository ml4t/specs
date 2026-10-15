"""Runtime-neutral temporal declarations; schedule execution belongs to consumers."""

from __future__ import annotations

from enum import Enum, StrEnum
from typing import Any


class CalendarUnset(Enum):
    """Distinguish an omitted calendar argument from an explicit no-calendar request."""

    UNSET = "unset"


UNSET_CALENDAR = CalendarUnset.UNSET


class WindowUnit(StrEnum):
    """Units consumers must not implicitly interchange when interpreting a window."""

    OBSERVATION = "observation"
    EXPECTED_BAR = "expected_bar"
    SESSION = "session"
    ELAPSED = "elapsed"


class BarGridAnchor(StrEnum):
    """Origin of a fixed bar grid, restarted at each tradable interval's open."""

    SESSION_OPEN = "session_open"


class BarLabel(StrEnum):
    """Boundary represented by a fixed bar's timestamp."""

    LEFT = "left"
    RIGHT = "right"


class PartialBarPolicy(StrEnum):
    """Treatment of the final interval shorter than the declared bar duration."""

    INCLUDE = "include"
    EXCLUDE = "exclude"


_GRID_FIELDS = {
    "bar_grid_anchor": BarGridAnchor,
    "bar_label": BarLabel,
    "partial_bar_policy": PartialBarPolicy,
}


def _validate_calendar(calendar: Any) -> str | None:
    if calendar is None or isinstance(calendar, str) and calendar.strip():
        return calendar
    raise ValueError("calendar must be a non-empty name or None")


def _normalize_time_contract(contract: Any) -> None:
    version = contract.time_contract_version
    if isinstance(version, bool) or version not in (1, 2) or not isinstance(version, int):
        raise ValueError("time_contract_version must be 1 or 2")
    calendar = contract.calendar
    if version == 1:
        if any(getattr(contract, name) is not None for name in _GRID_FIELDS):
            raise ValueError("bar grid declarations require time_contract_version=2")
        if calendar is UNSET_CALENDAR:
            object.__setattr__(contract, "calendar", None)
        return

    if calendar is not UNSET_CALENDAR:
        _validate_calendar(calendar)
    normalized = {}
    for name, enum in _GRID_FIELDS.items():
        value = getattr(contract, name)
        if value is not None:
            try:
                normalized[name] = enum(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"invalid {name}: {value!r}") from exc
    if contract.timestamp_semantics == "bar_close" and contract.bar_label == "left":
        raise ValueError("bar_close timestamp_semantics requires bar_label='right'")
    if contract.timestamp_semantics == "session_label" and normalized:
        raise ValueError("session_label timestamps cannot declare an intraday bar grid")
    for name, value in normalized.items():
        object.__setattr__(contract, name, value)


def _resolve_calendar(
    declaration: str | None | CalendarUnset,
    version: int,
    calendar: str | None | CalendarUnset,
) -> str | None:
    if calendar is not UNSET_CALENDAR:
        return _validate_calendar(calendar)
    if declaration is UNSET_CALENDAR or (version == 1 and declaration is None):
        return "NYSE"
    return _validate_calendar(declaration)


def _serialize_time_contract(data: dict[str, Any]) -> dict[str, Any]:
    if data["time_contract_version"] == 1:
        del data["time_contract_version"]
        for name in _GRID_FIELDS:
            del data[name]
    elif data["calendar"] is UNSET_CALENDAR:
        del data["calendar"]
    return data
