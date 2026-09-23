from __future__ import annotations

import json
from pathlib import Path

from .recovery_models import RecoverySample, RecoveryTestSpec


def recovery_test_from_dict(data: dict) -> RecoveryTestSpec:
    samples = tuple(RecoverySample(**item) for item in data["samples"])
    return RecoveryTestSpec(
        name=data["name"],
        target_concentration_per_m3=data["target_concentration_per_m3"],
        samples=samples,
        max_recovery_time_minutes=data.get("max_recovery_time_minutes"),
        design_ach=data.get("design_ach"),
        removal_efficiency=data.get("removal_efficiency", 1.0),
    )


def load_recovery_test(path: str | Path) -> RecoveryTestSpec:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return recovery_test_from_dict(data)
