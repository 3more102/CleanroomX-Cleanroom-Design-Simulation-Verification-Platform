import pytest

from cleanroomx.damper_study import (
    DamperCase,
    DamperSetting,
    DamperStudy,
    solve_damper_study,
)
from cleanroomx.damper_study_io import damper_study_from_dict
from cleanroomx.damper_study_report import markdown_damper_study_report
from cleanroomx.loop_network import LoopedFlowNetwork, QuadraticFlowEdge


def _network() -> LoopedFlowNetwork:
    return LoopedFlowNetwork(
        name="Two-path damper network",
        node_injections_m3_h={
            "Supply": 3600.0,
            "Mid": 0.0,
            "Return": -3600.0,
        },
        edges=(
            QuadraticFlowEdge("Direct", "Supply", "Return", 2.0),
            QuadraticFlowEdge("Upper 1", "Supply", "Mid", 1.0),
            QuadraticFlowEdge("Upper 2", "Mid", "Return", 1.0),
        ),
        reference_node="Supply",
    )


def _study(added_resistance: float = 6.0) -> DamperStudy:
    return DamperStudy(
        name="Damper branch sweep",
        loop_network=_network(),
        cases=(
            DamperCase(
                name="Throttle direct path",
                settings=(
                    DamperSetting(
                        edge_name="Direct",
                        added_resistance_pa_per_m3_s_squared=added_resistance,
                        position_percent=60.0,
                        setting_label="user case 60%",
                    ),
                ),
            ),
        ),
    )


def test_added_damper_resistance_redistributes_flow() -> None:
    result = solve_damper_study(_study())
    case = result["cases"][0]
    flows = {
        edge["edge_name"]: edge["case_airflow_m3_h"]
        for edge in case["flow_changes"]
    }

    assert result["baseline_solution"]["edges"][0]["airflow_m3_h"] == pytest.approx(
        1800.0, abs=1e-6
    )
    assert flows["Direct"] == pytest.approx(1200.0, abs=1e-5)
    assert flows["Upper 1"] == pytest.approx(2400.0, abs=1e-5)
    assert flows["Upper 2"] == pytest.approx(2400.0, abs=1e-5)
    assert case["pressure_span_change_pa"] > 0.0
    assert case["network_solution"]["max_abs_mass_balance_residual_m3_h"] <= 1e-6


def test_zero_added_resistance_matches_baseline() -> None:
    result = solve_damper_study(_study(0.0))
    case = result["cases"][0]

    for row in case["flow_changes"]:
        assert row["airflow_change_m3_h"] == pytest.approx(0.0, abs=1e-6)
    assert case["pressure_span_change_pa"] == pytest.approx(0.0, abs=1e-9)


def test_unknown_damper_edge_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown edge"):
        DamperStudy(
            name="Bad damper study",
            loop_network=_network(),
            cases=(
                DamperCase(
                    name="Bad case",
                    settings=(
                        DamperSetting(
                            edge_name="Missing",
                            added_resistance_pa_per_m3_s_squared=1.0,
                        ),
                    ),
                ),
            ),
        )


def test_duplicate_edge_setting_is_rejected() -> None:
    with pytest.raises(ValueError, match="same edge"):
        DamperCase(
            name="Duplicate",
            settings=(
                DamperSetting("Direct", 1.0),
                DamperSetting("Direct", 2.0),
            ),
        )


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf")])
def test_invalid_added_resistance_is_rejected(bad: float) -> None:
    with pytest.raises(ValueError):
        DamperSetting("Direct", bad)


@pytest.mark.parametrize("bad", [-0.1, 100.1, float("nan"), float("inf")])
def test_invalid_position_is_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="position_percent"):
        DamperSetting("Direct", 1.0, position_percent=bad)


def test_loader_and_report_preserve_explicit_user_case() -> None:
    study = damper_study_from_dict(
        {
            "name": "Loaded damper study",
            "loop_network": {
                "name": "Loaded loop",
                "reference_node": "Supply",
                "node_injections_m3_h": {
                    "Supply": 3600.0,
                    "Return": -3600.0,
                },
                "edges": [
                    {
                        "name": "Main",
                        "start_node": "Supply",
                        "end_node": "Return",
                        "resistance_pa_per_m3_s_squared": 2.0,
                    }
                ],
            },
            "cases": [
                {
                    "name": "Partly closed",
                    "settings": [
                        {
                            "edge_name": "Main",
                            "added_resistance_pa_per_m3_s_squared": 3.0,
                            "position_percent": 50.0,
                            "setting_label": "manufacturer test point",
                        }
                    ],
                }
            ],
        }
    )
    result = solve_damper_study(study)
    report = markdown_damper_study_report(result)

    setting = result["cases"][0]["settings"][0]
    assert setting["base_resistance_pa_per_m3_s_squared"] == 2.0
    assert setting["added_resistance_pa_per_m3_s_squared"] == 3.0
    assert setting["total_resistance_pa_per_m3_s_squared"] == 5.0
    assert "Damper Case Study" in report
    assert "manufacturer test point" in report
    assert "does not infer a position-to-loss relationship" in result["scope_note"]


def test_geometry_base_basis_is_preserved_in_damper_evidence() -> None:
    study = damper_study_from_dict(
        {
            "name": "Geometry damper study",
            "loop_network": {
                "name": "Geometry loop",
                "reference_node": "Supply",
                "node_injections_m3_h": {
                    "Supply": 3600.0,
                    "Return": -3600.0,
                },
                "edges": [
                    {
                        "name": "Main",
                        "start_node": "Supply",
                        "end_node": "Return",
                        "duct_geometry": {
                            "length_m": 0.0,
                            "air_density_kg_m3": 1.0,
                            "friction_factor": 0.0,
                            "local_loss_coefficient": 2.0,
                            "width_m": 1.0,
                            "height_m": 1.0,
                        },
                    }
                ],
            },
            "cases": [
                {
                    "name": "Added damper loss",
                    "settings": [
                        {
                            "edge_name": "Main",
                            "added_resistance_pa_per_m3_s_squared": 3.0,
                        }
                    ],
                }
            ],
        }
    )
    result = solve_damper_study(study)
    setting = result["cases"][0]["settings"][0]

    assert setting["base_resistance_basis"] == "duct_geometry"
    evidence = result["cases"][0]["network_solution"]["edges"][0][
        "resistance_evidence"
    ]
    assert evidence["base_resistance_basis"] == "duct_geometry"
    assert evidence["source"] == "damper_case_adjustment"
