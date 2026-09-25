from __future__ import annotations

from collections.abc import Callable
import errno
import os
from pathlib import Path
import stat
import tempfile


_UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS = {
    code
    for code in (
        getattr(errno, "EINVAL", None),
        getattr(errno, "ENOTSUP", None),
        getattr(errno, "EOPNOTSUPP", None),
        getattr(errno, "EBADF", None),
    )
    if code is not None
}


def _sync_directory(directory: Path) -> None:
    """Persist a directory-entry update when directory fsync is supported."""

    if os.name == "nt":
        return

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            if exc.errno not in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS:
                raise
    finally:
        os.close(descriptor)


def atomic_write_text(
    path: str | Path,
    text: str,
    *,
    before_replace: Callable[[], None] | None = None,
) -> Path:
    """Crash-safely replace a UTF-8 text file.

    The payload is written to a same-directory temporary file, flushed and
    fsynced before replacement. The optional before_replace callback runs after
    the temporary file is durable but immediately before the atomic replace,
    allowing guarded project saves to re-check external-revision preconditions.

    Existing POSIX permission bits are retained. After replacement, the parent
    directory is fsynced where supported so the directory-entry update is also
    durable. If replacement fails or execution is interrupted beforehand, the
    previous destination remains untouched and the temporary file is removed.

    A real post-replace directory-sync error is surfaced because durability
    could not be confirmed even though the new file may already be visible.
    """

    if not isinstance(text, str):
        raise TypeError("atomic_write_text text must be a string")

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    existing_mode: int | None = None
    try:
        existing_mode = stat.S_IMODE(destination.stat().st_mode)
    except FileNotFoundError:
        pass

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
            if existing_mode is not None and hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), existing_mode)
            handle.flush()
            os.fsync(handle.fileno())

        if existing_mode is not None and not hasattr(os, "fchmod"):
            os.chmod(temp_path, existing_mode)

        if before_replace is not None:
            before_replace()

        temp_path.replace(destination)
        temp_path = None
        _sync_directory(destination.parent)
    except BaseException:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise

    return destination
