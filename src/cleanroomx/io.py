from __future__ import annotations

import json
from pathlib import Path

from .models import ParticleRequirement, PressureCascadeSpec, PressureRequirement, PressureZone, RoomSpec


def load_room(path: str | Path) -> RoomSpec:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    particle_requirements = tuple(
        ParticleRequirement(
            size_um=item["size_um"],
            max_concentration_per_m3=item["max_concentration_per_m3"],
            observed_concentration_per_m3=item["observed_concentration_per_m3"],
        )
        for item in data.get("particle_requirements", [])
    )
    return RoomSpec(
        name=data["name"],
        length_m=data["length_m"],
        width_m=data["width_m"],
        height_m=data["height_m"],
        supply_airflow_m3_h=data["supply_airflow_m3_h"],
        min_ach=data.get("min_ach"),
        min_pressure_pa=data.get("min_pressure_pa"),
        observed_pressure_pa=data.get("observed_pressure_pa"),
        particle_requirements=particle_requirements,
    )


def load_pressure_cascade(path: str | Path) -> PressureCascadeSpec:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    zones = tuple(
        PressureZone(name=item["name"], observed_pressure_pa=item["observed_pressure_pa"])
        for item in data["zones"]
    )
    requirements = tuple(
        PressureRequirement(
            high_zone=item["high_zone"],
            low_zone=item["low_zone"],
            min_delta_pa=item["min_delta_pa"],
        )
        for item in data["requirements"]
    )
    return PressureCascadeSpec(name=data["name"], zones=zones, requirements=requirements)
