from __future__ import annotations

from contextlib import contextmanager
import errno
from hashlib import sha256
import os
from pathlib import Path
import stat
import tempfile
from typing import Callable, Iterator


BeforeReplace = Callable[[], None]
_IS_WINDOWS = os.name == "nt"


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


class StableFileSizeError(OSError):
    """Raised when a bounded stable-file read exceeds its byte ceiling."""

    def __init__(
        self,
        path: str | Path,
        observed_size: int,
        limit: int,
    ) -> None:
        self.path = Path(path)
        self.observed_size = observed_size
        self.limit = limit
        super().__init__(
            "file exceeds supported size limit "
            f"({observed_size} > {limit} bytes): {self.path}"
        )


class StableFileSnapshotVerificationError(OSError):
    """Raised when private snapshot bytes do not match the captured source revision."""

    def __init__(
        self,
        path: str | Path,
        *,
        expected_size: int,
        expected_sha256: str,
        actual_size: int | None,
        actual_sha256: str | None,
    ) -> None:
        self.path = Path(path)
        self.expected_size = expected_size
        self.expected_sha256 = expected_sha256
        self.actual_size = actual_size
        self.actual_sha256 = actual_sha256
        super().__init__(
            f"stable file snapshot verification failed for {self.path}: "
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


def _ensure_directory_durable(directory: Path) -> None:
    """Create missing directory components and durably record each new entry.

    Existing directories are left untouched. On POSIX, every directory entry
    created by this helper is followed by an fsync of its parent before the next
    nested component is created. Unsupported directory-fsync filesystems retain
    the existing best-effort behavior from _fsync_directory().
    """
    target = Path(directory)
    missing: list[Path] = []
    current = target

    while True:
        try:
            metadata = current.stat()
        except FileNotFoundError:
            missing.append(current)
            parent = current.parent
            if parent == current:
                raise
            current = parent
            continue
        if not stat.S_ISDIR(metadata.st_mode):
            raise NotADirectoryError(
                f"directory path component is not a directory: {current}"
            )
        break

    for item in reversed(missing):
        try:
            item.mkdir()
        except FileExistsError:
            if not item.is_dir():
                raise
        # Also sync after a concurrent creator wins the mkdir race. The entry
        # must be durable before we rely on it for deeper staged writes.
        _fsync_directory(item.parent)


def _stable_file_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _stable_file_path_matches_opened(
    path_stat: os.stat_result,
    opened_stat: os.stat_result,
) -> bool:
    """Bind an opened descriptor to its path revision without non-portable Windows IDs."""
    if opened_stat.st_size != path_stat.st_size:
        return False
    if _IS_WINDOWS:
        return (
            opened_stat.st_mtime_ns == path_stat.st_mtime_ns
            and opened_stat.st_ctime_ns == path_stat.st_ctime_ns
        )
    return _stable_file_identity(path_stat) == _stable_file_identity(opened_stat)


def _validate_stable_file_max_bytes(max_bytes: int | None) -> int | None:
    if max_bytes is None:
        return None
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0:
        raise ValueError("max_bytes must be a non-negative integer or None")
    return max_bytes


def _capture_stable_file_revision(
    source: Path,
    *,
    attempts: int,
    max_bytes: int | None,
    snapshot_path: Path | None,
) -> tuple[os.stat_result, str]:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    limit = _validate_stable_file_max_bytes(max_bytes)
    last_error: OSError | None = None

    for _attempt in range(attempts):
        try:
            before_path = source.stat()
            if limit is not None and before_path.st_size > limit:
                raise StableFileSizeError(source, before_path.st_size, limit)

            digest = sha256()
            bytes_read = 0
            with source.open("rb") as handle:
                before_handle = os.fstat(handle.fileno())
                if limit is not None and before_handle.st_size > limit:
                    raise StableFileSizeError(source, before_handle.st_size, limit)

                def read_chunk() -> bytes:
                    read_size = 1024 * 1024
                    if limit is not None:
                        read_size = min(read_size, limit - bytes_read + 1)
                    return handle.read(read_size)

                if snapshot_path is None:
                    for chunk in iter(read_chunk, b""):
                        bytes_read += len(chunk)
                        if limit is not None and bytes_read > limit:
                            raise StableFileSizeError(source, bytes_read, limit)
                        digest.update(chunk)
                else:
                    with snapshot_path.open("wb") as snapshot:
                        for chunk in iter(read_chunk, b""):
                            bytes_read += len(chunk)
                            if limit is not None and bytes_read > limit:
                                raise StableFileSizeError(source, bytes_read, limit)
                            digest.update(chunk)
                            snapshot.write(chunk)
                        snapshot.flush()

                after_handle = os.fstat(handle.fileno())
            after_path = source.stat()
        except StableFileSizeError:
            raise
        except OSError as exc:
            last_error = exc
            continue

        if (
            _stable_file_identity(before_path) == _stable_file_identity(after_path)
            and _stable_file_identity(before_handle)
            == _stable_file_identity(after_handle)
            and _stable_file_path_matches_opened(before_path, before_handle)
            and _stable_file_path_matches_opened(after_path, after_handle)
            and bytes_read == after_handle.st_size
        ):
            return after_path, digest.hexdigest()
        last_error = OSError(f"file changed while verifying: {source}")

    assert last_error is not None
    raise last_error


def stable_file_sha256(
    path: str | Path,
    *,
    attempts: int = 3,
    max_bytes: int | None = None,
) -> tuple[os.stat_result, str]:
    """Hash one stable file revision and reject path/descriptor replacement races."""
    return _capture_stable_file_revision(
        Path(path),
        attempts=attempts,
        max_bytes=max_bytes,
        snapshot_path=None,
    )


@contextmanager
def stable_file_snapshot(
    path: str | Path,
    *,
    attempts: int = 3,
    max_bytes: int | None = None,
    suffix: str = "",
) -> Iterator[tuple[Path, os.stat_result, str]]:
    """Copy one stable source revision into a private digest-bound file snapshot."""
    if not isinstance(suffix, str):
        raise TypeError("suffix must be a string")
    if any(separator and separator in suffix for separator in (os.sep, os.altsep)):
        raise ValueError("suffix must not contain path separators")

    source = Path(path)
    with tempfile.TemporaryDirectory(prefix="cleanroomx-stable-file-") as directory:
        snapshot = Path(directory) / f"snapshot{suffix}"
        metadata, digest = _capture_stable_file_revision(
            source,
            attempts=attempts,
            max_bytes=max_bytes,
            snapshot_path=snapshot,
        )
        try:
            snapshot_metadata, snapshot_digest = stable_file_sha256(
                snapshot,
                attempts=1,
                max_bytes=max(metadata.st_size, 1),
            )
        except StableFileSizeError as exc:
            raise StableFileSnapshotVerificationError(
                snapshot,
                expected_size=metadata.st_size,
                expected_sha256=digest,
                actual_size=exc.observed_size,
                actual_sha256=None,
            ) from exc
        except OSError as exc:
            raise StableFileSnapshotVerificationError(
                snapshot,
                expected_size=metadata.st_size,
                expected_sha256=digest,
                actual_size=None,
                actual_sha256=None,
            ) from exc
        if (
            snapshot_metadata.st_size != metadata.st_size
            or snapshot_digest != digest
        ):
            raise StableFileSnapshotVerificationError(
                snapshot,
                expected_size=metadata.st_size,
                expected_sha256=digest,
                actual_size=snapshot_metadata.st_size,
                actual_sha256=snapshot_digest,
            )
        yield snapshot, metadata, digest


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
        stat_result, actual_sha256 = _stable_file_sha256(
            path,
            max_bytes=expected_size,
        )
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
    _ensure_directory_durable(destination.parent)
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
        stat_result, actual_sha256 = stable_file_sha256(
            path,
            max_bytes=expected_size,
        )
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
    _ensure_directory_durable(destination.parent)

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

        initial_staged_size = staged.stat().st_size
        staged_stat, expected_sha256 = stable_file_sha256(
            staged,
            max_bytes=initial_staged_size,
        )
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
    """Generate a potentially large file and publish it through one atomic path.

    The generator receives a same-directory private staging path and never writes
    the destination directly. Publication, fsync, staged-byte revalidation,
    replacement, directory durability, and committed-byte verification are all
    delegated to atomic_publish_staged_file so generated outputs cannot drift into
    a second persistence implementation.
    """
    if not callable(generator):
        raise TypeError("generator must be callable")

    destination = Path(path)
    _ensure_directory_durable(destination.parent)

    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(descriptor)
    temp_path: Path | None = Path(temp_name)
    try:
        generator(temp_path)
        if not temp_path.is_file():
            raise OSError(
                f"generated output did not leave a regular staged file: {temp_path}"
            )
        published = atomic_publish_staged_file(
            destination,
            temp_path,
            before_replace=before_replace,
        )
        temp_path = None
        return published
    except BaseException:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
