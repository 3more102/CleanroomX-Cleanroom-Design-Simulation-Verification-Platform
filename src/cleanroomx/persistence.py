from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import secrets
import stat
from typing import BinaryIO, Callable


class AtomicWriteVerificationError(OSError):
    """Raised when the destination does not contain the exact bytes just committed."""

    def __init__(
        self,
        path: str | Path,
        *,
        expected_size: int,
        actual_size: int | None,
        expected_sha256: str,
        actual_sha256: str | None,
    ):
        self.path = Path(path)
        self.expected_size = expected_size
        self.actual_size = actual_size
        self.expected_sha256 = expected_sha256
        self.actual_sha256 = actual_sha256
        super().__init__(
            "atomic write verification failed for "
            f"{self.path}: expected {expected_size} bytes/{expected_sha256}, "
            f"observed {actual_size} bytes/{actual_sha256}"
        )


def _destination_mode(destination: Path) -> int | None:
    try:
        mode = destination.stat().st_mode
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(mode):
        raise OSError(f"atomic-write destination is not a regular file: {destination}")
    return stat.S_IMODE(mode)


def _open_exclusive_temp(destination: Path) -> tuple[Path, BinaryIO]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_BINARY", 0)
    for _attempt in range(32):
        candidate = destination.parent / (
            f".{destination.name}.{secrets.token_hex(8)}.tmp"
        )
        try:
            fd = os.open(candidate, flags, 0o666)
        except FileExistsError:
            continue
        try:
            return candidate, os.fdopen(fd, "wb")
        except Exception:
            os.close(fd)
            candidate.unlink(missing_ok=True)
            raise
    raise FileExistsError(
        f"could not allocate a unique temporary file beside {destination}"
    )


def _verify_replaced_bytes(destination: Path, expected: bytes) -> None:
    expected_digest = sha256(expected).hexdigest()
    digest = sha256()
    actual_size = 0
    try:
        with destination.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                actual_size += len(chunk)
                digest.update(chunk)
    except FileNotFoundError as exc:
        raise AtomicWriteVerificationError(
            destination,
            expected_size=len(expected),
            actual_size=None,
            expected_sha256=expected_digest,
            actual_sha256=None,
        ) from exc

    actual_digest = digest.hexdigest()
    if actual_size != len(expected) or actual_digest != expected_digest:
        raise AtomicWriteVerificationError(
            destination,
            expected_size=len(expected),
            actual_size=actual_size,
            expected_sha256=expected_digest,
            actual_sha256=actual_digest,
        )


def _fsync_directory(directory: Path) -> None:
    """Persist a completed rename where the platform exposes directory fsync."""
    if os.name != "posix":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(directory, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(
    path: str | Path,
    payload: bytes,
    *,
    before_replace: Callable[[], None] | None = None,
) -> Path:
    """Durably replace a file and verify the committed bytes before success."""
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = _destination_mode(destination)

    temp_path: Path | None = None
    try:
        temp_path, handle = _open_exclusive_temp(destination)
        with handle:
            handle.write(payload)
            handle.flush()
            if existing_mode is not None:
                os.chmod(temp_path, existing_mode)
            os.fsync(handle.fileno())

        if before_replace is not None:
            before_replace()

        temp_path.replace(destination)
        temp_path = None

        _verify_replaced_bytes(destination, payload)
        _fsync_directory(destination.parent)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise

    return destination


def atomic_write_text(
    path: str | Path,
    text: str,
    *,
    before_replace: Callable[[], None] | None = None,
) -> Path:
    """Durably replace a UTF-8 text file and verify its exact committed bytes."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return atomic_write_bytes(
        path,
        text.encode("utf-8"),
        before_replace=before_replace,
    )
