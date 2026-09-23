from __future__ import annotations

import json
from pathlib import Path

from .recovery_models import RecoverySample, RecoveryTestSpec


def recovery_test_from_dict(data: dict) -> RecoveryTestSpec:
    samples = tuple(RecoverySample(**item) for item in data["samples"])
    return RecoveryTestSpec(
        name=data["name"],
        particle_size_um=data["particle_size_um"],
        target_concentration_per_m3=data["target_concentration_per_m3"],
        max_recovery_time_minutes=data.get("max_recovery_time_minutes"),
        instrument_id=data.get("instrument_id"),
        instrument_serial_number=data.get("instrument_serial_number"),
        calibration_certificate_id=data.get("calibration_certificate_id"),
        calibration_date=data.get("calibration_date"),
        calibration_due_date=data.get("calibration_due_date"),
        sample_location=data.get("sample_location"),
        occupancy_state=data.get("occupancy_state"),
        method_reference=data.get("method_reference"),
        data_source=data.get("data_source"),
        analyst=data.get("analyst"),
        samples=samples,
    )


def load_recovery_test(path: str | Path) -> RecoveryTestSpec:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return recovery_test_from_dict(data)
