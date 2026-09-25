from __future__ import annotations

from .markdown import markdown_text


def _number(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"{value:g}"


def markdown_pressure_network_report(result: dict) -> str:
    solver = result["solver"]
    totals = result["mechanical_airflow_totals_m3_h"]
    summary = result["target_summary"]
    lines = [
        (
            "# CleanroomX Room Pressure-Network Report — "
            + markdown_text(result["network"])
        ),
        "",
        "## Solver summary",
        "",
        f"- Status: **{markdown_text(result['status']).upper()}**",
        f"- Method: **{markdown_text(solver['method'])}**",
        f"- Iterations: **{solver['iterations']}**",
        (
            "- Mass-balance tolerance: "
            f"**{solver['mass_balance_tolerance_m3_h']:g} m³/h**"
        ),
        (
            "- Maximum unknown-node mass-balance residual: "
            f"**{solver['max_abs_unknown_node_mass_balance_residual_m3_h']:g} m³/h**"
        ),
        "",
        "## Mechanical airflow totals",
        "",
        "| Supply (m³/h) | Return (m³/h) | Exhaust (m³/h) | Net injection (m³/h) |",
        "| ---: | ---: | ---: | ---: |",
        (
            f"| {totals['supply']:g} | {totals['return']:g} | "
            f"{totals['exhaust']:g} | {totals['net_injection']:g} |"
        ),
        "",
        "## Room / boundary pressures",
        "",
        (
            "| Node | Pressure (Pa) | Fixed | Supply | Return | Exhaust | "
            "Mechanical injection | Balance evidence | Dominant pressure path |"
        ),
        "| --- | ---: | :---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]

    for node in result["nodes"]:
        if node["fixed_pressure"]:
            balance = (
                f"external {node['required_external_balance_m3_h']:g} m³/h"
            )
        else:
            balance = (
                f"residual {node['mass_balance_residual_m3_h']:g} m³/h"
            )
        dominant = node.get("dominant_pressure_path")
        if dominant is None:
            dominant_text = "—"
        else:
            dominant_text = (
                f"{markdown_text(dominant['path'])}: "
                f"{dominant['airflow_m3_h']:g} m³/h "
                f"{markdown_text(dominant['direction'])}"
            )
        lines.append(
            f"| {markdown_text(node['name'])} | {node['pressure_pa']:g} | "
            f"{'yes' if node['fixed_pressure'] else 'no'} | "
            f"{node['supply_m3_h']:g} | {node['return_m3_h']:g} | "
            f"{node['exhaust_m3_h']:g} | "
            f"{node['mechanical_injection_m3_h']:g} | "
            f"{markdown_text(balance)} | {dominant_text} |"
        )

    lines.extend(
        [
            "",
            "## Pressure paths",
            "",
            (
                "| Path | Kind | Model | Direction | ΔP (Pa) | Effective ΔP (Pa) | "
                "Flow (m³/h) | Local dQ/dP (m³/s/Pa) |"
            ),
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for path in result["paths"]:
        lines.append(
            f"| {markdown_text(path['name'])} | "
            f"{markdown_text(path['kind'])} | "
            f"{markdown_text(path['model'])} | "
            f"{markdown_text(path['flow_direction'])} | "
            f"{path['pressure_difference_pa']:g} | "
            f"{path['effective_pressure_difference_pa']:g} | "
            f"{path['airflow_m3_h']:g} | "
            f"{path['local_flow_sensitivity_m3_s_pa']:g} |"
        )

    lines.extend(
        [
            "",
            "## Pressure targets",
            "",
            (
                f"- Configured: **{summary['configured']}**; "
                f"passed: **{summary['passed']}**; "
                f"failed: **{summary['failed']}**"
            ),
        ]
    )
    if result["targets"]:
        lines.extend(
            [
                "",
                "| Target | High node | Low node | Observed ΔP | Minimum | Maximum | Status |",
                "| --- | --- | --- | ---: | ---: | ---: | :---: |",
            ]
        )
        for target in result["targets"]:
            lines.append(
                f"| {markdown_text(target['name'])} | "
                f"{markdown_text(target['high_node'])} | "
                f"{markdown_text(target['low_node'])} | "
                f"{target['observed_delta_pa']:g} | "
                f"{target['minimum_delta_pa']:g} | "
                f"{_number(target['maximum_delta_pa'])} | "
                f"**{target['status'].upper()}** |"
            )
    else:
        lines.append("")
        lines.append("No pressure targets were configured.")

    lines.extend(
        [
            "",
            "## Engineering scope",
            "",
            markdown_text(result["scope_note"]),
            "",
            (
                "The pressure-path coefficients, opening areas, discharge coefficients, "
                "mechanical airflows, offsets, and acceptance targets are project inputs. "
                "CleanroomX does not invent them or treat this steady-state network result "
                "as cleanroom certification, CFD validation, or commissioning/TAB evidence."
            ),
        ]
    )
    return "\n".join(lines) + "\n"
