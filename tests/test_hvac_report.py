from cleanroomx.hvac import analyze_hvac_project
from cleanroomx.hvac_io import hvac_project_from_dict
from cleanroomx.hvac_report import markdown_hvac_report


def test_markdown_report_includes_air_balance() -> None:
    project = hvac_project_from_dict(
        {
            "name": "Report Demo",
            "rooms": [
                {
                    "name": "Room A",
                    "cleanroom_airflow_m3_h": 1000,
                    "thermal_design": {
                        "room_air": {
                            "dry_bulb_c": 22,
                            "relative_humidity_percent": 45
                        }
                    },
                    "air_balance": {
                        "return_air_m3_h": 900,
                        "leakage_out_m3_h": 100
                    }
                }
            ]
        }
    )
    report = markdown_hvac_report(analyze_hvac_project(project))
    assert "Room air-balance closure" in report
    assert "status `balanced`" in report
