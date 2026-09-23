from __future__ import annotations


def _fmt(value: object) -> str:
    return "—" if value is None else str(value)


def markdown_fan_variable_friction_loop_uncertainty_report(
    result: dict,
) -> str:
    lines = [
        "# CleanroomX Fan / Variable-Friction Loop Uncertainty Report — "
        f"{result['analysis']}",
        "",
        f"- Status: **{result['status'].upper()}**",
        f"- Fan curve: **{result['fan_curve']}**",
        f"- Loop network: **{result['loop_network']}**",
        f"- Solved corners: **{result['solved_corner_count']}/{result['corner_count']}**",
        "",
        "## Input intervals",
        "",
    ]

    fixed = result["input_intervals"]["fixed_pressure_pa"]
    lines.append(
        f"- Fixed pressure: **{fixed['lower']} to {fixed['upper']} Pa** "
        f"(nominal {fixed['nominal']} Pa)"
    )
    speed = result["input_intervals"].get("fan_speed_ratio")
    if speed is not None:
        lines.append(
            f"- Fan speed ratio: **{speed['lower']} to {speed['upper']}** "
            f"(nominal {speed['nominal']})"
        )
    for airflow, interval in result["input_intervals"].get(
        "fan_curve_pressure_pa", {}
    ).items():
        lines.append(
            f"- Fan pressure at `{airflow} m³/h`: "
            f"**{interval['lower']} to {interval['upper']} Pa** "
            f"(nominal {interval['nominal']} Pa)"
        )
    for point_index, interval in result["input_intervals"].get(
        "fan_curve_airflow_m3_h", {}
    ).items():
        lines.append(
            f"- Fan airflow at point index `{point_index}`: "
            f"**{interval['lower']} to {interval['upper']} m³/h** "
            f"(nominal {interval['nominal']} m³/h)"
        )
    for name, interval in result["input_intervals"][
        "edge_local_loss_coefficient"
    ].items():
        lines.append(
            f"- Edge `{name}` local-loss coefficient K: "
            f"**{interval['lower']} to {interval['upper']}** "
            f"(nominal {interval['nominal']})"
        )
    for name, interval in result["input_intervals"].get(
        "edge_absolute_roughness_m", {}
    ).items():
        lines.append(
            f"- Edge `{name}` Absolute roughness: "
            f"**{interval['lower']} to {interval['upper']} m** "
            f"(nominal {interval['nominal']} m)"
        )
    for name, interval in result["input_intervals"].get(
        "edge_kinematic_viscosity_m2_s", {}
    ).items():
        lines.append(
            f"- Edge `{name}` Kinematic viscosity: "
            f"**{interval['lower']} to {interval['upper']} m²/s** "
            f"(nominal {interval['nominal']} m²/s)"
        )
    for name, interval in result["input_intervals"].get(
        "edge_air_density_kg_m3", {}
    ).items():
        lines.append(
            f"- Edge `{name}` Air density: "
            f"**{interval['lower']} to {interval['upper']} kg/m³** "
            f"(nominal {interval['nominal']} kg/m³)"
        )
    for name, interval in result["input_intervals"].get(
        "edge_length_m", {}
    ).items():
        lines.append(
            f"- Edge `{name}` Duct length: "
            f"**{interval['lower']} to {interval['upper']} m** "
            f"(nominal {interval['nominal']} m)"
        )
    for name, interval in result["input_intervals"].get(
        "edge_circular_diameter_m", {}
    ).items():
        lines.append(
            f"- Edge `{name}` Circular diameter: "
            f"**{interval['lower']} to {interval['upper']} m** "
            f"(nominal {interval['nominal']} m)"
        )
    for name, interval in result["input_intervals"].get(
        "edge_rectangular_width_m", {}
    ).items():
        lines.append(
            f"- Edge `{name}` Rectangular width: "
            f"**{interval['lower']} to {interval['upper']} m** "
            f"(nominal {interval['nominal']} m)"
        )
    for name, interval in result["input_intervals"].get(
        "edge_rectangular_height_m", {}
    ).items():
        lines.append(
            f"- Edge `{name}` Rectangular height: "
            f"**{interval['lower']} to {interval['upper']} m** "
            f"(nominal {interval['nominal']} m)"
        )

    lines.extend(["", "## Nominal operating point", ""])
    nominal = result["nominal_operating_point"]
    if nominal is None:
        lines.append(
            f"Nominal state: **{result['nominal_status']}**; "
            "no nominal operating point is reported."
        )
    else:
        lines.extend(
            [
                f"- Airflow: **{nominal['airflow_m3_h']} m³/h**",
                f"- Fan pressure: **{nominal['fan_pressure_pa']} Pa**",
                f"- System pressure: **{nominal['system_pressure_pa']} Pa**",
            ]
        )

    lines.extend(["", "## Bounded corner envelope", ""])
    envelope = result["operating_point_envelope"]
    if envelope is None:
        lines.append(result["message"])
    else:
        lines.extend(
            [
                "- Airflow: "
                f"**{envelope['airflow_m3_h']['lower']} to "
                f"{envelope['airflow_m3_h']['upper']} m³/h**",
                "- Fan pressure: "
                f"**{envelope['fan_pressure_pa']['lower']} to "
                f"{envelope['fan_pressure_pa']['upper']} Pa**",
                "- System pressure: "
                f"**{envelope['system_pressure_pa']['lower']} to "
                f"{envelope['system_pressure_pa']['upper']} Pa**",
            ]
        )

    power_ranges = result.get("power_corner_ranges")
    if power_ranges is not None:
        lines.extend(["", "## Evaluated power corner ranges", ""])
        labels = {
            "fluid_air_power_kw": "Fluid air power",
            "shaft_power_kw": "Shaft power",
            "electrical_input_kw": "Electrical input",
            "specific_fan_power_w_per_m3_s": "Specific fan power",
        }
        for key, interval in power_ranges["metrics"].items():
            lines.append(
                f"- {labels[key]}: **{interval['lower']} to "
                f"{interval['upper']} {interval['unit']}**"
            )
        lines.extend(["", power_ranges["scope_note"]])

    lines.extend(
        [
            "",
            "## Corner results",
            "",
            "| Fixed pressure Pa | Speed ratio | Fan-point pressures Pa | Fan-point airflows m³/h | Local-loss K values | Physical-input values | Status | Airflow m³/h | Pressure Pa |",
            "|---:|---:|---|---|---|---|---|---:|---:|",
        ]
    )
    for corner in result["corners"]:
        point = corner["operating_point"]
        fan_pressures = ", ".join(
            f"{airflow}={value}"
            for airflow, value in corner.get(
                "fan_curve_pressure_pa", {}
            ).items()
        )
        fan_airflows = ", ".join(
            f"point {point_index}={value}"
            for point_index, value in corner.get(
                "fan_curve_airflow_m3_h", {}
            ).items()
        )
        local_losses = ", ".join(
            f"{name}={value}"
            for name, value in corner[
                "edge_local_loss_coefficient"
            ].items()
        )
        physical_values = []
        for label, key, unit in (
            ("roughness", "edge_absolute_roughness_m", "m"),
            ("viscosity", "edge_kinematic_viscosity_m2_s", "m²/s"),
            ("density", "edge_air_density_kg_m3", "kg/m³"),
            ("length", "edge_length_m", "m"),
            ("diameter", "edge_circular_diameter_m", "m"),
            ("width", "edge_rectangular_width_m", "m"),
            ("height", "edge_rectangular_height_m", "m"),
        ):
            for name, value in corner.get(key, {}).items():
                physical_values.append(
                    f"{name} {label}={value} {unit}"
                )
        lines.append(
            f"| {corner['fixed_pressure_pa']} | "
            f"{corner.get('fan_speed_ratio', '—')} | "
            f"{fan_pressures or '—'} | {fan_airflows or '—'} | "
            f"{local_losses or '—'} | "
            f"{', '.join(physical_values) or '—'} | {corner['status']} | "
            f"{_fmt(None if point is None else point['airflow_m3_h'])} | "
            f"{_fmt(None if point is None else point['system_pressure_pa'])} |"
        )

    traceability = result["traceability"]
    lines.extend(
        [
            "",
            "## Traceability",
            "",
            "- Provenance complete for bounded inputs: "
            f"**{'yes' if traceability['complete'] else 'no'}**",
        ]
    )
    if traceability["missing_provenance"]:
        lines.append(
            "- Missing provenance: "
            + ", ".join(traceability["missing_provenance"])
        )

    lines.extend(
        [
            "",
            "## Engineering note",
            "",
            result["engineering_note"],
            "",
        ]
    )
    return "\n".join(lines)
