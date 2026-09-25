from __future__ import annotations

from pathlib import Path

from .jsonio import load_strict_json

from .recovery_models import RecoverySample, RecoveryTestSpec


def recovery_test_from_dict(data: dict) -> RecoveryTestSpec:
    samples = tuple(RecoverySample(**item) for item in data["samples"])
    return RecoveryTestSpec(
        name=data["name"],
        particle_size_um=data["particle_size_um"],
        target_concentration_per_m3=data["target_concentration_per_m3"],
        max_recovery_time_minutes=data.get("max_recovery_time_minutes"),
        instrument_id=data.get("instrument_id"),
        sample_location=data.get("sample_location"),
        occupancy_state=data.get("occupancy_state"),
        method_reference=data.get("method_reference"),
        samples=samples,
    )


def load_recovery_test(path: str | Path) -> RecoveryTestSpec:
    data = load_strict_json(path)
    return recovery_test_from_dict(data)
