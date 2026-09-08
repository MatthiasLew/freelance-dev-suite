"""Small, shared primitives for durable local business data."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock


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


@contextmanager
def storage_lock(path: Path, timeout: float = 15.0) -> Iterator[None]:
    """Serialize a read-modify-write transaction across processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path), timeout=timeout):
        yield
