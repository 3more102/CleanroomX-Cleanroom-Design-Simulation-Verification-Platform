from __future__ import annotations

import json
from pathlib import Path

from .recovery_uncertainty_models import (
    RecoveryUncertaintySpec,
    UncertainRecoverySample,
)
from .uncertainty_models import Provenance


def _provenance_from_dict(
    data: dict | None,
) -> Provenance | None:
    return Provenance(**data) if data is not None else None


def recovery_uncertainty_from_dict(
    data: dict,
) -> RecoveryUncertaintySpec:
    samples = tuple(
        UncertainRecoverySample(
            time_minutes=item["time_minutes"],
            concentration_per_m3=(
                item["concentration_per_m3"]
            ),
            concentration_uncertainty_abs=item.get(
                "concentration_uncertainty_abs",
                0.0,
            ),
            provenance=_provenance_from_dict(
                item.get("provenance")
            ),
        )
        for item in data["samples"]
    )
    return RecoveryUncertaintySpec(
        name=data["name"],
        particle_size_um=data["particle_size_um"],
        target_concentration_per_m3=(
            data["target_concentration_per_m3"]
        ),
        samples=samples,
        max_recovery_time_minutes=data.get(
            "max_recovery_time_minutes"
        ),
        instrument_id=data.get("instrument_id"),
        sample_location=data.get("sample_location"),
        occupancy_state=data.get("occupancy_state"),
        method_reference=data.get("method_reference"),
    )


def load_recovery_uncertainty(
    path: str | Path,
) -> RecoveryUncertaintySpec:
    return recovery_uncertainty_from_dict(
        json.loads(
            Path(path).read_text(encoding="utf-8")
        )
    )
