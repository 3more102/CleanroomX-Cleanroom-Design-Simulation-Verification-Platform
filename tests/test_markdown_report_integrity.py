from __future__ import annotations

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
