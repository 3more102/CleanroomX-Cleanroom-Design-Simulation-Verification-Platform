import json

from cleanroomx.hvac import analyze_hvac_project
from cleanroomx.hvac_io import load_hvac_project


def test_hvac_project_load_and_analysis(tmp_path) -> None:
    path = tmp_path / "hvac.json"
    path.write_text(
        json.dumps(
            {
                "name": "HVAC Demo",
                "filter_unit": {
                    "name": "FFU",
                    "rated_airflow_m3_h": 1200,
                    "design_utilization": 0.9
                },
                "rooms": [
                    {
                        "name": "Process",
                        "cleanroom_airflow_m3_h": 2000,
                        "thermal_design": {
                            "room_air": {
                                "dry_bulb_c": 22,
                                "relative_humidity_percent": 45
                            },
                            "loads": {"equipment_w": 8000},
                            "supply_air_temp_c": 16
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = analyze_hvac_project(load_hvac_project(path))
    room = result["rooms"][0]
    assert room["governing_airflow_m3_h"] > 2000
    assert room["filter_units"] is not None
    assert result["total_preliminary_cooling_capacity_kw"] == 8.0
