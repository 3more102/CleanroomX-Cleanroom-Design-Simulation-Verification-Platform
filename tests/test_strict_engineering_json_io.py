from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

import cleanroomx.strict_json as strict_json_module
from cleanroomx.damper_study_io import load_loop_damper_study
from cleanroomx.dossier import build_dossier
from cleanroomx.dossier_cli import main as dossier_main
from cleanroomx.duct_flow_io import load_parallel_flow_network
from cleanroomx.fan_curve_io import load_fan_operating_point_study
from cleanroomx.fan_duct_network_io import load_fan_duct_network_study
from cleanroomx.fan_loop_network_io import load_fan_loop_network_study
from cleanroomx.fan_loop_speed_io import load_fan_loop_speed_study
from cleanroomx.fan_loop_uncertainty_io import load_fan_loop_network_uncertainty
from cleanroomx.fan_network_io import load_fan_driven_parallel_network_study
from cleanroomx.fan_speed_io import load_fan_speed_study
from cleanroomx.fan_uncertainty_io import load_fan_system_uncertainty
from cleanroomx.fan_variable_friction_loop_io import (
    load_fan_variable_friction_loop_study,
)
from cleanroomx.fan_variable_friction_speed_io import (
    load_fan_variable_friction_speed_study,
)
from cleanroomx.fan_variable_friction_uncertainty_io import (
    load_fan_variable_friction_loop_uncertainty,
)
from cleanroomx.hvac_io import load_hvac_project
from cleanroomx.io import load_project, load_room
from cleanroomx.loop_network_io import load_looped_flow_network
from cleanroomx.pressure_network_io import load_pressure_network
from cleanroomx.psychrometric_uncertainty_io import load_psychrometric_uncertainty
from cleanroomx.qualification_io import load_qualification_uncertainty
from cleanroomx.recovery_io import load_recovery_test
from cleanroomx.strict_json import (
    StrictJSONError,
    load_strict_json,
    load_strict_json_snapshot,
    strict_json_loads,
)
from cleanroomx.thermal_uncertainty_io import load_thermal_uncertainty
from cleanroomx.uncertainty_io import load_uncertain_room


FILE_LOADERS: tuple[Callable[[str | Path], object], ...] = (
    build_dossier,
    load_room,
    load_project,
    load_recovery_test,
    load_hvac_project,
    load_parallel_flow_network,
    load_looped_flow_network,
    load_pressure_network,
    load_uncertain_room,
    load_qualification_uncertainty,
    load_fan_speed_study,
    load_fan_operating_point_study,
    load_fan_driven_parallel_network_study,
    load_loop_damper_study,
    load_fan_loop_speed_study,
    load_fan_system_uncertainty,
    load_fan_duct_network_study,
    load_fan_loop_network_study,
    load_fan_loop_network_uncertainty,
    load_fan_variable_friction_loop_study,
    load_fan_variable_friction_speed_study,
    load_fan_variable_friction_loop_uncertainty,
    load_psychrometric_uncertainty,
    load_thermal_uncertainty,
)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("loader", FILE_LOADERS, ids=lambda loader: loader.__name__)
def test_file_backed_engineering_loaders_reject_non_finite_json(
    tmp_path: Path,
    loader: Callable[[str | Path], object],
    constant: str,
) -> None:
    source = tmp_path / "input.json"
    source.write_text(
        '{"sentinel": ' + constant + '}',
        encoding="utf-8",
    )

    with pytest.raises(StrictJSONError, match="non-finite JSON constant"):
        loader(source)


def test_strict_file_loader_rejects_duplicate_object_keys(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.json"
    source.write_text('{"value": 1, "value": 2}', encoding="utf-8")

    with pytest.raises(StrictJSONError, match="duplicate JSON object key"):
        load_strict_json(source)


@pytest.mark.parametrize("loader", FILE_LOADERS, ids=lambda loader: loader.__name__)
def test_file_backed_engineering_loaders_reject_oversized_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader: Callable[[str | Path], object],
) -> None:
    source = tmp_path / "oversized.json"
    source.write_text('{"sentinel": 12345}', encoding="utf-8")
    monkeypatch.setattr(strict_json_module, "STRICT_JSON_FILE_MAX_BYTES", 8)

    with pytest.raises(StrictJSONError, match="exceeds maximum supported JSON size"):
        loader(source)


def test_strict_file_loader_accepts_input_at_exact_size_limit(tmp_path: Path) -> None:
    source = tmp_path / "exact-limit.json"
    payload = b'{"value":1}'
    source.write_bytes(payload)

    assert load_strict_json(source, max_bytes=len(payload)) == {"value": 1}


def test_strict_file_snapshot_returns_exact_bytes_passed_to_parser(
    tmp_path: Path,
) -> None:
    source = tmp_path / "snapshot.json"
    payload = b'{"value":1,"label":"exact"}'
    source.write_bytes(payload)

    snapshot = load_strict_json_snapshot(source)

    assert snapshot.value == {"value": 1, "label": "exact"}
    assert snapshot.raw_bytes == payload
    assert snapshot.size == len(payload)
    assert snapshot.mtime_ns == source.stat().st_mtime_ns


def test_strict_file_loader_accepts_windows_path_descriptor_id_divergence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "windows-portable.json"
    source.write_text('{"revision": 1}', encoding="utf-8")
    real_fstat = strict_json_module.os.fstat

    class DivergentOpenedStat:
        def __init__(self, value):
            self.st_dev = value.st_dev + 100
            self.st_ino = value.st_ino + 100
            self.st_size = value.st_size
            self.st_mtime_ns = value.st_mtime_ns
            self.st_ctime_ns = value.st_ctime_ns

    def windows_divergent_fstat(fd):
        return DivergentOpenedStat(real_fstat(fd))

    monkeypatch.setattr(strict_json_module.os, "name", "nt")
    monkeypatch.setattr(strict_json_module.os, "fstat", windows_divergent_fstat)

    assert load_strict_json(source) == {"revision": 1}


def test_strict_file_loader_rejects_ctime_only_descriptor_revision_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "ctime-revision.json"
    source.write_text('{"revision": 1}', encoding="utf-8")
    real_fstat = strict_json_module.os.fstat
    descriptor_stat_calls = 0

    class ChangedStat:
        def __init__(self, value):
            self.st_dev = value.st_dev
            self.st_ino = value.st_ino
            self.st_size = value.st_size
            self.st_mtime_ns = value.st_mtime_ns
            self.st_ctime_ns = value.st_ctime_ns + 1

    def changed_after_read(fd):
        nonlocal descriptor_stat_calls
        value = real_fstat(fd)
        descriptor_stat_calls += 1
        if descriptor_stat_calls == 2:
            return ChangedStat(value)
        return value

    monkeypatch.setattr(strict_json_module.os, "fstat", changed_after_read)

    with pytest.raises(StrictJSONError, match="changed while reading JSON input"):
        load_strict_json(source)

    assert descriptor_stat_calls == 2


def test_strict_file_loader_rejects_path_identity_change_after_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.json"
    replacement = tmp_path / "replacement.json"
    source.write_text('{"revision": 1}', encoding="utf-8")
    replacement.write_text('{"revision": 2}', encoding="utf-8")
    real_stat = Path.stat
    replacement_stat = real_stat(replacement)
    source_stat_calls = 0

    def report_replacement_identity(self: Path, *args, **kwargs):
        nonlocal source_stat_calls
        if self == source:
            source_stat_calls += 1
            if source_stat_calls == 2:
                return replacement_stat
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", report_replacement_identity)

    with pytest.raises(StrictJSONError, match="changed while reading JSON input"):
        load_strict_json(source)

    assert source_stat_calls == 2


def test_strict_file_loader_rejects_path_disappearance_after_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.json"
    source.write_text('{"revision": 1}', encoding="utf-8")
    real_stat = Path.stat
    source_stat_calls = 0

    def disappear_on_live_path_check(self: Path, *args, **kwargs):
        nonlocal source_stat_calls
        if self == source:
            source_stat_calls += 1
            if source_stat_calls == 2:
                raise FileNotFoundError(str(source))
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", disappear_on_live_path_check)

    with pytest.raises(
        StrictJSONError,
        match="changed while reading JSON input",
    ) as raised:
        load_strict_json(source)

    assert source_stat_calls == 2

    assert isinstance(raised.value.__cause__, FileNotFoundError)


@pytest.mark.parametrize("loader", FILE_LOADERS, ids=lambda loader: loader.__name__)
def test_file_backed_engineering_loaders_reject_invalid_utf8(
    tmp_path: Path,
    loader: Callable[[str | Path], object],
) -> None:
    source = tmp_path / "invalid-utf8.json"
    source.write_bytes(b'{"sentinel": "\xff"}')

    with pytest.raises(StrictJSONError, match="valid UTF-8 JSON text") as raised:
        loader(source)

    assert source.name in str(raised.value)
    assert isinstance(raised.value.__cause__, UnicodeDecodeError)


def test_strict_json_parser_normalizes_excessive_nesting() -> None:
    nested = "[" * 2_000 + "0" + "]" * 2_000

    with pytest.raises(
        StrictJSONError,
        match="JSON nesting exceeds the supported parser/validation depth",
    ) as raised:
        strict_json_loads(nested)

    assert isinstance(raised.value.__cause__, RecursionError)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_dossier_manifest_rejects_non_finite_json(
    tmp_path: Path,
    constant: str,
) -> None:
    manifest = tmp_path / "dossier.json"
    manifest.write_text(
        '{"sentinel": ' + constant + '}',
        encoding="utf-8",
    )

    with pytest.raises(StrictJSONError, match="non-finite JSON constant"):
        build_dossier(manifest)


def test_dossier_cli_rejects_non_finite_manifest_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "dossier.json"
    manifest.write_text('{"sentinel": NaN}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["cleanroomx-dossier", str(manifest)])

    assert dossier_main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cleanroomx-dossier: error: invalid manifest:" in captured.err
    assert "non-finite JSON constant" in captured.err
    assert "Traceback" not in captured.err


def test_dossier_cli_rejects_malformed_json_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "malformed-dossier.json"
    manifest.write_text('{"name": "broken",}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["cleanroomx-dossier", str(manifest)])

    assert dossier_main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cleanroomx-dossier: error: invalid manifest:" in captured.err
    assert "Traceback" not in captured.err


def test_dossier_cli_reports_missing_manifest_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "missing-dossier.json"
    monkeypatch.setattr(sys, "argv", ["cleanroomx-dossier", str(manifest)])

    assert dossier_main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cleanroomx-dossier: error: invalid manifest:" in captured.err
    assert str(manifest) in captured.err
    assert "Traceback" not in captured.err


def test_dossier_cli_rejects_invalid_utf8_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "invalid-utf8-dossier.json"
    manifest.write_bytes(b'{"sentinel": "\xff"}')
    monkeypatch.setattr(sys, "argv", ["cleanroomx-dossier", str(manifest)])

    assert dossier_main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cleanroomx-dossier: error: invalid manifest:" in captured.err
    assert "valid UTF-8 JSON text" in captured.err
    assert "Traceback" not in captured.err


def test_dossier_cli_rejects_oversized_manifest_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest = tmp_path / "oversized-dossier.json"
    manifest.write_text('{"sentinel": 12345}', encoding="utf-8")
    monkeypatch.setattr(strict_json_module, "STRICT_JSON_FILE_MAX_BYTES", 8)
    monkeypatch.setattr(sys, "argv", ["cleanroomx-dossier", str(manifest)])

    assert dossier_main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cleanroomx-dossier: error: invalid manifest:" in captured.err
    assert "exceeds maximum supported JSON size" in captured.err
    assert "Traceback" not in captured.err
