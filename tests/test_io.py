import json

from cleanroomx.io import load_project


def test_load_project(tmp_path):
    path = tmp_path / "project.json"
    path.write_text(
        json.dumps(
            {
                "name": "Suite",
                "rooms": [
                    {
                        "name": "Process",
                        "length_m": 5,
                        "width_m": 4,
                        "height_m": 3,
                        "supply_airflow_m3_h": 1200,
                        "observed_pressure_pa": 20,
                    },
                    {
                        "name": "Ante",
                        "length_m": 4,
                        "width_m": 3,
                        "height_m": 3,
                        "supply_airflow_m3_h": 720,
                        "observed_pressure_pa": 8,
                    },
                ],
                "pressure_cascade": [
                    {
                        "higher_pressure_room": "Process",
                        "lower_pressure_room": "Ante",
                        "min_delta_pa": 10,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    project = load_project(path)
    assert project.name == "Suite"
    assert len(project.rooms) == 2
    assert project.pressure_cascade[0].min_delta_pa == 10

import pytest

from cleanroomx.json_integrity import DuplicateJSONKeyError, NonFiniteJSONNumberError


def test_domain_loader_rejects_duplicate_engineering_field(tmp_path):
    path = tmp_path / "room.json"
    path.write_text(
        '{"name":"Room","length_m":5,"length_m":50,"width_m":4,"height_m":3,'
        '"supply_airflow_m3_h":1200}',
        encoding="utf-8",
    )

    from cleanroomx.io import load_room

    with pytest.raises(DuplicateJSONKeyError, match="length_m"):
        load_room(path)


def test_domain_loader_rejects_overflow_to_infinity(tmp_path):
    path = tmp_path / "room.json"
    path.write_text(
        '{"name":"Room","length_m":1e400,"width_m":4,"height_m":3,'
        '"supply_airflow_m3_h":1200}',
        encoding="utf-8",
    )

    from cleanroomx.io import load_room

    with pytest.raises(NonFiniteJSONNumberError, match="1e400"):
        load_room(path)
