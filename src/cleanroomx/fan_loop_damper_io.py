from __future__ import annotations

import json
from pathlib import Path

from .fan_loop_damper import DamperState, FanLoopDamperStudy
from .fan_loop_network_io import fan_loop_network_study_from_dict


def fan_loop_damper_study_from_dict(data: dict) -> FanLoopDamperStudy:
    return FanLoopDamperStudy(
        name=data["name"],
        base_study=fan_loop_network_study_from_dict(data["base_study"]),
        states=tuple(
            DamperState(
                name=state["name"],
                edge_added_resistance_pa_per_m3_s_squared=dict(
                    state["edge_added_resistance_pa_per_m3_s_squared"]
                ),
            )
            for state in data["damper_states"]
        ),
    )


def load_fan_loop_damper_study(path: str | Path) -> FanLoopDamperStudy:
    return fan_loop_damper_study_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
