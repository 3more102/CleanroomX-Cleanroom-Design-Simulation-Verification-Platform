"""Inspect recorded cell-centred p/U without interpolating across walls.

The canonical importer checks solver evidence before this module is called.
Probes retain that source identity, density and reporting pressure reference;
they do not establish convergence, pointwise accuracy or cleanroom acceptance.
"""
from __future__ import annotations

import copy
from decimal import Context, Decimal, localcontext, ROUND_FLOOR
import json
import math
from pathlib import Path
import re

from .cfd_streamlines import ComputedVelocityGrid, SOURCE_SCHEMA

PROBE_SCHEMA = "cleanroomx.recorded-cell-probe.v1"
EXPORT_SCHEMA = "cleanroomx.recorded-cell-probes.v1"
MAX_PROBES = 100
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _point(values):
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise ValueError("Probe requires three XYZ coordinates in metres")
    return tuple(_number(value, "Probe coordinate") for value in values)


class RecordedCellProbeIndex:
    """Copy one imported field and locate only its occupied regular voxels.

    Cell indices are zero-based rows in the imported OpenFOAM p/U/C arrays.
    Voxels use [centre - pitch/2, centre + pitch/2) on each axis. At a shared
    face, the positive-coordinate cell owns the point. Empty voxels and the
    outer upper face produce no result; a nearest-cell fallback is never used.
    """

    def __init__(self, report):
        if (not isinstance(report, dict) or report.get("schema") != SOURCE_SCHEMA
                or report.get("status") != "computed_fields_require_engineering_review"
                or report.get("scenario") != "all_doors_open"):
            raise ValueError("Import a computed multiroom CFD report before probing")
        iteration = report.get("time_name")
        if (not isinstance(iteration, str) or not iteration
                or _number(float(iteration), "Source iteration") < 0):
            raise ValueError("A recorded SIMPLE iteration is required")
        density = _number(report.get("density_kg_m3"), "Air density")
        if density <= 0:
            raise ValueError("Air density must be positive")
        reference = report.get("pressure_reference")
        if (not isinstance(reference, dict)
                or not isinstance(reference.get("room_id"), str)
                or not reference["room_id"]):
            raise ValueError("A computed reporting pressure reference is required")
        if type(report.get("solver_reported_convergence")) is not bool:
            raise ValueError("Recorded solver convergence status is required")
        provenance = report.get("provenance", {})
        if not isinstance(provenance, dict):
            raise ValueError("Recorded CFD source SHA-256 identities are required")
        for key in ("manifest_sha256", "run_receipt_sha256"):
            if not isinstance(provenance.get(key), str) or not _SHA256.fullmatch(provenance[key]):
                raise ValueError("Recorded CFD source SHA-256 identities are required")
        self.source = {
            "source_iteration": iteration,
            "source_manifest_sha256": provenance["manifest_sha256"],
            "source_run_receipt_sha256": provenance["run_receipt_sha256"],
            "density_kg_m3": density,
            "pressure_reference": copy.deepcopy(reference),
            "solver_reported_convergence": report["solver_reported_convergence"],
        }
        self.grid = ComputedVelocityGrid(report)
        self._base_decimal = tuple(Decimal(str(v)) for v in self.grid.base)
        self._pitch_decimal = tuple(Decimal(str(v)) for v in self.grid.pitch)
        self.cells = []
        self.indices = {}
        for index, cell in enumerate(report["cells"]):
            center = tuple(cell["center_m"])
            velocity = tuple(cell["velocity_m_s"])
            pressure = _number(cell.get("pressure_pa_relative_to_reference"), "Computed pressure")
            room = cell.get("room_id")
            if not isinstance(room, str) or not room:
                raise ValueError("Recorded cell room identity is required")
            key = self._key(center)
            self.indices[key] = index
            self.cells.append((center, velocity, pressure, room))

    def _key(self, point):
        # Binary division can put an exact decimal face (e.g. 0.6 on a 0.1 m
        # grid) just below its integer index. Use the coordinates' recorded
        # decimal representations, without snapping nearby points to a face.
        with localcontext(Context(prec=50)):
            return tuple(int(((Decimal(str(point[i])) - self._base_decimal[i])
                              / self._pitch_decimal[i] + Decimal("0.5"))
                             .to_integral_value(rounding=ROUND_FLOOR)) for i in range(3))

    def probe_at(self, xyz_m, *, room_id="all"):
        """Return the containing cell's recorded value, or None for no fluid."""
        point = _point(xyz_m)
        index = self.indices.get(self._key(point))
        if index is None:
            return None
        center, velocity, pressure, room = self.cells[index]
        if room_id != "all" and room_id != room:
            return None
        return {
            "schema": PROBE_SCHEMA,
            **copy.deepcopy(self.source),
            "cell_index": index,
            "room_id": room,
            "requested_location_m": list(point),
            "cell_center_m": list(center),
            "velocity_m_s": list(velocity),
            "speed_m_s": math.hypot(*velocity),
            "pressure_pa_relative_to_reference": pressure,
            "sampling": "containing_recorded_cell_no_interpolation",
            "engineering_release": "HOLD",
        }


def export_recorded_cell_probes(report, probes, destination):
    """Recheck every selection against the current imported field; create once."""
    if not isinstance(probes, list) or not 1 <= len(probes) <= MAX_PROBES:
        raise ValueError(f"Select 1 to {MAX_PROBES} recorded cell probes before export")
    field = RecordedCellProbeIndex(report)
    checked = []
    for probe in probes:
        if not isinstance(probe, dict):
            raise ValueError("Invalid recorded cell probe")
        expected = field.probe_at(probe.get("requested_location_m"))
        if expected is None or probe != expected:
            raise ValueError("Cell probe is stale, altered or from a different field/reference")
        checked.append(expected)
    payload = {
        "schema": EXPORT_SCHEMA, **copy.deepcopy(field.source),
        "engineering_release": "HOLD", "probes": checked,
        "units": {"location": "m", "velocity": "m/s", "speed": "m/s", "pressure": "Pa"},
        "limitations": [
            "Containing cell-centred values only; no pointwise interpolation or spatial accuracy claim",
            "Pressure is relative to the imported computed room mean, not absolute pressure",
            "SIMPLE iteration is not physical time; probe readings do not establish convergence or compliance",
        ],
    }
    data = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    output = Path(destination)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(data)
    return output
