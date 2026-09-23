import pytest

from cleanroomx.uncertainty import analyze_room_uncertainty
from cleanroomx.uncertainty_io import uncertain_room_from_dict
from cleanroomx.uncertainty_models import Provenance, UncertainRoom, UncertainValue


def uv(
    value: float,
    unit: str,
    uncertainty: float = 0.0,
    source: bool = True,
) -> UncertainValue:
    provenance = (
        Provenance("measurement", "Test source", reference="REF-1")
        if source
        else None
    )
    return UncertainValue(value, unit, uncertainty, provenance)


def test_zero_uncertainty_matches_nominal_ach_and_passes() -> None:
    room = UncertainRoom(
        name="Bay",
        length_m=uv(6, "m"),
        width_m=uv(5, "m"),
        height_m=uv(3, "m"),
        supply_airflow_m3_h=uv(3000, "m3/h"),
        min_ach=30,
    )

    result = analyze_room_uncertainty(room)

    assert result["volume_m3"] == {
        "nominal": 90.0,
        "lower": 90.0,
        "upper": 90.0,
    }
    assert result["ach_1_h"] == pytest.approx(
        {
            "nominal": 33.333333,
            "lower": 33.333333,
            "upper": 33.333333,
        }
    )
    assert result["requirement"]["status"] == "pass"
    assert result["traceability"]["complete"] is True


def test_uncertainty_can_make_requirement_indeterminate() -> None:
    room = UncertainRoom(
        name="Process Bay",
        length_m=uv(6.0, "m", 0.02),
        width_m=uv(5.0, "m", 0.02),
        height_m=uv(3.0, "m", 0.01),
        supply_airflow_m3_h=uv(2700.0, "m3/h", 135.0),
        min_ach=30.0,
    )

    result = analyze_room_uncertainty(room)

    assert result["ach_1_h"]["lower"] < 30.0 < result["ach_1_h"]["upper"]
    assert result["requirement"]["status"] == "indeterminate"


def test_complete_interval_below_requirement_fails() -> None:
    room = UncertainRoom(
        name="Low flow",
        length_m=uv(6.0, "m", 0.01),
        width_m=uv(5.0, "m", 0.01),
        height_m=uv(3.0, "m", 0.01),
        supply_airflow_m3_h=uv(1800.0, "m3/h", 20.0),
        min_ach=25.0,
    )

    assert analyze_room_uncertainty(room)["requirement"]["status"] == "fail"


def test_missing_provenance_is_reported() -> None:
    room = UncertainRoom(
        name="Traceability",
        length_m=uv(6, "m"),
        width_m=uv(5, "m", source=False),
        height_m=uv(3, "m"),
        supply_airflow_m3_h=uv(2700, "m3/h"),
    )

    traceability = analyze_room_uncertainty(room)["traceability"]

    assert traceability["complete"] is False
    assert traceability["missing_provenance"] == ["width_m"]


def test_positive_input_interval_must_not_cross_zero() -> None:
    with pytest.raises(ValueError, match="lower uncertainty bound"):
        UncertainRoom(
            name="Invalid",
            length_m=uv(0.01, "m", 0.02),
            width_m=uv(5, "m"),
            height_m=uv(3, "m"),
            supply_airflow_m3_h=uv(2700, "m3/h"),
        )


def test_dict_loader_builds_provenance() -> None:
    data = {
        "name": "Loader",
        "min_ach": 20,
        "length_m": {
            "value": 4,
            "uncertainty_abs": 0.01,
            "provenance": {
                "source_type": "drawing",
                "source_name": "A-101",
                "revision": "P3",
            },
        },
        "width_m": {"value": 4, "uncertainty_abs": 0.01},
        "height_m": {"value": 3, "uncertainty_abs": 0.01},
        "supply_airflow_m3_h": {"value": 1200, "uncertainty_abs": 50},
    }

    room = uncertain_room_from_dict(data)

    assert room.length_m.provenance is not None
    assert room.length_m.provenance.revision == "P3"
    assert room.supply_airflow_m3_h.unit == "m3/h"
