from __future__ import annotations

import errno
import os
from pathlib import Path
import stat
import tempfile
from typing import Callable


BeforeReplace = Callable[[], None]


class AtomicWriteDurabilityError(OSError):
    """Raised after replacement when directory durability could not be confirmed."""

    def __init__(self, path: str | Path, cause: OSError):
        self.path = Path(path)
        self.cause = cause
        self.committed = True
        super().__init__(
            "atomic replacement completed, but parent-directory durability "
            f"could not be confirmed for {self.path}: {cause}"
        )


_UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS = {
    errno.EINVAL,
    getattr(errno, "ENOTSUP", errno.EINVAL),
    getattr(errno, "EOPNOTSUPP", errno.EINVAL),
}


def _fsync_directory(directory: Path) -> None:
    """Persist a directory-entry update when the filesystem supports it."""
    if os.name != "posix":
        return
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(directory, flags)
    except OSError as exc:
        if exc.errno in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
            return
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            if exc.errno not in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
                raise
    finally:
        os.close(descriptor)


def atomic_write_bytes(
    path: str | Path,
    payload: bytes | bytearray | memoryview,
    *,
    before_replace: BeforeReplace | None = None,
) -> Path:
    """Atomically replace a file with fully flushed bytes.

    The temporary file is created in the destination directory so the final
    replace remains atomic on the same filesystem. Existing POSIX permission
    bits are retained. If writing, flushing, validation, or replacement fails,
    the previous destination is left untouched and the temporary file is
    removed. After a successful replace, the parent directory is fsynced on
    POSIX when supported so the rename itself is durably recorded before success
    is reported. A real post-replace directory-sync failure raises
    AtomicWriteDurabilityError with committed=True because the destination has
    already been replaced; explicit unsupported-filesystem errors are tolerated.
    """
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError("payload must be bytes-like")

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = bytes(payload)

    existing_mode: int | None = None
    try:
        existing_mode = stat.S_IMODE(destination.stat().st_mode)
    except FileNotFoundError:
        pass

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            written = handle.write(data)
            if written != len(data):
                raise OSError(
                    f"short write while persisting {destination}: "
                    f"{written} of {len(data)} bytes"
                )
            if existing_mode is not None and hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), existing_mode)
            handle.flush()
            os.fsync(handle.fileno())

        if before_replace is not None:
            before_replace()
        temp_path.replace(destination)
        temp_path = None
        try:
            _fsync_directory(destination.parent)
        except OSError as exc:
            raise AtomicWriteDurabilityError(destination, exc) from exc
    except BaseException:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    return destination


def atomic_write_text(
    path: str | Path,
    text: str,
    *,
    before_replace: BeforeReplace | None = None,
) -> Path:
    """Atomically replace a UTF-8 text file using deterministic encoded bytes."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return atomic_write_bytes(
        path,
        text.encode("utf-8"),
        before_replace=before_replace,
    )
