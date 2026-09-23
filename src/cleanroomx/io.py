from __future__ import annotations

import json
from pathlib import Path

from .models import ParticleRequirement, RoomSpec


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
