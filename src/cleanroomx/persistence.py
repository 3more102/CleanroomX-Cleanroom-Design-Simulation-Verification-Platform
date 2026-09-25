from __future__ import annotations

import errno
from hashlib import sha256
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


class AtomicWriteVerificationError(OSError):
    """Raised when staged or committed bytes do not match the requested payload."""

    def __init__(
        self,
        path: str | Path,
        *,
        stage: str,
        expected_size: int,
        expected_sha256: str,
        actual_size: int | None,
        actual_sha256: str | None,
        committed: bool,
    ) -> None:
        self.path = Path(path)
        self.stage = stage
        self.expected_size = expected_size
        self.expected_sha256 = expected_sha256
        self.actual_size = actual_size
        self.actual_sha256 = actual_sha256
        self.committed = committed
        super().__init__(
            f"{stage} verification failed for {self.path}: "
            f"expected {expected_size} bytes / sha256 {expected_sha256}, "
            f"got {actual_size!r} bytes / sha256 {actual_sha256!r}"
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


def _stable_file_sha256(
    path: Path,
    *,
    attempts: int = 3,
) -> tuple[os.stat_result, str]:
    """Hash one stable file revision, rejecting mutation or replacement during read."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    last_error: OSError | None = None
    for _attempt in range(attempts):
        try:
            before = path.stat()
            digest = sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            after = path.stat()
        except OSError as exc:
            last_error = exc
            continue
        if (
            before.st_dev == after.st_dev
            and before.st_ino == after.st_ino
            and before.st_size == after.st_size
            and before.st_mtime_ns == after.st_mtime_ns
        ):
            return after, digest.hexdigest()
        last_error = OSError(f"file changed while verifying: {path}")
    assert last_error is not None
    raise last_error


def _verify_file_payload(
    path: Path,
    payload: bytes,
    *,
    stage: str,
    committed: bool,
) -> None:
    expected_size = len(payload)
    expected_sha256 = sha256(payload).hexdigest()
    try:
        stat_result, actual_sha256 = _stable_file_sha256(path)
    except OSError as exc:
        raise AtomicWriteVerificationError(
            path,
            stage=stage,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            actual_size=None,
            actual_sha256=None,
            committed=committed,
        ) from exc
    if stat_result.st_size != expected_size or actual_sha256 != expected_sha256:
        raise AtomicWriteVerificationError(
            path,
            stage=stage,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            actual_size=stat_result.st_size,
            actual_sha256=actual_sha256,
            committed=committed,
        )


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

        _verify_file_payload(
            temp_path,
            data,
            stage="staged write",
            committed=False,
        )
        if before_replace is not None:
            before_replace()
        temp_path.replace(destination)
        temp_path = None
        try:
            _fsync_directory(destination.parent)
        except OSError as exc:
            raise AtomicWriteDurabilityError(destination, exc) from exc
        _verify_file_payload(
            destination,
            data,
            stage="committed write",
            committed=True,
        )
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
