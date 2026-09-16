"""Small, shared primitives for durable local business data and schema contracts."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from filelock import FileLock

CURRENT_STATE_SCHEMA_VERSION = "1.0"


class StateError(RuntimeError):
    """Base error for persistent state issues."""


class IncompatibleSchemaError(StateError):
    """Raised when an artifact has an unsupported future schema version."""


class CorruptedStateError(StateError):
    """Raised when an artifact is empty, malformed, or has invalid data types."""


def atomic_write_text(path: Path, content: str) -> None:
    """Replace *path* atomically after flushing the new content to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def atomic_write_json(
    path: Path,
    data: Any,
    indent: int = 2,
    schema_version: str | None = None,
) -> None:
    """Atomically write arbitrary data as formatted JSON.

    If schema_version is explicitly provided and data is a dict without schema_version,
    it is injected. Otherwise, generic JSON data is written structurally unchanged.
    """
    if schema_version is not None and isinstance(data, dict) and "schema_version" not in data:
        data = {"schema_version": schema_version, **data}

    content = json.dumps(data, indent=indent, ensure_ascii=False) + "\n"
    atomic_write_text(path, content)


def atomic_write_state(
    path: Path,
    data: dict[str, Any],
    schema_version: str = CURRENT_STATE_SCHEMA_VERSION,
    indent: int = 2,
) -> None:
    """Atomically write versioned persistent business state, ensuring schema_version is present."""
    atomic_write_json(path, data, indent=indent, schema_version=schema_version)


def safe_read_json(
    path: Path,
    expected_version: str = CURRENT_STATE_SCHEMA_VERSION,
    allow_legacy_without_version: bool = True,
) -> dict[str, Any]:
    """Read and validate a persistent JSON artifact with schema version checks.

    Fail-safe and backwards-aware: legacy files without schema_version are accepted
    and annotated with the default version, while unsupported future versions are rejected.
    """
    if not path.exists():
        raise FileNotFoundError(f"State file not found: {path}")

    try:
        raw_text = path.read_text(encoding="utf-8")
        if not raw_text.strip():
            raise CorruptedStateError(f"State file is empty: {path}")
        data = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as exc:
        raise CorruptedStateError(f"Failed to read state file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise CorruptedStateError(f"Expected JSON object in {path}, got {type(data).__name__}")

    raw_version = data.get("schema_version")
    if raw_version is None:
        if not allow_legacy_without_version:
            raise IncompatibleSchemaError(f"Missing schema_version in {path}")
        data["schema_version"] = CURRENT_STATE_SCHEMA_VERSION
        return data

    version_str = str(raw_version)
    # Check compatibility: major version difference triggers incompatibility
    try:
        file_major = int(version_str.split(".")[0])
        expected_major = int(expected_version.split(".")[0])
        if file_major > expected_major:
            msg = (
                f"Unsupported schema_version '{version_str}' in {path} "
                f"(expected <= {expected_version})"
            )
            raise IncompatibleSchemaError(msg)
    except ValueError as exc:
        raise IncompatibleSchemaError(
            f"Malformed schema_version '{version_str}' in {path}"
        ) from exc

    return data


_active_locks: threading.local = threading.local()


def _get_active_locks() -> dict[str, int]:
    if not hasattr(_active_locks, "held"):
        _active_locks.held = {}
    return _active_locks.held  # type: ignore[no-any-return]


@contextmanager
def storage_lock(path: Path, timeout: float = 15.0) -> Iterator[None]:
    """Serialize a read-modify-write transaction across processes (re-entrant in same thread)."""
    from packages.security.secrets import canonicalize_path

    path.parent.mkdir(parents=True, exist_ok=True)
    canonical = os.path.normcase(os.path.normpath(str(canonicalize_path(path))))
    held = _get_active_locks()

    if held.get(canonical, 0) > 0:
        held[canonical] += 1
        try:
            yield
        finally:
            held[canonical] -= 1
            if held[canonical] <= 0:
                held.pop(canonical, None)
        return

    with FileLock(canonical, timeout=timeout):
        held[canonical] = 1
        try:
            yield
        finally:
            held[canonical] -= 1
            if held[canonical] <= 0:
                held.pop(canonical, None)
