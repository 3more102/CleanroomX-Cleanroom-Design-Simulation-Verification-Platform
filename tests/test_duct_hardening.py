import math

import pytest

from cleanroomx.duct import DuctSection


def make_section(**overrides):
    values = {
        "name": "S",
        "length_m": 5.0,
        "airflow_m3_h": 900.0,
        "friction_factor": 0.02,
        "air_density_kg_m3": 1.2,
        "local_loss_coefficient": 1.0,
        "diameter_m": 0.4,
    }
    values.update(overrides)
    return DuctSection(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("airflow_m3_h", math.nan),
        ("airflow_m3_h", math.inf),
        ("air_density_kg_m3", math.nan),
        ("air_density_kg_m3", math.inf),
        ("friction_factor", math.nan),
        ("friction_factor", math.inf),
        ("local_loss_coefficient", math.nan),
        ("local_loss_coefficient", math.inf),
        ("length_m", math.nan),
        ("length_m", math.inf),
        ("diameter_m", math.nan),
        ("diameter_m", math.inf),
    ],
)
def test_duct_section_rejects_nonfinite_numeric_inputs(field, value) -> None:
    with pytest.raises(ValueError, match="finite"):
        make_section(**{field: value})


def test_rectangular_geometry_rejects_nonfinite_dimension() -> None:
    with pytest.raises(ValueError, match="finite"):
        DuctSection(
            name="R",
            length_m=5.0,
            airflow_m3_h=900.0,
            friction_factor=0.02,
            air_density_kg_m3=1.2,
            width_m=math.inf,
            height_m=0.3,
        )
