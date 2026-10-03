from __future__ import annotations

import json
from pathlib import Path

import pytest

import cleanroomx.autosave as autosave_module
import cleanroomx.strict_json as strict_json_module
from cleanroomx.autosave import AutosaveManager, RecoveryFormatError, load_recovery_artifact
from cleanroomx.strict_json import StrictJSONError, StrictJSONSizeError


def _legacy_recovery_bytes(*, project_identity: str = "session-test") -> bytes:
    return json.dumps(
        {
            "schema": "cleanroomx.autosave",
            "schema_version": 1,
            "project_identity": project_identity,
            "saved_at_utc": "2026-10-02T10:00:00Z",
            "source": {"path": None},
            "snapshot": {"project": {}},
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_recovery_loader_accepts_artifact_at_exact_size_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "exact.recovery.json"
    payload = _legacy_recovery_bytes()
    source.write_bytes(payload)
    monkeypatch.setattr(autosave_module, "RECOVERY_FILE_MAX_BYTES", len(payload))

    loaded = load_recovery_artifact(source)

    assert loaded["project_identity"] == "session-test"


def test_recovery_loader_rejects_oversized_artifact_before_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "oversized.recovery.json"
    payload = _legacy_recovery_bytes()
    source.write_bytes(payload)
    monkeypatch.setattr(autosave_module, "RECOVERY_FILE_MAX_BYTES", len(payload) - 1)

    with pytest.raises(RecoveryFormatError, match="recovery artifact size") as raised:
        load_recovery_artifact(source)

    assert isinstance(raised.value.__cause__, StrictJSONSizeError)
    assert raised.value.__cause__.observed_size == len(payload)
    assert raised.value.__cause__.limit == len(payload) - 1
    assert str(len(payload)) in str(raised.value)
    assert str(len(payload) - 1) in str(raised.value)


def test_recovery_loader_does_not_classify_generic_strict_json_error_as_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "generic-strict-json-error.recovery.json"
    source.write_text("{}", encoding="utf-8")

    def fail_strict_json(*args, **kwargs):
        raise strict_json_module.StrictJSONError(
            "exceeds maximum supported JSON size but this is an injected semantic failure"
        )

    monkeypatch.setattr(autosave_module, "load_strict_json", fail_strict_json)

    with pytest.raises(
        RecoveryFormatError,
        match="invalid strict recovery JSON",
    ) as raised:
        load_recovery_artifact(source)

    assert "recovery artifact size" not in str(raised.value)
    assert isinstance(raised.value.__cause__, StrictJSONError)
    assert not isinstance(raised.value.__cause__, StrictJSONSizeError)


def test_recovery_loader_rejects_invalid_utf8(
    tmp_path: Path,
) -> None:
    source = tmp_path / "invalid-utf8.recovery.json"
    source.write_bytes(b'{"schema":"cleanroomx.autosave","bad":"\xff"}')

    with pytest.raises(RecoveryFormatError, match="valid UTF-8"):
        load_recovery_artifact(source)


def test_recovery_loader_rejects_duplicate_keys(
    tmp_path: Path,
) -> None:
    source = tmp_path / "duplicate.recovery.json"
    source.write_text(
        '{"schema":"cleanroomx.autosave","schema_version":1,'
        '"project_identity":"a","project_identity":"b",'
        '"saved_at_utc":"2026-10-02T10:00:00Z",'
        '"source":{"path":null},"snapshot":{}}',
        encoding="utf-8",
    )

    with pytest.raises(RecoveryFormatError, match="duplicate JSON object key"):
        load_recovery_artifact(source)


def test_recovery_loader_rejects_non_finite_numbers(
    tmp_path: Path,
) -> None:
    source = tmp_path / "nonfinite.recovery.json"
    source.write_text(
        '{"schema":"cleanroomx.autosave","schema_version":1,'
        '"project_identity":"a","saved_at_utc":"2026-10-02T10:00:00Z",'
        '"source":{"path":null},"snapshot":{"value":NaN}}',
        encoding="utf-8",
    )

    with pytest.raises(RecoveryFormatError, match="non-finite JSON constant"):
        load_recovery_artifact(source)


def test_recovery_loader_rejects_live_path_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.recovery.json"
    replacement = tmp_path / "replacement.recovery.json"
    source.write_bytes(_legacy_recovery_bytes(project_identity="original"))
    replacement.write_bytes(_legacy_recovery_bytes(project_identity="replacement"))
    real_stat = Path.stat
    replacement_stat = real_stat(replacement)

    def report_replacement(self: Path, *args, **kwargs):
        if self == source:
            return replacement_stat
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", report_replacement)

    with pytest.raises(RecoveryFormatError, match="changed while reading JSON input"):
        load_recovery_artifact(source)


def test_recovery_loader_rejects_live_path_disappearance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.recovery.json"
    source.write_bytes(_legacy_recovery_bytes())
    real_stat = Path.stat

    def disappear(self: Path, *args, **kwargs):
        if self == source:
            raise FileNotFoundError(str(source))
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", disappear)

    with pytest.raises(RecoveryFormatError, match="changed while reading JSON input") as raised:
        load_recovery_artifact(source)

    assert isinstance(raised.value.__cause__, StrictJSONError)
    assert isinstance(raised.value.__cause__.__cause__, FileNotFoundError)


def test_recovery_loader_rejects_revision_growth_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.recovery.json"
    larger = tmp_path / "larger.recovery.json"
    source.write_bytes(_legacy_recovery_bytes())
    larger.write_bytes(_legacy_recovery_bytes() + b" ")
    source_stat = source.stat()
    larger_stat = larger.stat()
    real_fstat = strict_json_module.os.fstat
    calls = 0

    def changing_fstat(fd: int):
        nonlocal calls
        calls += 1
        if calls == 1:
            return source_stat
        if calls == 2:
            return larger_stat
        return real_fstat(fd)

    monkeypatch.setattr(strict_json_module.os, "fstat", changing_fstat)

    with pytest.raises(RecoveryFormatError, match="changed while reading JSON input"):
        load_recovery_artifact(source)


def test_recovery_writer_never_publishes_artifact_above_reader_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = AutosaveManager(tmp_path / "recovery", session_id="bounded-writer")
    request = autosave_module._AutosaveRequest(
        project_identity="session-bounded",
        epoch=0,
        source_path=None,
        snapshot_text='{"project":{}}',
        digest="0" * 64,
    )
    monkeypatch.setattr(autosave_module, "RECOVERY_FILE_MAX_BYTES", 64)

    try:
        with pytest.raises(RecoveryFormatError, match="exceeds maximum supported size"):
            manager._write_recovery(request)
    finally:
        manager.shutdown(wait=True)

    assert not list((tmp_path / "recovery").glob("*.recovery.json"))
