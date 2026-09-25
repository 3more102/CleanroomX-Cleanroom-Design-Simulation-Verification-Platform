from __future__ import annotations

import json
from pathlib import Path

import pytest

from cleanroomx.damper_study_io import load_loop_damper_study
from cleanroomx.dossier import build_dossier
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
from cleanroomx.input_json import (
    NonFiniteJSONError,
    load_strict_json,
    strict_json_loads,
)
from cleanroomx.io import load_project, load_room
from cleanroomx.loop_network_io import load_looped_flow_network
from cleanroomx.psychrometric_uncertainty_io import load_psychrometric_uncertainty
from cleanroomx.qualification_io import load_qualification_uncertainty
from cleanroomx.recovery_io import load_recovery_test
from cleanroomx.thermal_uncertainty_io import load_thermal_uncertainty
from cleanroomx.uncertainty_io import load_uncertain_room


FILE_LOADERS = (
    load_room,
    load_project,
    load_hvac_project,
    load_recovery_test,
    load_uncertain_room,
    load_qualification_uncertainty,
    load_parallel_flow_network,
    load_looped_flow_network,
    load_thermal_uncertainty,
    load_psychrometric_uncertainty,
    load_fan_operating_point_study,
    load_fan_system_uncertainty,
    load_fan_speed_study,
    load_fan_duct_network_study,
    load_fan_driven_parallel_network_study,
    load_fan_loop_network_study,
    load_fan_loop_speed_study,
    load_fan_loop_network_uncertainty,
    load_fan_variable_friction_loop_study,
    load_fan_variable_friction_speed_study,
    load_fan_variable_friction_loop_uncertainty,
    load_loop_damper_study,
    build_dossier,
)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_strict_json_rejects_nonfinite_constants(token: str) -> None:
    with pytest.raises(NonFiniteJSONError, match="non-finite JSON constant"):
        strict_json_loads(f'{{"value": {token}}}')


def test_strict_json_rejects_float_overflow_to_infinity() -> None:
    with pytest.raises(NonFiniteJSONError, match="finite floating-point range"):
        strict_json_loads('{"value": 1e400}')


def test_strict_json_preserves_standard_json_decode_errors() -> None:
    with pytest.raises(json.JSONDecodeError):
        strict_json_loads('{"value":')


def test_strict_json_preserves_literal_strings_and_finite_numbers(
    tmp_path: Path,
) -> None:
    source = tmp_path / "valid.json"
    source.write_text(
        '{"label":"NaN Infinity -Infinity","values":[-150.0,0,1e300]}',
        encoding="utf-8",
    )

    assert load_strict_json(source) == {
        "label": "NaN Infinity -Infinity",
        "values": [-150.0, 0, 1e300],
    }


@pytest.mark.parametrize("loader", FILE_LOADERS, ids=lambda item: item.__name__)
def test_all_engineering_file_loaders_reject_nonfinite_json(
    loader,
    tmp_path: Path,
) -> None:
    source = tmp_path / f"{loader.__name__}.json"
    source.write_text('{"value": NaN}', encoding="utf-8")

    with pytest.raises(NonFiniteJSONError, match="NaN"):
        loader(source)
