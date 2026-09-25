from __future__ import annotations

import json
from pathlib import Path

import pytest

import cleanroomx.application as application_module
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


def test_application_info_exposes_current_implementation_revision():
    info = application_info()
    revision = info["implementation_revision"]
    assert revision["algorithm"] == "sha256-python-source-tree-v1"
    assert len(revision["sha256"]) == 64
    assert revision["source_file_count"] > 0
    assert info["runtime_environment"]["python_version"]
