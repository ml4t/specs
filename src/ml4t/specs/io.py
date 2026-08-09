"""Low-level payload I/O for ML4T artifact specifications."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import Any

import yaml

from .base import ArtifactSpec

_SUPPORTED_SUFFIXES = frozenset({".json", ".yaml", ".yml"})
_UMASK_LOCK = Lock()


def _validated_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES:
        choices = ", ".join(sorted(_SUPPORTED_SUFFIXES))
        raise ValueError(f"Spec path extension must be one of: {choices}")
    return suffix


def _normalize_mapping(data: Any) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise ValueError("Spec payload must be a mapping")
    return {str(key): value for key, value in data.items()}


def _new_file_mode() -> int:
    with _UMASK_LOCK:
        current_umask = os.umask(0)
        os.umask(current_umask)
    return 0o666 & ~current_umask


def _destination_mode(path: Path) -> int:
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        return _new_file_mode()


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
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=dest.parent,
            prefix=f".{dest.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            if suffix == ".json":
                json.dump(normalized, temporary, indent=2)
                temporary.write("\n")
            else:
                yaml.safe_dump(normalized, temporary, sort_keys=False)
        temporary_path.chmod(destination_mode)
        temporary_path.replace(dest)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return dest


__all__ = ["read_spec_payload", "write_spec_payload"]
