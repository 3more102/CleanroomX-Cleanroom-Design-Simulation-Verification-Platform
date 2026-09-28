from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

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
from cleanroomx.psychrometric_uncertainty_io import load_psychrometric_uncertainty
from cleanroomx.qualification_io import load_qualification_uncertainty
from cleanroomx.recovery_io import load_recovery_test
from cleanroomx.strict_json import StrictJSONError, load_strict_json, strict_json_loads
from cleanroomx.thermal_uncertainty_io import load_thermal_uncertainty
from cleanroomx.uncertainty_io import load_uncertain_room


FILE_LOADERS: tuple[Callable[[str | Path], object], ...] = (
    load_room,
    load_project,
    load_recovery_test,
    load_hvac_project,
    load_parallel_flow_network,
    load_looped_flow_network,
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


def test_dossier_cli_rejects_non_finite_manifest_before_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "dossier.json"
    manifest.write_text('{"sentinel": NaN}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["cleanroomx-dossier", str(manifest)])

    with pytest.raises(StrictJSONError, match="non-finite JSON constant"):
        dossier_main()
