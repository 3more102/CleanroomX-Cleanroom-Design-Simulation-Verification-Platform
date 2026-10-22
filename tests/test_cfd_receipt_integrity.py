"""Synthetic receipt-admission tests; no real OpenFOAM execution is claimed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import cleanroomx.cfd_multizone_results as imported


def _sha(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fixture(tmp_path, monkeypatch, *, mutation=None, raw=None):
    manifest = "{}\n"
    (tmp_path / "manifest.json").write_text(manifest, encoding="utf-8")
    stages = ("blockMesh", "checkMesh", "simpleFoam", "postProcess")
    files = {name + ".log": "completed " + name + "\n" for name in stages}
    files["100/U"] = "recorded velocity values\n"
    receipt = {
        "schema": "cleanroomx.multizone-run.v1",
        "status": "executed_requires_convergence_review",
        "manifest_sha256": _sha(manifest),
        "stages": [
            {
                "command": stage,
                "returncode": 0,
                "failure": None,
                "log_sha256": _sha(files[stage + ".log"]),
            }
            for stage in stages
        ],
        "outputs": {"100/U": _sha(files["100/U"])},
    }
    if mutation is not None:
        mutation(receipt)
    files["run-receipt.json"] = json.dumps(receipt) if raw is None else raw
    monkeypatch.setattr(imported, "verify_multizone_inputs",
                        lambda directory: (Path(directory), {"verified": True}))

    def _read(root, relative):
        if relative not in files:
            raise AssertionError("Unexpected read: " + relative)
        return files[relative]

    monkeypatch.setattr(imported, "_read", _read)
    return receipt


def test_canonical_recorded_receipt_still_passes(tmp_path, monkeypatch):
    receipt = _fixture(tmp_path, monkeypatch)
    manifest, observed = imported._recorded_outputs(tmp_path)
    assert manifest == {"verified": True}
    assert observed == receipt


@pytest.mark.parametrize("raw", [
    '{"schema":"cleanroomx.multizone-run.v1","schema":"other"}',
    '{"stages":[{"command":"blockMesh","command":"checkMesh"}]}',
    '{"status":NaN}',
    '{"status":Infinity}',
    '[]',
    'null',
])
def test_reject_ambiguous_nonfinite_or_nonobject_receipt(tmp_path, monkeypatch, raw):
    _fixture(tmp_path, monkeypatch, raw=raw)
    with pytest.raises(ValueError):
        imported._recorded_outputs(tmp_path)


@pytest.mark.parametrize("bad_stages", [
    None, {}, "blockMesh", [None, None, None, None],
    [{"command": "blockMesh"}] * 4, [],
])
def test_bad_stage_structure_fails_closed_with_valueerror(tmp_path, monkeypatch, bad_stages):
    _fixture(tmp_path, monkeypatch, mutation=lambda r: r.update(stages=bad_stages))
    with pytest.raises(ValueError, match="stage"):
        imported._recorded_outputs(tmp_path)


@pytest.mark.parametrize("bad_code", [False, True, 0.0, "0", -1, None])
def test_noninteger_or_failing_stage_exit_not_accepted(tmp_path, monkeypatch, bad_code):
    def modify(receipt):
        receipt["stages"][1]["returncode"] = bad_code
    _fixture(tmp_path, monkeypatch, mutation=modify)
    with pytest.raises(ValueError, match="stage failed|log changed"):
        imported._recorded_outputs(tmp_path)


@pytest.mark.parametrize("failure", [False, "", 0, "timeout", {"reason": "fatal"}])
def test_only_null_failure_is_accepted(tmp_path, monkeypatch, failure):
    def modify(receipt):
        receipt["stages"][2]["failure"] = failure
    _fixture(tmp_path, monkeypatch, mutation=modify)
    with pytest.raises(ValueError, match="stage failed|log changed"):
        imported._recorded_outputs(tmp_path)


def test_missing_or_modified_output_hash_rejected(tmp_path, monkeypatch):
    def modify(receipt):
        receipt["outputs"]["100/U"] = "f" * 64
    _fixture(tmp_path, monkeypatch, mutation=modify)
    with pytest.raises(ValueError, match="Computed output changed"):
        imported._recorded_outputs(tmp_path)
