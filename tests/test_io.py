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
