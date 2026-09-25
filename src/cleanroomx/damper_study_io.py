from __future__ import annotations

from pathlib import Path

from .jsonio import load_strict_json

from .damper_study import DamperResistanceCase, LoopDamperStudy
from .loop_network_io import looped_flow_network_from_dict


def loop_damper_study_from_dict(data: dict) -> LoopDamperStudy:
    return LoopDamperStudy(
        name=data["name"],
        loop_network=looped_flow_network_from_dict(data["loop_network"]),
        cases=tuple(
            DamperResistanceCase(
                name=case["name"],
                edge_resistance_multipliers=dict(
                    case["edge_resistance_multipliers"]
                ),
            )
            for case in data["cases"]
        ),
    )


def load_loop_damper_study(path: str | Path) -> LoopDamperStudy:
    return loop_damper_study_from_dict(
        load_strict_json(path)
    )
