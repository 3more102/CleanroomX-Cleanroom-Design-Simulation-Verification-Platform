"""Regression for a tamper-evident, unsigned CFD chart export set."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from cleanroomx.cfd_analysis_bundle import (
    publish_analysis_bundle,
    verify_analysis_bundle,
)


def _payloads():
    receipt = "a" * 64
    manifest = "b" * 64
    report = {
        "schema_version": "cleanroomx.cfd-two-room-analysis.v1",
        "status": "DIAGNOSTIC_ONLY",
        "scientific_validation": "BLOCKED",
        "solver_convergence": "NOT_ASSESSED",
        "receipt_sha256": receipt,
        "case_manifest_sha256": manifest,
        "graphs": ["pressure_probe_history.svg"],
    }
    return {
        "analysis.json": json.dumps(report) + "\n",
        "index.html": '<!doctype html><a href="pressure_probe_history.svg">Plot</a>',
        "pressure_probe_history.svg": "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>",
    }


def _export(tmp_path):
    output = tmp_path / "analysis"
    published = publish_analysis_bundle(
        output, _payloads(), receipt_sha256="a" * 64, case_manifest_sha256="b" * 64
    )
    return output, published


def test_analysis_bundle_publish_audit_and_refuse_overwrite(tmp_path):
    output, published = _export(tmp_path)
    audited = verify_analysis_bundle(output)
    assert published["manifest_sha256"] == audited["manifest_sha256"]
    assert audited["status"] == "VERIFIED_LOCAL_ARTIFACT_INTEGRITY"
    assert audited["file_count"] == 3
    assert audited["scientific_validation"] == "BLOCKED"
    assert set(path.name for path in output.iterdir()) == {
        "artifact_manifest.json", "analysis.json", "index.html", "pressure_probe_history.svg"
    }
    assert not list(tmp_path.glob(".cleanroomx-analysis-*"))
    with pytest.raises(FileExistsError):
        _export(tmp_path)


@pytest.mark.parametrize("mutation, error", [
    ("svg", "artifact hash or size mismatch"),
    ("dashboard", "artifact hash or size mismatch"),
    ("json", "artifact hash or size mismatch"),
    ("delete", "unexpected or missing files"),
    ("add", "unexpected or missing files"),
])
def test_analysis_bundle_rejects_mutations(tmp_path, mutation, error):
    output, _ = _export(tmp_path)
    if mutation == "svg":
        (output / "pressure_probe_history.svg").write_text("<svg>changed</svg>", encoding="utf-8")
    elif mutation == "dashboard":
        (output / "index.html").write_text("changed", encoding="utf-8")
    elif mutation == "json":
        (output / "analysis.json").write_text("{}", encoding="utf-8")
    elif mutation == "delete":
        (output / "pressure_probe_history.svg").unlink()
    else:
        (output / "extra.svg").write_text("<svg/>", encoding="utf-8")
    with pytest.raises(ValueError, match=error):
        verify_analysis_bundle(output)


def test_analysis_bundle_rejects_symlinked_artifact(tmp_path):
    output, _ = _export(tmp_path)
    target = tmp_path / "other.svg"
    target.write_text("<svg/>", encoding="utf-8")
    exported = output / "pressure_probe_history.svg"
    exported.unlink()
    exported.symlink_to(target)
    with pytest.raises(ValueError, match="regular, non-linked"):
        verify_analysis_bundle(output)


def test_analysis_bundle_rejects_manifest_forgery_and_missing_graph(tmp_path):
    output, _ = _export(tmp_path)
    manifest = output / "artifact_manifest.json"
    forged = json.loads(manifest.read_text(encoding="utf-8"))
    forged["scientific_validation"] = "PASS"
    manifest.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest schema or evidence boundary"):
        verify_analysis_bundle(output)


@pytest.mark.parametrize("name", ["../outside.svg", "other/sub.svg", "C:\\x.svg", "", "artifact_manifest.json"])
def test_analysis_bundle_rejects_unsafe_or_reserved_filenames(tmp_path, name):
    inputs = _payloads()
    inputs[name] = "<svg/>"
    with pytest.raises(ValueError, match="unsafe|reserve"):
        publish_analysis_bundle(
            tmp_path / "unpublished", inputs,
            receipt_sha256="a" * 64, case_manifest_sha256="b" * 64,
        )
    assert not (tmp_path / "unpublished").exists()


def test_analysis_bundle_refuses_tampered_analysis_semantics_even_if_manifest_resigned(tmp_path):
    output, _ = _export(tmp_path)
    from cleanroomx.cfd_analysis_bundle import _canonical
    import hashlib
    report_path = output / "analysis.json"
    document = json.loads(report_path.read_text(encoding="utf-8"))
    document["scientific_validation"] = "PASS"
    report_path.write_text(json.dumps(document), encoding="utf-8")
    manifest_path = output / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw = report_path.read_bytes()
    manifest["files"]["analysis.json"] = {
        "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()
    }
    manifest.pop("manifest_sha256")
    manifest["manifest_sha256"] = hashlib.sha256(_canonical(manifest)).hexdigest()
    manifest_path.write_bytes(_canonical(manifest) + b"\n")
    with pytest.raises(ValueError, match="Analysis JSON does not match"):
        verify_analysis_bundle(output)
