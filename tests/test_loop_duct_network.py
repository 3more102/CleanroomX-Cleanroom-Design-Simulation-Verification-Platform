from __future__ import annotations

import json
import math

import pytest

from cleanroomx.loop_duct_network import (
    FixedFrictionDuctSection,
    GeometryLoopEdge,
    GeometryLoopNetwork,
    solve_geometry_looped_network,
)
from cleanroomx.loop_duct_network_io import (
    geometry_loop_network_from_dict,
    load_geometry_loop_network,
)
from cleanroomx.loop_duct_network_report import markdown_geometry_loop_report


def _circular_section(
    name: str,
    *,
    length_m: float = 10.0,
    diameter_m: float = 0.5,
    friction_factor: float = 0.02,
    air_density_kg_m3: float = 1.2,
    local_loss_coefficient: float = 1.0,
) -> FixedFrictionDuctSection:
    return FixedFrictionDuctSection(
        name=name,
        length_m=length_m,
        diameter_m=diameter_m,
        friction_factor=friction_factor,
        air_density_kg_m3=air_density_kg_m3,
        local_loss_coefficient=local_loss_coefficient,
    )


def test_circular_section_derives_expected_quadratic_resistance():
    section = _circular_section("S1")
    area = math.pi * 0.5**2 / 4.0
    coefficient = 0.02 * 10.0 / 0.5 + 1.0
    expected = 0.5 * 1.2 * coefficient / area**2
    assert math.isclose(
        section.resistance_pa_per_m3_s_squared,
        expected,
        rel_tol=1e-12,
    )


def test_rectangular_section_uses_hydraulic_diameter():
    section = FixedFrictionDuctSection(
        name="Rect",
        length_m=8.0,
        width_m=0.6,
        height_m=0.3,
        friction_factor=0.018,
        air_density_kg_m3=1.18,
        local_loss_coefficient=0.7,
    )
    expected_dh = 2 * 0.6 * 0.3 / (0.6 + 0.3)
    assert math.isclose(section.hydraulic_diameter_m, expected_dh)
    assert section.resistance_pa_per_m3_s_squared > 0


def test_series_sections_sum_resistance():
    s1 = _circular_section("A", length_m=5.0)
    s2 = _circular_section("B", length_m=7.0, local_loss_coefficient=2.0)
    edge = GeometryLoopEdge(
        name="Edge",
        start_node="N1",
        end_node="N2",
        sections=(s1, s2),
    )
    assert math.isclose(
        edge.resistance_pa_per_m3_s_squared,
        s1.resistance_pa_per_m3_s_squared
        + s2.resistance_pa_per_m3_s_squared,
    )


def test_symmetric_geometry_loop_splits_flow_equally():
    section = _circular_section
    network = GeometryLoopNetwork(
        name="Symmetric geometry loop",
        reference_node="Supply",
        node_injections_m3_h={
            "Supply": 3600.0,
            "Mid": 0.0,
            "Return": -3600.0,
        },
        edges=(
            GeometryLoopEdge(
                "Direct",
                "Supply",
                "Return",
                (section("Direct-1"), section("Direct-2")),
            ),
            GeometryLoopEdge(
                "Upper 1",
                "Supply",
                "Mid",
                (section("Upper-1"),),
            ),
            GeometryLoopEdge(
                "Upper 2",
                "Mid",
                "Return",
                (section("Upper-2"),),
            ),
        ),
    )
    result = solve_geometry_looped_network(network)
    edge = {item["name"]: item for item in result["edges"]}
    assert edge["Direct"]["airflow_m3_h"] == pytest.approx(1800.0, abs=1e-4)
    assert edge["Upper 1"]["airflow_m3_h"] == pytest.approx(1800.0, abs=1e-4)
    assert edge["Upper 2"]["airflow_m3_h"] == pytest.approx(1800.0, abs=1e-4)
    assert result["max_abs_mass_balance_residual_m3_h"] <= 1e-6

def test_section_pressure_sum_matches_solved_edge_pressure():
    network = GeometryLoopNetwork(
        name="Series geometry",
        reference_node="Supply",
        node_injections_m3_h={"Supply": 1800.0, "Return": -1800.0},
        edges=(
            GeometryLoopEdge(
                "Main",
                "Supply",
                "Return",
                (
                    _circular_section("S1", length_m=5.0),
                    _circular_section("S2", length_m=9.0, local_loss_coefficient=1.5),
                ),
            ),
        ),
    )
    result = solve_geometry_looped_network(network)
    edge = result["edges"][0]
    assert edge["section_pressure_drop_sum_pa"] == pytest.approx(
        edge["pressure_difference_pa"],
        abs=2e-6,
    )
    assert abs(edge["geometry_pressure_residual_pa"]) <= 2e-6


def test_loader_rejects_automatic_friction_inputs():
    data = {
        "name": "Unsupported automatic friction",
        "reference_node": "A",
        "node_injections_m3_h": {"A": 100.0, "B": -100.0},
        "edges": [
            {
                "name": "AB",
                "start_node": "A",
                "end_node": "B",
                "sections": [
                    {
                        "name": "S",
                        "length_m": 1.0,
                        "diameter_m": 0.2,
                        "friction_factor": 0.02,
                        "air_density_kg_m3": 1.2,
                        "absolute_roughness_m": 0.0001,
                        "kinematic_viscosity_m2_s": 1.5e-5,
                    }
                ],
            }
        ],
    }
    with pytest.raises(ValueError, match="explicit fixed friction_factor"):
        geometry_loop_network_from_dict(data)


def test_zero_fixed_resistance_is_rejected():
    with pytest.raises(ValueError, match="positive fixed loss"):
        FixedFrictionDuctSection(
            name="Zero",
            length_m=2.0,
            diameter_m=0.3,
            friction_factor=0.0,
            air_density_kg_m3=1.2,
            local_loss_coefficient=0.0,
        )


def test_loader_and_markdown_report(tmp_path):
    section = {
        "length_m": 4.0,
        "diameter_m": 0.35,
        "friction_factor": 0.02,
        "air_density_kg_m3": 1.2,
        "local_loss_coefficient": 0.8,
    }
    data = {
        "name": "Loaded geometry loop",
        "reference_node": "Supply",
        "node_injections_m3_h": {
            "Supply": 1200.0,
            "Mid": 0.0,
            "Return": -1200.0,
        },
        "edges": [
            {
                "name": "Direct",
                "start_node": "Supply",
                "end_node": "Return",
                "sections": [
                    {"name": "Direct-1", **section},
                    {"name": "Direct-2", **section},
                ],
            },
            {
                "name": "Upper 1",
                "start_node": "Supply",
                "end_node": "Mid",
                "sections": [{"name": "Upper-1", **section}],
            },
            {
                "name": "Upper 2",
                "start_node": "Mid",
                "end_node": "Return",
                "sections": [{"name": "Upper-2", **section}],
            },
        ],
    }
    path = tmp_path / "geometry-loop.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    network = load_geometry_loop_network(path)
    result = solve_geometry_looped_network(network)
    markdown = markdown_geometry_loop_report(result)
    assert result["status"] == "solved"
    assert "Geometry-Derived Looped-Duct Report" in markdown
    assert "Section evidence" in markdown
    assert "explicit duct geometry" in result["scope_note"]

