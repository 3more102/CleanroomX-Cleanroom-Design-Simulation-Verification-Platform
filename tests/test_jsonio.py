import json

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
from cleanroomx.fan_variable_friction_loop_io import load_fan_variable_friction_loop_study
from cleanroomx.fan_variable_friction_speed_io import load_fan_variable_friction_speed_study
from cleanroomx.fan_variable_friction_uncertainty_io import load_fan_variable_friction_loop_uncertainty
from cleanroomx.hvac_io import load_hvac_project
from cleanroomx.io import load_project, load_room
from cleanroomx.jsonio import load_strict_json, strict_json_dumps, strict_json_loads
from cleanroomx.loop_network_io import load_looped_flow_network
from cleanroomx.psychrometric_uncertainty_io import load_psychrometric_uncertainty
from cleanroomx.qualification_io import load_qualification_uncertainty
from cleanroomx.recovery_io import load_recovery_test
from cleanroomx.thermal_uncertainty_io import load_thermal_uncertainty
from cleanroomx.uncertainty_io import load_uncertain_room


FILE_LOADERS = (
    load_room,
    load_project,
    load_recovery_test,
    load_fan_speed_study,
    load_parallel_flow_network,
    load_fan_operating_point_study,
    load_fan_driven_parallel_network_study,
    load_uncertain_room,
    load_loop_damper_study,
    load_qualification_uncertainty,
    load_fan_loop_speed_study,
    load_fan_system_uncertainty,
    load_fan_duct_network_study,
    load_fan_loop_network_study,
    load_looped_flow_network,
    load_psychrometric_uncertainty,
    load_fan_variable_friction_loop_study,
    load_hvac_project,
    load_fan_variable_friction_speed_study,
    load_thermal_uncertainty,
    load_fan_loop_network_uncertainty,
    load_fan_variable_friction_loop_uncertainty,
    build_dossier,
)


@pytest.mark.parametrize("loader", FILE_LOADERS, ids=lambda item: item.__name__)
@pytest.mark.parametrize("constant", ("NaN", "Infinity", "-Infinity"))
def test_all_engineering_file_loaders_reject_non_finite_json(
    tmp_path, loader, constant
) -> None:
    path = tmp_path / "non_finite.json"
    path.write_text(f'{{"sentinel": {constant}}}', encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="non-finite JSON constant is not allowed",
    ):
        loader(path)


def test_strict_json_round_trip_preserves_standard_values(tmp_path) -> None:
    payload = {"name": "ΔP", "values": [0, 1.25, -3, None, True, False]}
    text = strict_json_dumps(payload, sort_keys=True, ensure_ascii=False)
    assert strict_json_loads(text) == payload

    path = tmp_path / "strict.json"
    path.write_text(text, encoding="utf-8")
    assert load_strict_json(path) == payload


@pytest.mark.parametrize("constant", ("NaN", "Infinity", "-Infinity"))
def test_strict_json_loads_rejects_non_finite_constants(constant) -> None:
    with pytest.raises(
        ValueError,
        match="non-finite JSON constant is not allowed",
    ):
        strict_json_loads(f'{{"value": {constant}}}')


@pytest.mark.parametrize("value", (float("nan"), float("inf"), float("-inf")))
def test_strict_json_dumps_rejects_non_finite_values(value) -> None:
    with pytest.raises(ValueError, match="Out of range float values"):
        strict_json_dumps({"value": value})


def test_strict_json_loads_preserves_json_decode_errors() -> None:
    with pytest.raises(json.JSONDecodeError):
        strict_json_loads('{"value": }')
