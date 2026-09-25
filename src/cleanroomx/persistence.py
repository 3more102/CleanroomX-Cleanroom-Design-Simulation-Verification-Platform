from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import stat
import tempfile


class PersistenceDurabilityError(OSError):
    """A filesystem mutation completed but its directory sync could not be confirmed."""

    def __init__(self, path: str | Path, operation: str, error: OSError):
        self.path = Path(path)
        self.operation = operation
        self.mutation_completed = True
        self.original_error = error
        super().__init__(
            f"{operation} completed for {self.path}, but filesystem durability "
            f"could not be confirmed: {error}"
        )


def _open_directory_sync_fd(directory: Path) -> int | None:
    """Open a directory for metadata fsync where the platform exposes that contract."""
    if os.name == "nt":
        # CPython does not provide a portable Windows directory-handle fsync contract.
        return None
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    return os.open(directory, flags)


def _sync_open_directory(fd: int | None) -> bool:
    if fd is None:
        return False
    os.fsync(fd)
    return True


def atomic_write_text(
    path: str | Path,
    text: str,
    *,
    before_replace: Callable[[], None] | None = None,
) -> Path:
    """Crash-harden a UTF-8 text replacement in the destination directory.

    The staged bytes are exact UTF-8 (no platform newline translation), the staged
    file is flushed and fsynced before replacement, an existing regular file's mode
    is retained, and the parent directory is fsynced after the atomic replacement
    on platforms that expose directory fsync.

    before_replace runs after the staged file is durable but immediately before
    replacement. It is used by project optimistic-write protection.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    existing_mode: int | None = None
    try:
        existing_stat = destination.lstat()
    except FileNotFoundError:
        pass
    else:
        if stat.S_ISREG(existing_stat.st_mode):
            existing_mode = stat.S_IMODE(existing_stat.st_mode)

    directory_fd = _open_directory_sync_fd(destination.parent)
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
            handle.write(text.encode("utf-8"))
            handle.flush()
            if existing_mode is not None:
                os.chmod(temp_path, existing_mode)
            os.fsync(handle.fileno())

        if before_replace is not None:
            before_replace()

        temp_path.replace(destination)
        temp_path = None

        try:
            _sync_open_directory(directory_fd)
        except OSError as exc:
            raise PersistenceDurabilityError(
                destination,
                "atomic replacement",
                exc,
            ) from exc
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    finally:
        if directory_fd is not None:
            os.close(directory_fd)

    return destination


def durable_unlink(path: str | Path, *, missing_ok: bool = False) -> bool:
    """Remove one file and durably flush the parent directory where supported."""
    target = Path(path)
    if missing_ok:
        try:
            target.lstat()
        except FileNotFoundError:
            return False
    directory_fd = _open_directory_sync_fd(target.parent)
    try:
        try:
            target.unlink()
        except FileNotFoundError:
            if not missing_ok:
                raise
            return False

        try:
            _sync_open_directory(directory_fd)
        except OSError as exc:
            raise PersistenceDurabilityError(
                target,
                "file removal",
                exc,
            ) from exc
        return True
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
