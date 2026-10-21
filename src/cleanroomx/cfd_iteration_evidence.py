"""Independent internal-consistency audit for archived SIMPLE iteration histories.

A stored run hash is an identity *reference*, not proof that the source files
have been re-read. This validator checks the recorded snapshot arithmetic and
reported summary; the original import gate verifies actual OpenFOAM files.
"""
from __future__ import annotations

import math
import re

HISTORY_SCHEMA = "cleanroomx.multizone-iteration-comparison.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _require(test, message):
    if not test:
        raise ValueError(message)


def _number(row, key, *, nonnegative=False):
    _require(isinstance(row, dict), f"Expected recorded data object for {key}")
    value = row.get(key)
    _require(type(value) in (int, float) and math.isfinite(value),
             f"Recorded {key} must be a finite number")
    if nonnegative:
        _require(value >= 0, f"Recorded {key} must be nonnegative")
    return float(value)


def _matching_number(stored, calculated, metric):
    _require(type(stored) in (int, float) and math.isfinite(stored),
             f"Recorded {metric} is missing or nonfinite")
    _require(math.isclose(stored, calculated, rel_tol=1e-12, abs_tol=1e-12),
             f"Recorded {metric} disagrees with saved source snapshots")


def validate_recorded_history_consistency(history):
    """Fail closed on drift/pressure/flux values not derived from saved snapshots.

    This validates a comparison object, not the SHA-256 identity of the original
    OpenFOAM bytes. It neither changes solver results nor authorizes a release.
    """
    _require(isinstance(history, dict) and
             history.get("schema") == HISTORY_SCHEMA and
             history.get("source_schema") == "cleanroomx.multizone-results.v1" and
             history.get("scenario") == "all_doors_open" and
             history.get("engineering_release") == "HOLD" and
             history.get("closed_door_5pa_demonstrated") is False,
             "Recorded history must retain noncertifying all-open-door CFD identity")
    for key in ("source_manifest_sha256", "source_run_receipt_sha256"):
        val = history.get(key)
        _require(type(val) is str and _SHA256.fullmatch(val) is not None,
                 f"Recorded {key} requires a valid SHA-256 source identity")
    _require(type(history.get("pressure_reference_room")) is str and
             bool(history["pressure_reference_room"]),
             "Recorded history lacks a pressure reference room")
    _require(_number(history, "density_kg_m3") > 0,
             "Recorded air density must be positive")
    snaps = history.get("snapshots")
    _require(isinstance(snaps, list) and 2 <= len(snaps) <= 12,
             "History must contain 2–12 saved SIMPLE snapshots")
    _require(isinstance(history.get("door_pressure_direction_changes"), list),
             "History lacks pressure-direction change inventory")
    ref_rooms = ref_doors = None
    previous = None
    previous_index = -math.inf
    direction_changes = []
    for position, snap in enumerate(snaps):
        _require(isinstance(snap, dict), "Malformed saved CFD iteration snapshot")
        iteration = snap.get("iteration")
        _require(type(iteration) is str, "Snapshot SIMPLE iteration identifier must be a string")
        try:
            iteration_number = float(iteration)
        except ValueError as exc:
            raise ValueError("Snapshot SIMPLE iteration must be numeric") from exc
        _require(math.isfinite(iteration_number) and iteration_number >= 0 and
                 iteration_number > previous_index,
                 "Recorded SIMPLE iterations must be finite and increasing")
        previous_index = iteration_number
        _require(type(snap.get("solver_reported_convergence")) is bool,
                 "Recorded solver convergence flag is missing")
        rooms, doors = snap.get("rooms"), snap.get("doors")
        _require(isinstance(rooms, dict) and bool(rooms) and
                 isinstance(doors, dict) and bool(doors),
                 "Recorded room and door source inventories are required")
        if ref_rooms is None:
            ref_rooms = set(rooms)
            ref_doors = set(doors)
            _require(all(type(k) is str for k in ref_rooms | ref_doors),
                     "Room/door identifiers must be strings")
        _require(set(rooms) == ref_rooms and set(doors) == ref_doors,
                 "Recorded room or door inventory changed across saved iterations")
        for name, values in rooms.items():
            _number(values, "mean_pressure_pa")
            _number(values, "mean_speed_m_s", nonnegative=True)
            _number(values, "net_outward_m3_s")
        for name, values in doors.items():
            _number(values, "delta_pa")
            net = _number(values, "net_m3_s")
            forward = _number(values, "forward_m3_s", nonnegative=True)
            reverse = _number(values, "reverse_m3_s", nonnegative=True)
            _number(values, "target_delta_pa")
            _require(math.isclose(net, forward - reverse, rel_tol=1e-8, abs_tol=1e-9),
                     f"Recorded door {name} has inconsistent signed phi components")
            if previous is not None:
                _require(values["target_delta_pa"] == previous["doors"][name]["target_delta_pa"],
                         f"Recorded door {name} design target changed between iterations")
        cell_sum = _number(snap, "sum_absolute_cell_imbalance_m3_s", nonnegative=True)
        cell_max = _number(snap, "max_absolute_cell_imbalance_m3_s", nonnegative=True)
        _require(cell_max <= cell_sum + 1e-12,
                 "Maximum recorded cell imbalance exceeds total absolute cell imbalance")
        _number(snap, "global_signed_boundary_imbalance_m3_s")

        changes = snap.get("change_from_previous_recorded_iteration")
        if previous is None:
            _require(changes is None,
                     "First recorded SIMPLE snapshot must not contain a drift")
        else:
            _require(isinstance(changes, dict) and
                     changes.get("previous_iteration") == previous["iteration"],
                     "Recorded drift is not linked to preceding SIMPLE iteration")
            expected = {
                "max_absolute_room_pressure_change_pa": max(
                    abs(rooms[name]["mean_pressure_pa"] -
                        previous["rooms"][name]["mean_pressure_pa"])
                    for name in ref_rooms),
                "max_absolute_room_speed_change_m_s": max(
                    abs(rooms[name]["mean_speed_m_s"] -
                        previous["rooms"][name]["mean_speed_m_s"])
                    for name in ref_rooms),
                "max_absolute_door_delta_change_pa": max(
                    abs(doors[name]["delta_pa"] -
                        previous["doors"][name]["delta_pa"])
                    for name in ref_doors),
                "max_absolute_door_transfer_change_m3_s": max(
                    abs(doors[name]["net_m3_s"] -
                        previous["doors"][name]["net_m3_s"])
                    for name in ref_doors),
                "sum_absolute_cell_imbalance_change_m3_s":
                    cell_sum - previous["sum_absolute_cell_imbalance_m3_s"],
            }
            for key, value in expected.items():
                _matching_number(changes.get(key), value, key)
            reversed_doors = sorted(
                name for name in ref_doors
                if doors[name]["delta_pa"] * previous["doors"][name]["delta_pa"] < 0
            )
            recorded_reversed = changes.get("doors_with_sign_reversal_since_previous_snapshot")
            _require(type(recorded_reversed) is list and
                     sorted(recorded_reversed, key=str) == reversed_doors,
                     "Recorded door pressure-direction reversals disagree with source snapshots")
            # The canonical builder orders door identifiers by name.
            _require(recorded_reversed == reversed_doors,
                     "Recorded door pressure reversals are not in canonical order")
            direction_changes.extend(
                {"iteration": iteration, "door": name} for name in reversed_doors
            )
        previous = snap
    latest = snaps[-1]
    _require(history.get("latest_iteration") == latest["iteration"] and
             history.get("latest_solver_reported_convergence") is
             latest["solver_reported_convergence"],
             "Last saved iteration and convergence summary disagree")
    _require(history.get("last_saved_snapshot_change") ==
             latest["change_from_previous_recorded_iteration"],
             "Last recorded drift summary differs from saved source snapshots")
    _require(history["door_pressure_direction_changes"] == direction_changes,
             "Recorded door pressure reversal inventory differs from snapshots")
    return True
