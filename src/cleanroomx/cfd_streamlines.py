"""Trace *steady streamlines* through recorded OpenFOAM cell-centred velocity.

No synthetic flow field, interpolation across missing cells, particle inertia,
diffusion, deposition, or transient time stepping is claimed. The integration
parameter has dimensions of seconds but is NOT a CFD transient simulation.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

SOURCE_SCHEMA = "cleanroomx.multizone-results.v1"
TRACE_SCHEMA = "cleanroomx.steady-streamline.v1"


def _finite(value, name):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


class ComputedVelocityGrid:
    """Bounded regular occupied-voxel lookup; missing voxels are solid/outside."""

    def __init__(self, report: dict):
        if report.get("schema") != SOURCE_SCHEMA or not report.get("cells"):
            raise ValueError("A nonempty computed multiroom CFD report is required")
        self.pitch = tuple(_finite(x, "voxel pitch") for x in report["voxel_pitch_m"])
        if len(self.pitch) != 3 or any(x <= 0 for x in self.pitch):
            raise ValueError("Invalid CFD voxel pitch")
        cells = report["cells"]
        self.base = tuple(min(_finite(c["center_m"][i], "cell centre") for c in cells)
                          for i in range(3))
        self.data = {}
        for cell in cells:
            center = tuple(_finite(x, "cell centre") for x in cell["center_m"])
            velocity = tuple(_finite(x, "computed velocity") for x in cell["velocity_m_s"])
            if len(center) != 3 or len(velocity) != 3:
                raise ValueError("Expected three-dimensional CFD samples")
            index = tuple(round((center[i] - self.base[i]) / self.pitch[i])
                          for i in range(3))
            if any(not math.isclose(center[i], self.base[i] + index[i]*self.pitch[i],
                                    rel_tol=0, abs_tol=1e-6) for i in range(3)):
                raise ValueError("Computed centres must lie on the recorded voxel lattice")
            if index in self.data:
                raise ValueError("Duplicate computed velocity cell")
            self.data[index] = (velocity, cell["room_id"])

    def cell_at(self, xyz):
        point = tuple(_finite(v, "trace coordinate") for v in xyz)
        if len(point) != 3:
            raise ValueError("Expected a three-dimensional trace coordinate")
        index = tuple(math.floor((point[i] - self.base[i]) / self.pitch[i] + 0.5)
                      for i in range(3))
        found = self.data.get(index)
        if found is None:
            return None
        if any(abs(point[i] - (self.base[i] + index[i]*self.pitch[i]))
               > self.pitch[i]/2 + 1e-9 for i in range(3)):
            return None
        return found

    def connected_segment(self, start, end):
        """Do not permit an integration step to jump over missing fluid voxels."""
        length = math.dist(start, end)
        samples = max(2, math.ceil(length/(min(self.pitch)/8)))
        for n in range(1, samples+1):
            fraction = n/samples
            xyz = tuple(start[i] + fraction*(end[i]-start[i]) for i in range(3))
            if self.cell_at(xyz) is None:
                return False
        return True


def trace_computed_streamline(report: dict, seed_m, *,
                              max_integration_s: float = 20.0,
                              step_fraction: float = 0.25,
                              max_steps: int = 800,
                              min_speed_m_s: float = 1e-9) -> dict:
    """Follow a recorded steady U field using bounded midpoint (RK2) steps.

    Cell-centred U is used as a piecewise constant reconstruction. A step is
    rejected on entering an unoccupied voxel; no wall crossing is manufactured.
    Routes cannot establish particle dynamics, recirculation, or compliance.
    """
    duration = _finite(max_integration_s, "max_integration_s")
    fraction = _finite(step_fraction, "step_fraction")
    min_speed = _finite(min_speed_m_s, "min_speed_m_s")
    if duration <= 0 or not 0 < fraction <= 0.5 or min_speed < 0:
        raise ValueError("Invalid streamline integration limits")
    if type(max_steps) is not int or not 1 <= max_steps <= 10000:
        raise ValueError("max_steps must be an integer between 1 and 10000")
    grid = ComputedVelocityGrid(report)
    point = tuple(_finite(x, "seed coordinate") for x in seed_m)
    if len(point) != 3 or grid.cell_at(point) is None:
        raise ValueError("Seed must lie inside a recorded CFD fluid cell")
    points = []
    elapsed = 0.0
    max_step_m = min(grid.pitch) * fraction
    reason = "max_steps"
    for _ in range(max_steps+1):
        sample = grid.cell_at(point)
        if sample is None:  # Defensive; an external report must never invent fluid.
            reason = "domain_exit"
            break
        velocity, room = sample
        speed = math.sqrt(math.fsum(component*component for component in velocity))
        points.append({"xyz_m":list(point), "integration_parameter_s":elapsed,
                       "speed_m_s":speed, "room_id":room})
        if speed <= min_speed:
            reason = "stagnation"
            break
        if elapsed >= duration - 1e-12:
            reason = "max_integration_parameter"
            break
        if len(points) > max_steps:
            reason = "max_steps"
            break
        dt = min(max_step_m/speed, duration-elapsed)
        midpoint = tuple(point[i] + velocity[i]*dt/2 for i in range(3))
        mid_cell = grid.cell_at(midpoint)
        if mid_cell is None:
            reason = "domain_exit"
            break
        velocity_mid = mid_cell[0]
        end = tuple(point[i] + velocity_mid[i]*dt for i in range(3))
        if not grid.connected_segment(point, end):
            reason = "domain_exit"
            break
        if math.dist(point, end) <= 1e-15:
            reason = "stagnation"
            break
        point = end
        elapsed += dt
    provenance = report.get("provenance", {})
    return {
        "schema":TRACE_SCHEMA, "source_schema":SOURCE_SCHEMA,
        "source_iteration":report.get("time_name"),
        "source_manifest_sha256":provenance.get("manifest_sha256"),
        "source_run_receipt_sha256":provenance.get("run_receipt_sha256"),
        "method":"Piecewise-constant recorded cell U; bounded RK2 steady streamline",
        "integration_parameter_not_physical_transient_time":True,
        "validated_particle_tracking":False,
        "step_fraction_of_smallest_voxel":fraction,
        "max_integration_parameter_s":duration,
        "termination":reason, "points":points,
    }


def export_computed_streamlines(traces: list[dict], destination: str | Path) -> Path:
    """Write explicit, provenance-tagged steady traces without overwriting files."""
    if not traces or len(traces) > 20:
        raise ValueError("Export requires one to twenty computed traces")
    source = traces[0]
    if any(trace.get("schema") != TRACE_SCHEMA or
           trace.get("source_manifest_sha256") != source.get("source_manifest_sha256") or
           trace.get("source_run_receipt_sha256") != source.get("source_run_receipt_sha256") or
           trace.get("source_iteration") != source.get("source_iteration")
           for trace in traces):
        raise ValueError("All traces must come from one recorded CFD iteration")
    payload = {
        "schema": "cleanroomx.steady-streamline-collection.v1",
        "validation": "steady_visualization_only_not_particle_transport",
        "source_iteration": source["source_iteration"],
        "source_manifest_sha256": source["source_manifest_sha256"],
        "source_run_receipt_sha256": source["source_run_receipt_sha256"],
        "units": {"xyz_m": "m", "speed_m_s": "m/s",
                  "integration_parameter_s": "steady-field integration parameter, NOT solver transient time"},
        "traces": traces,
    }
    serialized = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    path = Path(destination)
    with path.open("x", encoding="utf-8") as output:
        output.write(serialized)
    return path
