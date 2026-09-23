import pytest

from cleanroomx.duct import DuctNetwork, DuctPath, DuctSection
from cleanroomx.fan_curve import FanCurve, FanCurvePoint
from cleanroomx.fan_duct_network import (
    FanDuctNetworkStudy,
    analyze_fan_duct_network,
)
from cleanroomx.fan_duct_network_io import (
    fan_duct_network_study_from_dict,
)


def _curve() -> FanCurve:
    return FanCurve(
        "Supply fan",
        (
            FanCurvePoint(0, 600),
            FanCurvePoint(3000, 500),
            FanCurvePoint(6000, 300),
            FanCurvePoint(8000, 100),
        ),
    )


def _network() -> DuctNetwork:
    return DuctNetwork(
        paths=(
            DuctPath(
                "Path A",
                (
                    DuctSection(
                        "A1",
                        length_m=10,
                        airflow_m3_h=900,
                        friction_factor=0.02,
                        air_density_kg_m3=1.2,
                        local_loss_coefficient=2,
                        width_m=0.5,
                        height_m=0.25,
                    ),
                ),
            ),
            DuctPath(
                "Path B",
                (
                    DuctSection(
                        "B1",
                        length_m=20,
                        airflow_m3_h=900,
                        friction_factor=0.02,
                        air_density_kg_m3=1.2,
                        local_loss_coefficient=3,
                        width_m=0.5,
                        height_m=0.25,
                    ),
                ),
            ),
        )
    )


def test_derives_critical_path_and_solves_fan_operating_point() -> None:
    result = analyze_fan_duct_network(
        FanDuctNetworkStudy(
            "Integrated demo",
            _curve(),
            _network(),
            reference_system_airflow_m3_h=900,
            fixed_pressure_pa=80,
        )
    )

    assert result["critical_path"] == "Path B"
    assert (
        result[
            "critical_path_quadratic_resistance_pa_per_m3_s_squared"
        ]
        == pytest.approx(161.28)
    )
    assert result["critical_path_reference_pressure_drop_pa"] == pytest.approx(
        10.08
    )
    assert result["status"] == "solved"
    assert result["operating_point"]["airflow_m3_h"] == pytest.approx(
        4871.01, abs=0.01
    )
    assert result["operating_point"]["system_pressure_pa"] == pytest.approx(
        375.266, abs=0.01
    )

    path_b = next(
        path for path in result["paths"] if path["name"] == "Path B"
    )
    assert path_b["operating_pressure_drop_pa"] == pytest.approx(
        295.266, abs=0.02
    )


def test_reference_flow_ratio_scales_section_resistance() -> None:
    network = DuctNetwork(
        paths=(
            DuctPath(
                "Scaled path",
                (
                    DuctSection(
                        "Half-flow branch",
                        length_m=10,
                        airflow_m3_h=450,
                        friction_factor=0.02,
                        air_density_kg_m3=1.2,
                        local_loss_coefficient=2,
                        width_m=0.5,
                        height_m=0.25,
                    ),
                ),
            ),
        )
    )
    result = analyze_fan_duct_network(
        FanDuctNetworkStudy(
            "Scaled demo",
            _curve(),
            network,
            reference_system_airflow_m3_h=900,
            fixed_pressure_pa=80,
        )
    )

    assert (
        result[
            "critical_path_quadratic_resistance_pa_per_m3_s_squared"
        ]
        == pytest.approx(24.96)
    )
    assert result["critical_path_reference_pressure_drop_pa"] == pytest.approx(
        1.56
    )


def test_rejects_section_reference_flow_above_system_reference() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        FanDuctNetworkStudy(
            "Bad reference",
            _curve(),
            _network(),
            reference_system_airflow_m3_h=800,
            fixed_pressure_pa=80,
        )


def test_rejects_zero_derived_path_resistance() -> None:
    network = DuctNetwork(
        paths=(
            DuctPath(
                "Zero path",
                (
                    DuctSection(
                        "Zero-loss section",
                        length_m=10,
                        airflow_m3_h=900,
                        friction_factor=0,
                        air_density_kg_m3=1.2,
                        local_loss_coefficient=0,
                        width_m=0.5,
                        height_m=0.25,
                    ),
                ),
            ),
        )
    )

    with pytest.raises(ValueError, match="zero derived"):
        analyze_fan_duct_network(
            FanDuctNetworkStudy(
                "Zero",
                _curve(),
                network,
                reference_system_airflow_m3_h=900,
            )
        )


def test_json_loader_builds_integrated_study() -> None:
    study = fan_duct_network_study_from_dict(
        {
            "name": "Loaded",
            "reference_system_airflow_m3_h": 900,
            "fixed_pressure_pa": 80,
            "fan_curve": {
                "name": "Fan",
                "points": [
                    {"airflow_m3_h": 0, "pressure_pa": 600},
                    {"airflow_m3_h": 6000, "pressure_pa": 300},
                ],
            },
            "duct_network": {
                "paths": [
                    {
                        "name": "Path",
                        "sections": [
                            {
                                "name": "S1",
                                "length_m": 10,
                                "airflow_m3_h": 900,
                                "friction_factor": 0.02,
                                "air_density_kg_m3": 1.2,
                                "local_loss_coefficient": 2,
                                "width_m": 0.5,
                                "height_m": 0.25,
                            }
                        ],
                    }
                ]
            },
        }
    )

    assert study.name == "Loaded"
    assert study.reference_system_airflow_m3_h == 900
    assert study.duct_network.paths[0].sections[0].airflow_m3_h == 900
