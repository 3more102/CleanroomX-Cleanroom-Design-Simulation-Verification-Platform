from __future__ import annotations

import json
from pathlib import Path

from .damper_study import DamperCase, DamperSetting, DamperStudy
from .loop_network_io import looped_flow_network_from_dict


def damper_study_from_dict(data: dict) -> DamperStudy:
    return DamperStudy(
        name=data["name"],
        loop_network=looped_flow_network_from_dict(data["loop_network"]),
        cases=tuple(
            DamperCase(
                name=case["name"],
                settings=tuple(
                    DamperSetting(**setting) for setting in case["settings"]
                ),
            )
            for case in data["cases"]
        ),
    )


def load_damper_study(path: str | Path) -> DamperStudy:
    return damper_study_from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
