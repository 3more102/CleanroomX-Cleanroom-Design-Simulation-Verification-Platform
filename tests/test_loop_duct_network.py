import math

import pytest

from cleanroomx.duct import (
    DuctSection,
    analyze_duct_section,
    derive_duct_section_quadratic_resistance,
)
from cleanroomx.loop_duct_network import (
    LoopDuctEdge,
    LoopDuctNetworkStudy,
    analyze_loop_duct_network,
)
from cleanroomx.loop_duct_network_io import loop_duct_network_study_from_dict
from cleanroomx.loop_duct_network_report import markdown_loop_duct_network_report


def test_manual_friction_derives_analytical_quadratic_resistance() -> None:
    section = DuctSection(
        name="Manual edge",
        length_m=10.0,
        airflow_m3_h=1800.0,
        friction_factor=0.02,
        air_density_kg_m3=1.2,
        local_loss_coefficient=1.5,
        diameter_m=0.5,
    )

    result = derive_duct_section_quadratic_resistance(section)
    area = math.pi * 0.5**2 / 4.0
    expected = 0.5 * 1.2 * (0.02 * 10.0 / 0.5 + 1.5) / area**2

    assert result["quadratic_resistance_pa_per_m3_s_squared"] == pytest.approx(
        expected, rel=1e-12
    )
    assert result["reference_pressure_drop_pa"] == pytest.approx(
        expected * 0.5**2, rel=1e-12
    )
    assert result["friction_factor_method"] == "user_input"


def test_auto_friction_reference_drop_matches_duct_analysis() -> None:
    section = DuctSection(
        name="Auto edge",
        length_m=10.0,
        airflow_m3_h=900.0,
        friction_factor=None,
        air_density_kg_m3=1.2,
        local_loss_coefficient=2.0,
        width_m=0.5,
        height_m=0.25,
        absolute_roughness_m=0.00009,
        kinematic_viscosity_m2_s=1.5e-5,
    )

    derived = derive_duct_section_quadratic_resistance(section)
    analyzed = analyze_duct_section(section)

    assert derived["friction_factor_method"] == "colebrook"
    assert derived["reynolds_number"] == pytest.approx(44444.444444, rel=1e-8)
    assert derived["reference_pressure_drop_pa"] == pytest.approx(
        analyzed["total_pressure_drop_pa"], abs=5e-5
    )


def _equal_path_study() -> LoopDuctNetworkStudy:
    common = {
        "length_m": 0.0,
        "airflow_m3_h": 1800.0,
        "friction_factor": 0.0,
        "air_density_kg_m3": 1.2,
        "diameter_m": 1.0,
    }
    return LoopDuctNetworkStudy(
        name="Geometry equal paths",
        node_injections_m3_h={
            "Source": 3600.0,
            "Mid": 0.0,
            "Sink": -3600.0,
        },
        reference_node="Source",
        edges=(
            LoopDuctEdge(
                "Direct",
                "Source",
                "Sink",
                DuctSection(
                    name="Direct section",
                    local_loss_coefficient=2.0,
                    **common,
                ),
            ),
            LoopDuctEdge(
                "Series 1",
                "Source",
                "Mid",
                DuctSection(
                    name="Series 1 section",
                    local_loss_coefficient=1.0,
                    **common,
                ),
            ),
            LoopDuctEdge(
                "Series 2",
                "Mid",
                "Sink",
                DuctSection(
                    name="Series 2 section",
                    local_loss_coefficient=1.0,
                    **common,
                ),
            ),
        ),
    )


def test_geometry_derived_equal_paths_split_flow_equally() -> None:
    result = analyze_loop_duct_network(_equal_path_study())
    flows = {edge["name"]: edge["airflow_m3_h"] for edge in result["edges"]}

    assert flows["Direct"] == pytest.approx(1800.0, abs=1e-6)
    assert flows["Series 1"] == pytest.approx(1800.0, abs=1e-6)
    assert flows["Series 2"] == pytest.approx(1800.0, abs=1e-6)
    assert result["max_abs_mass_balance_residual_m3_h"] <= 1e-6
    assert result["resistance_basis"] == "duct_geometry_at_reference_flow"


def test_reference_friction_is_frozen_when_solved_flow_changes() -> None:
    result = analyze_loop_duct_network(_equal_path_study())
    direct = next(edge for edge in result["edges"] if edge["name"] == "Direct")

    assert direct["reference_airflow_m3_h"] == 1800.0
    assert direct["airflow_m3_h"] == pytest.approx(1800.0, abs=1e-6)
    assert direct["friction_factor_method"] == "user_input"
    assert "holds that resistance fixed" in result["scope_note"]


def test_zero_derived_resistance_is_rejected() -> None:
    study = LoopDuctNetworkStudy(
        name="Zero resistance",
        node_injections_m3_h={"A": 3600.0, "B": -3600.0},
        reference_node="A",
        edges=(
            LoopDuctEdge(
                "AB",
                "A",
                "B",
                DuctSection(
                    name="No loss",
                    length_m=1.0,
                    airflow_m3_h=3600.0,
                    friction_factor=0.0,
                    air_density_kg_m3=1.2,
                    local_loss_coefficient=0.0,
                    diameter_m=0.5,
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="zero derived quadratic resistance"):
        analyze_loop_duct_network(study)


def test_loader_auto_friction_and_markdown_report() -> None:
    study = loop_duct_network_study_from_dict(
        {
            "name": "Loaded geometry loop",
            "reference_node": "Supply",
            "node_injections_m3_h": {
                "Supply": 3600.0,
                "Return": -3600.0,
            },
            "edges": [
                {
                    "name": "Supply duct",
                    "start_node": "Supply",
                    "end_node": "Return",
                    "section": {
                        "length_m": 12.0,
                        "airflow_m3_h": 3600.0,
                        "air_density_kg_m3": 1.2,
                        "local_loss_coefficient": 1.4,
                        "diameter_m": 0.55,
                        "absolute_roughness_m": 0.00009,
                        "kinematic_viscosity_m2_s": 1.5e-5,
                    },
                }
            ],
        }
    )

    result = analyze_loop_duct_network(study)
    report = markdown_loop_duct_network_report(result)

    assert result["status"] == "solved"
    assert result["edges"][0]["friction_factor_method"] == "colebrook"
    assert result["edges"][0]["reynolds_number"] is not None
    assert "Geometry-Derived Looped-Network Report" in report
    assert "Supply duct" in report


def test_duplicate_edge_names_are_rejected() -> None:
    section = DuctSection(
        name="S",
        length_m=0.0,
        airflow_m3_h=1800.0,
        friction_factor=0.0,
        air_density_kg_m3=1.2,
        local_loss_coefficient=1.0,
        diameter_m=1.0,
    )
    study = LoopDuctNetworkStudy(
        name="Duplicate",
        node_injections_m3_h={
            "A": 3600.0,
            "B": 0.0,
            "C": -3600.0,
        },
        reference_node="A",
        edges=(
            LoopDuctEdge("dup", "A", "B", section),
            LoopDuctEdge("dup", "B", "C", section),
        ),
    )

    with pytest.raises(ValueError, match="unique"):
        analyze_loop_duct_network(study)
