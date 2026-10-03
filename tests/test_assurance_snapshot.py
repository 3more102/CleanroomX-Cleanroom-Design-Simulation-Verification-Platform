from __future__ import annotations

from contextlib import contextmanager
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



def test_input_ingestion_uses_digest_bound_private_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.json"
    original = DEMO.read_bytes()
    source.write_bytes(original)

    real_stable_file_snapshot = assurance_snapshot_module.stable_file_snapshot
    calls: list[tuple[Path, int, int | None, str]] = []

    @contextmanager
    def controlled_snapshot(
        path,
        *,
        attempts=3,
        max_bytes=None,
        suffix="",
    ):
        with real_stable_file_snapshot(
            path,
            attempts=attempts,
            max_bytes=max_bytes,
            suffix=suffix,
        ) as captured:
            calls.append((Path(path), attempts, max_bytes, suffix))
            source.write_text('{"changed":true}\n', encoding="utf-8")
            yield captured

    monkeypatch.setattr(
        assurance_snapshot_module,
        "stable_file_snapshot",
        controlled_snapshot,
    )

    snapshot = create_assurance_snapshot(source)

    assert snapshot["source"]["utf8_text"] == original.decode("utf-8")
    assert snapshot["source"]["size_bytes"] == len(original)
    assert calls == [
        (
            source,
            3,
            assurance_snapshot_module.ASSURANCE_INPUT_MAX_BYTES,
            source.suffix,
        )
    ]
    assert source.read_text(encoding="utf-8") == '{"changed":true}\n'



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


def test_input_ingestion_does_not_classify_generic_oserror_as_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.json"
    source.write_bytes(DEMO.read_bytes())

    @contextmanager
    def fail_snapshot(*_args, **_kwargs):
        raise OSError(
            "file exceeds supported size limit but this is an injected I/O failure"
        )
        yield  # pragma: no cover

    monkeypatch.setattr(
        assurance_snapshot_module,
        "stable_file_snapshot",
        fail_snapshot,
    )

    with pytest.raises(
        AssuranceSnapshotError,
        match="injected I/O failure",
    ) as exc_info:
        create_assurance_snapshot(source)

    assert "exceeds maximum supported size" not in str(exc_info.value)


def test_input_ingestion_preserves_private_snapshot_verification_without_temp_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.json"
    source.write_bytes(DEMO.read_bytes())
    private_snapshot = tmp_path / "private-random-snapshot-12345.json"
    expected_size = source.stat().st_size

    @contextmanager
    def fail_snapshot(*_args, **_kwargs):
        raise assurance_snapshot_module.StableFileSnapshotVerificationError(
            private_snapshot,
            expected_size=expected_size,
            expected_sha256="1" * 64,
            actual_size=expected_size,
            actual_sha256="2" * 64,
        )
        yield  # pragma: no cover

    monkeypatch.setattr(
        assurance_snapshot_module,
        "stable_file_snapshot",
        fail_snapshot,
    )

    with pytest.raises(
        AssuranceSnapshotError,
        match="private assurance snapshot verification failed",
    ) as exc_info:
        create_assurance_snapshot(source)

    message = str(exc_info.value)
    assert str(source) in message
    assert str(private_snapshot) not in message
    assert f"expected {expected_size} bytes / sha256 {'1' * 64}" in message
    assert f"got {expected_size!r} bytes / sha256 {'2' * 64!r}" in message
    assert isinstance(
        exc_info.value.__cause__,
        assurance_snapshot_module.StableFileSnapshotVerificationError,
    )


def test_create_wraps_non_strict_analysis_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.json"
    source.write_bytes(DEMO.read_bytes())

    monkeypatch.setattr(
        assurance_snapshot_module,
        "analyze_design_assurance",
        lambda _model: {"status": float("nan")},
    )

    with pytest.raises(
        AssuranceSnapshotError,
        match="design assurance result is not strict JSON",
    ):
        create_assurance_snapshot(source)


def test_verify_wraps_non_strict_replayed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = create_assurance_snapshot(DEMO)

    monkeypatch.setattr(
        assurance_snapshot_module,
        "analyze_design_assurance",
        lambda _model: {"status": float("nan")},
    )

    with pytest.raises(
        AssuranceSnapshotError,
        match="replayed design assurance result is not strict JSON",
    ):
        verify_assurance_snapshot(snapshot)


def test_cli_create_reports_non_strict_analysis_result_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "invalid.snapshot.json"
    monkeypatch.setattr(
        assurance_snapshot_module,
        "analyze_design_assurance",
        lambda _model: {"status": float("nan")},
    )

    assert snapshot_cli_main(["create", str(DEMO), str(output)]) == 2
    captured = capsys.readouterr()
    assert "design assurance result is not strict JSON" in captured.err
    assert "Traceback" not in captured.err
    assert not output.exists()


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
