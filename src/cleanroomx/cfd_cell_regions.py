"""Explicit cell-center box selections in the synchronized mesh coordinate frame."""
from __future__ import annotations

import math

REGION_SCHEMA = "cleanroomx.cfd-cell-region.v1"
REGION_RULE = "cell center in [minimum, maximum) on each axis; full selected-cell volumes"


def validate_cell_region(region: dict | None) -> dict | None:
    """Return an independent canonical selection; a label does not prove room identity."""
    if region is None:
        return None
    if type(region) is not dict or set(region) != {"schema_version", "label", "bounds_m"}:
        raise ValueError("A cell region requires schema_version, label and bounds_m")
    if region["schema_version"] != REGION_SCHEMA:
        raise ValueError("Unsupported cell-region schema")
    label = region["label"]
    if type(label) is not str or not label.strip() or len(label) > 80 or any(ord(c) < 32 for c in label):
        raise ValueError("Region label must be 1–80 characters without control characters")
    bounds = region["bounds_m"]
    if type(bounds) is not list or len(bounds) != 6:
        raise ValueError("Region bounds require xmin, xmax, ymin, ymax, zmin, zmax in metres")
    if any(type(v) not in (int, float) for v in bounds):
        raise ValueError("Region bounds must be finite numbers")
    try:
        bounds = [float(v) for v in bounds]
    except OverflowError as exc:
        raise ValueError("Region bounds must be finite numbers") from exc
    if not all(math.isfinite(v) for v in bounds):
        raise ValueError("Region bounds must be finite numbers")
    if any(bounds[i] >= bounds[i + 1] for i in (0, 2, 4)):
        raise ValueError("Each region minimum must be smaller than its maximum")
    return {"schema_version": REGION_SCHEMA, "label": label.strip(), "bounds_m": bounds}


def region_contains(center: list[float], bounds: list[float]) -> bool:
    return all(bounds[2 * i] <= center[i] < bounds[2 * i + 1] for i in range(3))
