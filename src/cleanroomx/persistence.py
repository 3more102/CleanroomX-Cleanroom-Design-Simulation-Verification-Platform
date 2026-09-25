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
    errno.EBADF,
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


def stable_file_sha256(
    path: str | Path,
    *,
    attempts: int = 3,
) -> tuple[os.stat_result, str]:
    """Hash one stable file revision and reject path/descriptor replacement races."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    source = Path(path)
    last_error: OSError | None = None
    for _attempt in range(attempts):
        try:
            before_path = source.stat()
            digest = sha256()
            with source.open("rb") as handle:
                before_handle = os.fstat(handle.fileno())
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                after_handle = os.fstat(handle.fileno())
            after_path = source.stat()
        except OSError as exc:
            last_error = exc
            continue

        identities = (
            (
                before_path.st_dev,
                before_path.st_ino,
                before_path.st_size,
                before_path.st_mtime_ns,
            ),
            (
                before_handle.st_dev,
                before_handle.st_ino,
                before_handle.st_size,
                before_handle.st_mtime_ns,
            ),
            (
                after_handle.st_dev,
                after_handle.st_ino,
                after_handle.st_size,
                after_handle.st_mtime_ns,
            ),
            (
                after_path.st_dev,
                after_path.st_ino,
                after_path.st_size,
                after_path.st_mtime_ns,
            ),
        )
        if identities[0] == identities[1] == identities[2] == identities[3]:
            return after_path, digest.hexdigest()
        last_error = OSError(f"file changed while verifying: {source}")
    assert last_error is not None
    raise last_error


# Backward-compatible private alias for existing tests/internal callers.
_stable_file_sha256 = stable_file_sha256


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


def _verify_file_digest(
    path: Path,
    *,
    expected_size: int,
    expected_sha256: str,
    stage: str,
    committed: bool,
) -> None:
    try:
        stat_result, actual_sha256 = stable_file_sha256(path)
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


def atomic_publish_staged_file(
    path: str | Path,
    staged_path: str | Path,
    *,
    before_replace: BeforeReplace | None = None,
) -> Path:
    """Publish an already-written sibling file through the canonical atomic path.

    This is intended for streaming producers such as ZIP/report builders that cannot
    efficiently materialize their complete output as one in-memory bytes object.
    The staged file must be in the destination directory so replacement is atomic.
    Its exact byte size and SHA-256 are captured after fsync, rechecked after the
    optional conflict hook, and verified again after replacement.
    """
    destination = Path(path)
    staged = Path(staged_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    destination_parent = destination.parent.resolve(strict=False)
    staged_parent = staged.parent.resolve(strict=False)
    if staged_parent != destination_parent:
        raise ValueError("staged file must be in the destination directory")
    if staged.resolve(strict=False) == destination.resolve(strict=False):
        raise ValueError("staged file must be distinct from destination")

    existing_mode: int | None = None
    try:
        existing_mode = stat.S_IMODE(destination.stat().st_mode)
    except FileNotFoundError:
        pass

    committed = False
    try:
        with staged.open("rb") as handle:
            if existing_mode is not None and hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), existing_mode)
            os.fsync(handle.fileno())

        staged_stat, expected_sha256 = stable_file_sha256(staged)
        expected_size = staged_stat.st_size

        if before_replace is not None:
            before_replace()

        _verify_file_digest(
            staged,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            stage="staged publish",
            committed=False,
        )
        staged.replace(destination)
        committed = True
        try:
            _fsync_directory(destination.parent)
        except OSError as exc:
            raise AtomicWriteDurabilityError(destination, exc) from exc
        _verify_file_digest(
            destination,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            stage="committed publish",
            committed=True,
        )
    except BaseException:
        if not committed:
            staged.unlink(missing_ok=True)
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


def atomic_write_generated(
    path: str | Path,
    generator: Callable[[Path], None],
    *,
    before_replace: BeforeReplace | None = None,
) -> Path:
    """Atomically publish a file produced incrementally at a same-directory temp path.

    This is the shared primitive for potentially large generated engineering outputs
    such as portable ZIP bundles. The generator never writes the destination. After
    it returns, CleanroomX flushes the staged file, records its stable size/SHA-256,
    performs the guarded atomic replacement, fsyncs the directory where supported,
    then verifies that the committed bytes exactly match the staged bytes.
    """
    if not callable(generator):
        raise TypeError("generator must be callable")

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    existing_mode: int | None = None
    try:
        existing_mode = stat.S_IMODE(destination.stat().st_mode)
    except FileNotFoundError:
        pass

    temp_path: Path | None = None
    expected_size: int | None = None
    expected_sha256: str | None = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        os.close(descriptor)
        temp_path = Path(temp_name)

        generator(temp_path)
        if not temp_path.is_file():
            raise OSError(
                f"generated output did not leave a regular staged file: {temp_path}"
            )
        if existing_mode is not None:
            try:
                temp_path.chmod(existing_mode)
            except OSError:
                pass
        with temp_path.open("rb") as handle:
            os.fsync(handle.fileno())

        staged_stat, expected_sha256 = stable_file_sha256(temp_path)
        expected_size = staged_stat.st_size
        if before_replace is not None:
            before_replace()
        temp_path.replace(destination)
        temp_path = None

        try:
            _fsync_directory(destination.parent)
        except OSError as exc:
            raise AtomicWriteDurabilityError(destination, exc) from exc

        try:
            committed_stat, committed_sha256 = stable_file_sha256(destination)
        except OSError as exc:
            raise AtomicWriteVerificationError(
                destination,
                stage="committed generated write",
                expected_size=expected_size,
                expected_sha256=expected_sha256,
                actual_size=None,
                actual_sha256=None,
                committed=True,
            ) from exc
        if (
            committed_stat.st_size != expected_size
            or committed_sha256 != expected_sha256
        ):
            raise AtomicWriteVerificationError(
                destination,
                stage="committed generated write",
                expected_size=expected_size,
                expected_sha256=expected_sha256,
                actual_size=committed_stat.st_size,
                actual_sha256=committed_sha256,
                committed=True,
            )
    except BaseException:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise

    return destination
