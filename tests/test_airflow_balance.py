import json

import pytest

from cleanroomx.airflow_balance import (
    AirBalanceProject,
    RoomAirflow,
    TransferAirflow,
    analyze_air_balance,
)
from cleanroomx.airflow_io import load_air_balance_project


def test_room_and_facility_balance_with_transfer_air() -> None:
    project = AirBalanceProject(
        name="Suite",
        rooms=(
            RoomAirflow(
                name="Process",
                supply_airflow_m3_h=3000,
                return_airflow_m3_h=2400,
                exhaust_airflow_m3_h=200,
                min_net_offset_m3_h=200,
            ),
            RoomAirflow(
                name="Ante",
                supply_airflow_m3_h=800,
                return_airflow_m3_h=900,
                min_net_offset_m3_h=0,
                max_net_offset_m3_h=100,
            ),
        ),
        transfers=(
            TransferAirflow(
                from_room="Process",
                to_room="Ante",
                airflow_m3_h=150,
            ),
        ),
    )

    result = analyze_air_balance(project)
    process, ante = result["rooms"]

    assert process["net_offset_m3_h"] == 250.0
    assert process["pressurization_tendency"] == "positive"
    assert ante["net_offset_m3_h"] == 50.0
    assert result["facility_external_offset_m3_h"] == 300.0
    assert result["sum_room_net_offsets_m3_h"] == 300.0
    assert result["internal_transfer_conservation_error_m3_h"] == 0.0
    assert result["all_requirements_pass"] is True


def test_configured_offset_requirement_can_fail() -> None:
    project = AirBalanceProject(
        name="Negative room",
        rooms=(
            RoomAirflow(
                name="Containment",
                supply_airflow_m3_h=800,
                return_airflow_m3_h=900,
                exhaust_airflow_m3_h=100,
                max_net_offset_m3_h=-250,
            ),
        ),
    )

    result = analyze_air_balance(project)

    assert result["rooms"][0]["net_offset_m3_h"] == -200.0
    assert result["rooms"][0]["pressurization_tendency"] == "negative"
    assert result["rooms"][0]["requirements_pass"] is False
    assert result["all_requirements_pass"] is False


def test_loader_reads_project_json(tmp_path) -> None:
    path = tmp_path / "balance.json"
    path.write_text(
        json.dumps(
            {
                "name": "Demo",
                "rooms": [
                    {
                        "name": "A",
                        "supply_airflow_m3_h": 1000,
                        "return_airflow_m3_h": 800,
                    },
                    {
                        "name": "B",
                        "supply_airflow_m3_h": 600,
                        "return_airflow_m3_h": 700,
                    },
                ],
                "transfers": [
                    {
                        "from_room": "A",
                        "to_room": "B",
                        "airflow_m3_h": 100,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    project = load_air_balance_project(path)
    result = analyze_air_balance(project)

    assert project.name == "Demo"
    assert result["rooms"][0]["net_offset_m3_h"] == 100.0
    assert result["rooms"][1]["net_offset_m3_h"] == 0.0


def test_unknown_transfer_room_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown room"):
        AirBalanceProject(
            name="Bad",
            rooms=(RoomAirflow("A", 1000),),
            transfers=(TransferAirflow("A", "Missing", 100),),
        )


def test_duplicate_transfer_link_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate transfer-airflow link"):
        AirBalanceProject(
            name="Bad",
            rooms=(RoomAirflow("A", 1000), RoomAirflow("B", 1000)),
            transfers=(
                TransferAirflow("A", "B", 100),
                TransferAirflow("A", "B", 50),
            ),
        )


def test_invalid_offset_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        RoomAirflow(
            name="A",
            supply_airflow_m3_h=1000,
            min_net_offset_m3_h=200,
            max_net_offset_m3_h=100,
        )
