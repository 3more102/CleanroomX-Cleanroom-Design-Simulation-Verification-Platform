from __future__ import annotations

from cleanroomx.dossier_report import markdown_dossier_report
from cleanroomx.loop_network import LoopedFlowNetwork, QuadraticFlowEdge, solve_looped_network
from cleanroomx.loop_network_report import markdown_looped_network_report
from cleanroomx.markdown import markdown_text
from cleanroomx.uncertainty import analyze_room_uncertainty
from cleanroomx.uncertainty_models import Provenance, UncertainRoom, UncertainValue
from cleanroomx.uncertainty_report import markdown_uncertainty_report


def test_markdown_text_preserves_single_inline_structure() -> None:
    rendered = markdown_text("A | B\r\n*critical* <tag> [ref] \\ path")

    assert rendered == (
        "A \\| B<br>\\*critical\\* &lt;tag&gt; "
        "\\[ref\\] \\\\ path"
    )
    assert "\n" not in rendered


def test_loop_report_escapes_user_names_inside_tables() -> None:
    source = "Supply | North\nWing"
    sink = "Return *South*"
    edge_name = "Main | branch\nA"
    network = LoopedFlowNetwork(
        name="Network | Rev A",
        node_injections_m3_h={source: 3600.0, sink: -3600.0},
        edges=(QuadraticFlowEdge(edge_name, source, sink, 2.0),),
        reference_node=source,
    )

    report = markdown_looped_network_report(solve_looped_network(network))

    assert "Supply \\| North<br>Wing" in report
    assert "Return \\*South\\*" in report
    assert "Main \\| branch<br>A" in report
    assert "| Supply | North" not in report


def test_uncertainty_report_escapes_provenance_table_text() -> None:
    provenance = Provenance(
        "measurement",
        "Meter | A\nBench",
        reference="REF *7* | sheet",
    )
    value = lambda number, unit: UncertainValue(number, unit, 0.0, provenance)
    room = UncertainRoom(
        name="Bay | 1",
        length_m=value(6.0, "m"),
        width_m=value(5.0, "m"),
        height_m=value(3.0, "m"),
        supply_airflow_m3_h=value(3000.0, "m3/h"),
    )

    report = markdown_uncertainty_report(analyze_room_uncertainty(room))

    assert "Meter \\| A<br>Bench" in report
    assert "REF \\*7\\* \\| sheet" in report

def test_dossier_report_escapes_external_text_boundaries() -> None:
    result = {
        "dossier": "Dossier | A\nB",
        "metadata": {
            "project_reference": "REF | A\nB",
            "revision": None,
            "prepared_by": None,
            "notes": None,
        },
        "executive_summary": {
            "state": "complete",
            "adverse_item_count": 0,
            "unresolved_item_count": 0,
            "components": {},
            "scope_note": "Internal scope note.",
        },
        "verification": {
            "rooms": [
                {
                    "room": "Room | A\nB",
                    "ach": 10.0,
                    "findings": [],
                }
            ],
            "pressure_cascade": [],
        },
        "hvac": {
            "total_governing_airflow_m3_h": 1000.0,
            "total_preliminary_cooling_capacity_kw": 1.0,
            "total_preliminary_heating_capacity_kw": 0.0,
            "all_air_balances_pass": True,
            "duct_network": {
                "critical_path": "Path | A\nB",
                "critical_path_pressure_drop_pa": 12.3,
            },
            "branch_flow_network": {
                "critical_terminal": "Terminal | A\nB",
                "critical_path_pressure_drop_pa": 13.4,
            },
            "supply_fan": None,
            "fan_curve_duty_check": None,
        },
        "consistency_checks": {
            "verification_hvac_airflow": {
                "status": "pass",
                "room_airflow_abs_tolerance_m3_h": 0.1,
                "require_same_room_set": False,
                "shared_room_count": 0,
                "mismatch_count": 0,
                "room_airflow_checks": [],
                "verification_only_rooms": ["Verification | only\nroom"],
                "hvac_only_rooms": ["HVAC | only\nroom"],
                "scope_note": "Internal consistency note.",
            }
        },
        "recovery_tests": [],
        "qualification_analyses": [],
        "uncertainty_rooms": [],
        "thermal_uncertainty_analyses": [],
        "psychrometric_uncertainty_analyses": [],
        "fan_operating_point_studies": [],
        "fan_system_uncertainty_analyses": [],
        "fan_duct_network_studies": [],
        "fan_parallel_network_studies": [],
        "fan_speed_studies": [],
        "fan_loop_network_studies": [],
        "fan_loop_uncertainty_analyses": [],
        "fan_loop_speed_studies": [],
        "fan_variable_friction_loop_studies": [],
        "fan_variable_friction_speed_studies": [],
        "damper_studies": [],
        "source_files": [],
    }

    report = markdown_dossier_report(result)

    assert "# CleanroomX Engineering Dossier — Dossier \\| A<br>B" in report
    assert "Project Reference: REF \\| A<br>B" in report
    assert "**Room \\| A<br>B**" in report
    assert "Critical duct path: **Path \\| A<br>B**" in report
    assert "Critical branch-flow terminal: **Terminal \\| A<br>B**" in report
    assert "Verification-only rooms: Verification \\| only<br>room" in report
    assert "HVAC-only rooms: HVAC \\| only<br>room" in report
    assert "REF | A\nB" not in report
    assert "Room | A\nB" not in report

