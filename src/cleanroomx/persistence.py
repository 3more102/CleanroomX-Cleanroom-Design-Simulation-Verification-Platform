from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Callable


def atomic_write_text(
    path: str | Path,
    text: str,
    *,
    before_replace: Callable[[], None] | None = None,
) -> Path:
    """Atomically replace UTF-8 text through a same-directory temporary file.

    The temporary file is flushed and fsynced before replacement. An optional
    pre-replace callback supports optimistic concurrency checks without exposing
    a partially written destination.
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())

        if before_replace is not None:
            before_replace()
        temp_path.replace(destination)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return destination
