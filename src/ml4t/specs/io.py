"""Low-level payload I/O for ML4T artifact specifications."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from secrets import token_hex
from typing import Any, TextIO

import yaml

from .base import ArtifactSpec

_SUPPORTED_SUFFIXES = frozenset({".json", ".yaml", ".yml"})


def _validated_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES:
        choices = ", ".join(sorted(_SUPPORTED_SUFFIXES))
        raise ValueError(f"Spec path extension must be one of: {choices}")
    return suffix


def _normalize_mapping(data: Any) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise ValueError("Spec payload must be a mapping")
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        normalized_key = str(key)
        if normalized_key in normalized:
            raise ValueError(f"Spec payload contains colliding key {normalized_key!r}")
        normalized[normalized_key] = value
    return normalized


def _destination_mode(path: Path) -> int | None:
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        return None


def _open_temporary_file(destination: Path) -> tuple[TextIO, Path, int]:
    while True:
        temporary_path = destination.parent / f".{destination.name}.{token_hex(8)}"
        try:
            temporary = temporary_path.open("x", encoding="utf-8")
        except FileExistsError:
            continue
        try:
            creation_mode = stat.S_IMODE(temporary_path.stat().st_mode)
            temporary_path.chmod(0o600)
        except BaseException:
            temporary.close()
            temporary_path.unlink(missing_ok=True)
            raise
        return temporary, temporary_path, creation_mode


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":  # pragma: no cover - Windows has no directory fsync
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_spec_payload(path_or_mapping: str | Path | Mapping[Any, Any]) -> dict[str, Any]:
    """Load a spec payload from YAML/JSON or return a copied mapping."""
    if isinstance(path_or_mapping, Mapping):
        return _normalize_mapping(path_or_mapping)

    path = Path(path_or_mapping)
    suffix = _validated_suffix(path)
    with path.open(encoding="utf-8") as f:
        data = json.load(f) if suffix == ".json" else yaml.safe_load(f)
    return _normalize_mapping({} if data is None else data)


def write_spec_payload(payload: Mapping[Any, Any] | ArtifactSpec, path: str | Path) -> Path:
    """Write a spec payload to YAML or JSON."""
    dest = Path(path)
    suffix = _validated_suffix(dest)
    normalized = (
        payload.to_dict() if isinstance(payload, ArtifactSpec) else _normalize_mapping(payload)
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    destination_mode = _destination_mode(dest)
    temporary_path: Path | None = None
    try:
        temporary, temporary_path, creation_mode = _open_temporary_file(dest)
        with temporary:
            if suffix == ".json":
                json.dump(normalized, temporary, indent=2)
                temporary.write("\n")
            else:
                yaml.safe_dump(normalized, temporary, sort_keys=False)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.chmod(creation_mode if destination_mode is None else destination_mode)
        temporary_path.replace(dest)
        _fsync_directory(dest.parent)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return dest


__all__ = ["read_spec_payload", "write_spec_payload"]
