from __future__ import annotations


def markdown_air_balance_report(result: dict) -> str:
    lines = [f"# CleanroomX Airflow Balance Report — {result['project']}", ""]
    lines.extend(
        [
            "## Room balance",
            "",
            "| Room | Supply | Return | Exhaust | Transfer in | Transfer out | Net offset | Tendency | Requirements |",
            "|---|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )

    for room in result["rooms"]:
        requirement_status = (
            "PASS" if room["requirements_pass"] else "FAIL"
        ) if room["checks"] else "—"
        lines.append(
            f"| {room['name']} | {room['supply_airflow_m3_h']} | "
            f"{room['return_airflow_m3_h']} | {room['exhaust_airflow_m3_h']} | "
            f"{room['transfer_in_airflow_m3_h']} | "
            f"{room['transfer_out_airflow_m3_h']} | {room['net_offset_m3_h']} | "
            f"{room['pressurization_tendency']} | {requirement_status} |"
        )

    lines.extend(
        [
            "",
            "All airflow values are in m³/h.",
            "",
            "## Facility totals",
            "",
            f"- Supply: **{result['total_supply_airflow_m3_h']} m³/h**",
            f"- Return: **{result['total_return_airflow_m3_h']} m³/h**",
            f"- Exhaust: **{result['total_exhaust_airflow_m3_h']} m³/h**",
            f"- External offset: **{result['facility_external_offset_m3_h']} m³/h**",
            f"- Sum of room offsets: **{result['sum_room_net_offsets_m3_h']} m³/h**",
            f"- Internal-transfer conservation error: **{result['internal_transfer_conservation_error_m3_h']} m³/h**",
            "",
            f"Configured airflow-offset requirements: **{'PASS' if result['all_requirements_pass'] else 'FAIL'}**.",
            "",
            "## Engineering note",
            "",
            result["engineering_note"],
            "",
        ]
    )

    if result["transfers"]:
        lines.extend(["## Room-to-room transfer air", ""])
        for transfer in result["transfers"]:
            lines.append(
                f"- {transfer['from_room']} -> {transfer['to_room']}: "
                f"{transfer['airflow_m3_h']} m³/h"
            )
        lines.append("")

    return "\n".join(lines)
