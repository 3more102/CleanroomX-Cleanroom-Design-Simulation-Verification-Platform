from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import cleanroomx.assurance_snapshot as assurance_snapshot_module
from cleanroomx.assurance_snapshot import (
    AssuranceSnapshotError,
    create_assurance_snapshot,
    load_assurance_snapshot,
    verify_assurance_snapshot,
    verify_assurance_snapshot_file,
    write_assurance_snapshot,
)
from cleanroomx.assurance_snapshot_cli import main as snapshot_cli_main


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
DEMO = EXAMPLES / "design_assurance_demo.json"


PRESSURE_DEMO = EXAMPLES / "pressure_design_consistency_demo.json"


def _write_pressure_assurance_source(path: Path) -> None:
    payload = json.loads(DEMO.read_text(encoding="utf-8"))
    payload["pressure_design_consistency"] = json.loads(
        PRESSURE_DEMO.read_text(encoding="utf-8")
    )
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def test_snapshot_is_deterministic_and_self_verifying(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.snapshot.json"
    second_path = tmp_path / "second.snapshot.json"

    first = write_assurance_snapshot(DEMO, first_path)
    second = write_assurance_snapshot(DEMO, second_path)

    assert first == second
    assert first_path.read_bytes() == second_path.read_bytes()
    assert len(first["snapshot_sha256"]) == 64
    assert len(first["source"]["sha256"]) == 64
    assert len(first["analysis"]["result_sha256"]) == 64
    assert first["analysis"]["result"]["verified"] is True
    assert first["analysis"]["result"]["no_failures_detected"] is True
    assert (
        first["analysis"]["traceability_sha256"]
        == first["analysis"]["result"]["traceability_sha256"]
    )

    report = verify_assurance_snapshot_file(first_path)
    assert report["status"] == "valid"
    assert report["valid"] is True
    assert report["integrity_valid"] is True
    assert report["replay_consistent"] is True
    assert report["snapshot"]["match"] is True
    assert report["source"]["size_match"] is True
    assert report["source"]["sha256_match"] is True
    assert report["analysis"]["stored_result_digest_match"] is True
    assert report["analysis"]["replay_match"] is True
    assert report["analysis"]["replayed_traceability_match"] is True


def test_snapshot_binds_optional_pressure_assurance_evidence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "pressure-assurance.json"
    _write_pressure_assurance_source(source)

    snapshot = create_assurance_snapshot(source)
    result = snapshot["analysis"]["result"]

    assert result["status"] == "pass"
    assert result["verified"] is True
    assert result["no_failures_detected"] is True
    assert result["summary"]["component_count"] == 3
    assert result["traceability"][1]["component"] == "pressure_design_consistency"
    assert len(result["traceability"][1]["result_sha256"]) == 64

    report = verify_assurance_snapshot(snapshot)
    assert report["valid"] is True
    assert report["analysis"]["replay_match"] is True
    assert report["analysis"]["replayed_traceability_match"] is True


def test_exact_source_revision_is_bound_even_when_semantics_match(
    tmp_path: Path,
) -> None:
    source_a = tmp_path / "a.json"
    source_b = tmp_path / "b.json"
    text = DEMO.read_text(encoding="utf-8")
    source_a.write_text(text, encoding="utf-8")
    source_b.write_text(text + "\n", encoding="utf-8")

    first = create_assurance_snapshot(source_a)
    second = create_assurance_snapshot(source_b)

    assert first["analysis"]["result"] == second["analysis"]["result"]
    assert (
        first["analysis"]["result_sha256"]
        == second["analysis"]["result_sha256"]
    )
    assert first["source"]["sha256"] != second["source"]["sha256"]
    assert first["snapshot_sha256"] != second["snapshot_sha256"]


def test_source_tampering_is_detected_without_rewriting_recorded_hashes(
) -> None:
    snapshot = create_assurance_snapshot(DEMO)
    tampered = copy.deepcopy(snapshot)
    embedded = json.loads(tampered["source"]["utf8_text"])
    embedded["name"] = "Tampered design assurance"
    tampered["source"]["utf8_text"] = json.dumps(
        embedded,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )

    report = verify_assurance_snapshot(tampered)

    assert report["valid"] is False
    assert report["integrity_valid"] is False
    assert report["source"]["size_match"] is False
    assert report["source"]["sha256_match"] is False
    assert report["snapshot"]["match"] is False
    assert report["analysis"]["replay_match"] is False


def test_embedded_result_tampering_is_detected() -> None:
    snapshot = create_assurance_snapshot(DEMO)
    tampered = copy.deepcopy(snapshot)
    tampered["analysis"]["result"]["status"] = "fail"

    report = verify_assurance_snapshot(tampered)

    assert report["valid"] is False
    assert report["integrity_valid"] is False
    assert report["replay_consistent"] is False
    assert report["analysis"]["stored_result_digest_match"] is False
    assert report["analysis"]["replay_match"] is False
    assert report["snapshot"]["match"] is False


def test_snapshot_digest_tampering_is_detected() -> None:
    snapshot = create_assurance_snapshot(DEMO)
    snapshot["snapshot_sha256"] = "0" * 64

    report = verify_assurance_snapshot(snapshot)

    assert report["valid"] is False
    assert report["integrity_valid"] is False
    assert report["replay_consistent"] is True
    assert report["snapshot"]["match"] is False


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.json"
    source.write_text(
        (
            '{"name":"first","name":"second","design_consistency":{},'
            '"compliance_checks":[]}'
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        AssuranceSnapshotError,
        match="duplicate JSON object key",
    ):
        create_assurance_snapshot(source)


def test_snapshot_rejects_unknown_top_level_fields() -> None:
    snapshot = create_assurance_snapshot(DEMO)
    snapshot["signature"] = "not-supported-in-v1"

    with pytest.raises(
        AssuranceSnapshotError,
        match="unsupported field",
    ):
        verify_assurance_snapshot(snapshot)


def test_snapshot_output_cannot_overwrite_input(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    source.write_bytes(DEMO.read_bytes())

    with pytest.raises(
        AssuranceSnapshotError,
        match="different from the input source",
    ):
        write_assurance_snapshot(source, source)


def test_snapshot_output_identity_is_rechecked_before_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.json"
    source.write_bytes(DEMO.read_bytes())
    output = tmp_path / "snapshot.json"
    before = source.read_bytes()

    def alias_before_replace(path, text, *, before_replace=None):
        assert Path(path) == output
        assert isinstance(text, str)
        assert before_replace is not None
        output.hardlink_to(source)
        before_replace()
        raise AssertionError("unsafe replacement should not be reached")

    monkeypatch.setattr(
        assurance_snapshot_module,
        "atomic_write_text",
        alias_before_replace,
    )

    with pytest.raises(
        AssuranceSnapshotError,
        match="different from the input source",
    ):
        write_assurance_snapshot(source, output)

    assert source.read_bytes() == before
    assert output.read_bytes() == before


def test_input_size_limit_is_enforced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.json"
    source.write_bytes(DEMO.read_bytes())
    monkeypatch.setattr(
        assurance_snapshot_module,
        "ASSURANCE_INPUT_MAX_BYTES",
        8,
    )

    with pytest.raises(
        AssuranceSnapshotError,
        match="exceeds maximum supported size",
    ):
        create_assurance_snapshot(source)


def test_cli_create_and_verify_round_trip(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshot_path = tmp_path / "assurance.snapshot.json"

    assert (
        snapshot_cli_main(
            ["create", str(DEMO), str(snapshot_path)]
        )
        == 0
    )
    create_output = json.loads(capsys.readouterr().out)
    assert create_output["status"] == "created"
    assert (
        create_output["schema"]
        == "cleanroomx.design-assurance-snapshot"
    )

    assert snapshot_cli_main(["verify", str(snapshot_path)]) == 0
    verify_output = json.loads(capsys.readouterr().out)
    assert verify_output["status"] == "valid"
    assert verify_output["valid"] is True


def test_cli_returns_two_for_tampered_snapshot(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshot_path = tmp_path / "assurance.snapshot.json"
    write_assurance_snapshot(DEMO, snapshot_path)
    snapshot = load_assurance_snapshot(snapshot_path)
    snapshot["snapshot_sha256"] = "f" * 64
    snapshot_path.write_text(
        (
            json.dumps(
                snapshot,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n"
        ),
        encoding="utf-8",
    )

    assert snapshot_cli_main(["verify", str(snapshot_path)]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "invalid"
    assert output["valid"] is False
