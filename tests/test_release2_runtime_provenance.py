from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import cleanroomx.application as application_module
import cleanroomx.persistence as persistence_module
from cleanroomx.application import RuntimeCodeChangedError, application_info, run_analysis


ROOT = Path(__file__).resolve().parents[1]


def _example(name: str) -> dict:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def test_run_provenance_binds_exact_cleanroomx_code_and_runtime():
    run = run_analysis("room_verification", _example("basic_room.json"))
    provenance = run.diagnostics["application_execution_provenance"]

    code = provenance["code_revision"]
    assert code["algorithm"] == "sha256-python-source-tree-v1"
    assert len(code["sha256_before"]) == 64
    assert code["sha256_before"] == code["sha256_after"]
    assert code["source_file_count_before"] == code["source_file_count_after"]
    assert code["source_file_count_before"] > 0
    assert code["stable_during_run"] is True

    binding = provenance["execution_binding"]
    assert binding["parser"] == "cleanroomx.io:room_from_dict"
    assert binding["runner"] == "cleanroomx.verification:verify_room"
    assert binding["reporter"] == "cleanroomx.application:_fallback_markdown"
    assert binding["custom_adapter"] is None

    runtime = provenance["runtime_environment"]
    assert runtime["python_implementation"]
    assert runtime["python_version"]
    assert runtime["platform_system"]
    assert runtime["byteorder"] in {"little", "big"}
    assert runtime["float_radix"] == 2
    assert runtime["float_mant_dig"] >= 53


def test_analysis_discards_result_when_cleanroomx_code_changes(monkeypatch):
    fingerprints = iter(
        [
            {
                "algorithm": "sha256-python-source-tree-v1",
                "sha256": "1" * 64,
                "source_file_count": 100,
            },
            {
                "algorithm": "sha256-python-source-tree-v1",
                "sha256": "2" * 64,
                "source_file_count": 100,
            },
        ]
    )
    monkeypatch.setattr(
        application_module,
        "_capture_runtime_code_fingerprint",
        lambda: next(fingerprints),
    )

    with pytest.raises(RuntimeCodeChangedError, match="result was discarded") as raised:
        run_analysis("room_verification", _example("basic_room.json"))

    assert raised.value.before["sha256"] == "1" * 64
    assert raised.value.after["sha256"] == "2" * 64


def test_python_tree_fingerprint_is_deterministic_cached_and_content_sensitive(tmp_path):
    root = tmp_path / "cleanroomx"
    root.mkdir()
    source = root / "module.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    (root / "other.py").write_text("VALUE = 2\n", encoding="utf-8")
    cache = root / "__pycache__"
    cache.mkdir()
    (cache / "ignored.py").write_text("IGNORED = True\n", encoding="utf-8")

    application_module._hash_python_tree_manifest.cache_clear()
    first = application_module._fingerprint_python_tree(root)
    first_cache = application_module._hash_python_tree_manifest.cache_info()
    second = application_module._fingerprint_python_tree(root)
    second_cache = application_module._hash_python_tree_manifest.cache_info()

    assert second == first
    assert first["source_file_count"] == 2
    assert second_cache.hits == first_cache.hits + 1

    source.write_text("VALUE = 3\n", encoding="utf-8")
    changed = application_module._fingerprint_python_tree(root)
    assert changed["sha256"] != first["sha256"]


def test_python_tree_fingerprint_rejects_oversized_source_before_binary_read(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "cleanroomx"
    root.mkdir()
    source = root / "oversized.py"
    with source.open("wb") as stream:
        stream.truncate(application_module._RUNTIME_SOURCE_FILE_MAX_BYTES + 1)

    original_open = Path.open

    def reject_binary_read(self, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if Path(self) == source and mode == "rb":
            raise AssertionError("oversized runtime source must fail before binary read")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_binary_read)
    application_module._hash_python_tree_manifest.cache_clear()

    with pytest.raises(RuntimeError, match="source file exceeds supported size limit"):
        application_module._fingerprint_python_tree(root)


def test_python_tree_fingerprint_rejects_oversized_tree_before_binary_read(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "cleanroomx"
    root.mkdir()
    first = root / "first.py"
    second = root / "second.py"
    first.write_bytes(b"A" * 8)
    second.write_bytes(b"B" * 8)

    monkeypatch.setattr(application_module, "_RUNTIME_SOURCE_FILE_MAX_BYTES", 8)
    monkeypatch.setattr(application_module, "_RUNTIME_SOURCE_TREE_MAX_BYTES", 12)
    original_open = Path.open

    def reject_binary_read(self, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if mode == "rb" and Path(self).parent == root:
            raise AssertionError("oversized runtime tree must fail before binary read")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_binary_read)
    application_module._hash_python_tree_manifest.cache_clear()

    with pytest.raises(RuntimeError, match="source tree exceeds supported size limit"):
        application_module._fingerprint_python_tree(root)


def test_python_tree_fingerprint_uses_bounded_source_read(tmp_path, monkeypatch):
    root = tmp_path / "cleanroomx"
    root.mkdir()
    source = root / "module.py"
    source.write_bytes(b"VALUE = 1\n")
    requested_sizes = []
    original_open = Path.open

    class RecordingReader:
        def __init__(self, handle): self._handle = handle
        def __enter__(self): self._handle.__enter__(); return self
        def __exit__(self, exc_type, exc, tb): return self._handle.__exit__(exc_type, exc, tb)
        def fileno(self): return self._handle.fileno()
        def read(self, size=-1): requested_sizes.append(size); return self._handle.read(size)

    def recording_open(self, *args, **kwargs):
        handle = original_open(self, *args, **kwargs)
        mode = args[0] if args else kwargs.get("mode", "r")
        if Path(self) == source and mode == "rb": return RecordingReader(handle)
        return handle

    monkeypatch.setattr(Path, "open", recording_open)
    application_module._hash_python_tree_manifest.cache_clear()
    result = application_module._fingerprint_python_tree(root)
    assert result["source_file_count"] == 1
    assert requested_sizes == [source.stat().st_size + 1]


def test_python_tree_fingerprint_rejects_opened_source_revision_change(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "cleanroomx"
    root.mkdir()
    source = root / "module.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")

    application_module._hash_python_tree_manifest.cache_clear()
    manifest = application_module._python_tree_manifest(root)
    real_fstat = application_module.os.fstat
    fstat_calls = 0

    def changed_fstat(fd):
        nonlocal fstat_calls
        metadata = real_fstat(fd)
        fstat_calls += 1
        if fstat_calls != 2:
            return metadata
        return SimpleNamespace(
            st_dev=metadata.st_dev,
            st_ino=metadata.st_ino,
            st_size=metadata.st_size + 1,
            st_mtime_ns=metadata.st_mtime_ns,
            st_ctime_ns=metadata.st_ctime_ns,
        )

    monkeypatch.setattr(application_module.os, "fstat", changed_fstat)
    monkeypatch.setattr(
        application_module,
        "_python_tree_manifest",
        lambda _root: manifest,
    )

    with pytest.raises(
        application_module._RuntimeSourceTreeChangedError,
        match="changed while it was being fingerprinted",
    ):
        application_module._hash_python_tree_manifest(str(root.resolve()), manifest)


def test_python_tree_fingerprint_rejects_windows_same_size_path_handle_substitution(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "cleanroomx"
    root.mkdir()
    source = root / "module.py"
    replacement = tmp_path / "replacement.py"
    source.write_bytes(b"VALUE = 1\n")
    replacement.write_bytes(b"VALUE = 2\n")
    source_stat = source.stat()
    replacement_stat = replacement.stat()
    os.utime(
        replacement,
        ns=(
            replacement_stat.st_atime_ns,
            source_stat.st_mtime_ns,
        ),
    )
    replacement_stat = replacement.stat()
    assert source_stat.st_ino != replacement_stat.st_ino

    application_module._hash_python_tree_manifest.cache_clear()
    manifest = application_module._python_tree_manifest(root)
    original_open = Path.open
    substituted = False

    def substitute_same_size_source(self, *args, **kwargs):
        nonlocal substituted
        mode = args[0] if args else kwargs.get("mode", "r")
        if Path(self) == source and mode == "rb":
            substituted = True
            return original_open(replacement, *args, **kwargs)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(persistence_module, "_IS_WINDOWS", True)
    monkeypatch.setattr(Path, "open", substitute_same_size_source)
    monkeypatch.setattr(application_module, "_python_tree_manifest", lambda _root: manifest)

    with pytest.raises(
        application_module._RuntimeSourceTreeChangedError,
        match="changed while it was being fingerprinted",
    ) as exc_info:
        application_module._hash_python_tree_manifest(str(root.resolve()), manifest)

    message = str(exc_info.value)
    assert "path/handle binding mismatch" in message
    assert f"path dev={source_stat.st_dev}, ino={source_stat.st_ino}" in message
    assert (
        f"handle dev={replacement_stat.st_dev}, ino={replacement_stat.st_ino}"
        in message
    )
    assert substituted is True


def test_python_tree_fingerprint_retries_only_typed_revision_change(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "cleanroomx"
    root.mkdir()
    (root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    expected = {
        "algorithm": application_module._RUNTIME_CODE_FINGERPRINT_ALGORITHM,
        "sha256": "0" * 64,
        "source_file_count": 1,
    }
    calls = 0

    def typed_race_then_success(root_text, manifest):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise application_module._RuntimeSourceTreeChangedError(
                "simulated runtime source revision race"
            )
        return expected

    monkeypatch.setattr(
        application_module,
        "_hash_python_tree_manifest",
        typed_race_then_success,
    )

    assert application_module._fingerprint_python_tree(root) == expected
    assert calls == 2


def test_python_tree_fingerprint_does_not_retry_unrelated_runtime_error_with_race_text(
    tmp_path,
    monkeypatch,
):
    root = tmp_path / "cleanroomx"
    root.mkdir()
    (root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    calls = 0

    def unrelated_failure(root_text, manifest):
        nonlocal calls
        calls += 1
        raise RuntimeError(
            "changed while it was being fingerprinted but this is an unrelated failure"
        )

    monkeypatch.setattr(
        application_module,
        "_hash_python_tree_manifest",
        unrelated_failure,
    )

    with pytest.raises(RuntimeError, match="unrelated failure"):
        application_module._fingerprint_python_tree(root)

    assert calls == 1


def test_frozen_runtime_fingerprint_uses_executable_artifact(tmp_path, monkeypatch):
    executable = tmp_path / "CleanroomX.exe"
    executable.write_bytes(b"cleanroomx-frozen-runtime")
    monkeypatch.setattr(application_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(application_module.sys, "executable", str(executable))

    revision = application_module._capture_runtime_code_fingerprint()

    assert revision["algorithm"] == "sha256-frozen-executable-v1"
    assert len(revision["sha256"]) == 64
    assert revision["source_file_count"] == 1
    assert revision["artifact_size_bytes"] == executable.stat().st_size


def test_application_info_exposes_current_implementation_revision():
    info = application_info()
    revision = info["implementation_revision"]
    assert revision["algorithm"] == "sha256-python-source-tree-v1"
    assert len(revision["sha256"]) == 64
    assert revision["source_file_count"] > 0
    assert info["runtime_environment"]["python_version"]
