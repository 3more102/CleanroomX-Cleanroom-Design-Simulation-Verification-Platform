"""Synthetic consistency-gate regression tests; no sample is physical CFD evidence."""
import copy

import pytest

from cleanroomx.cfd_iteration_evidence import validate_recorded_history_consistency
from cleanroomx.cfd_multizone_stability import (
    compare_recorded_iterations, export_recorded_iteration_history,
)
from cleanroomx.cfd_convergence_triage import triage_recorded_convergence
from test_cfd_multizone_stability import _series


def _valid():
    return compare_recorded_iterations(_series())


def test_real_builder_output_remains_self_consistent():
    assert validate_recorded_history_consistency(_valid()) is True
    triage = triage_recorded_convergence(_valid())
    assert triage["engineering_release"] == "HOLD"
    assert triage["numerical_screening"] == "solver_not_converged"


@pytest.mark.parametrize("edit,description", [
    (lambda h: h["snapshots"][1]["rooms"]["A"].update(mean_pressure_pa=999),
     "max_absolute_room_pressure_change_pa"),
    (lambda h: h["snapshots"][1]["rooms"]["A"].update(mean_speed_m_s=.11),
     "max_absolute_room_speed_change_m_s"),
    (lambda h: h["snapshots"][1]["doors"]["AB"].update(
        net_m3_s=.5, forward_m3_s=.55), "max_absolute_door_transfer_change_m3_s"),
    (lambda h: h["snapshots"][1]["doors"]["AB"].update(delta_pa=99),
     "max_absolute_door_delta_change_pa"),
    (lambda h: h["snapshots"][1].update(sum_absolute_cell_imbalance_m3_s=.6),
     "sum_absolute_cell_imbalance_change_m3_s"),
    (lambda h: h["snapshots"][1]["change_from_previous_recorded_iteration"].update(
        max_absolute_room_speed_change_m_s=0), "max_absolute_room_speed_change_m_s"),
    (lambda h: h["snapshots"][1]["change_from_previous_recorded_iteration"].update(
        doors_with_sign_reversal_since_previous_snapshot=["AB"]),
     "pressure-direction reversals"),
    (lambda h: h.update(door_pressure_direction_changes=[
        {"iteration": "50", "door": "AB"}]), "reversal inventory"),
    (lambda h: h["snapshots"][1]["rooms"].pop("B"), "inventory changed"),
    (lambda h: h["snapshots"][1]["doors"]["AB"].update(forward_m3_s=-.3),
     "nonnegative"),
    (lambda h: h["snapshots"][1].update(max_absolute_cell_imbalance_m3_s=10),
     "exceeds total"),
    (lambda h: h["snapshots"][0]["rooms"]["A"].update(mean_speed_m_s=True),
     "finite number"),
])
def test_modified_saved_evidence_fails_closed(edit, description):
    history = _valid()
    edit(history)
    with pytest.raises(ValueError, match=description):
        validate_recorded_history_consistency(history)


def test_tampering_with_both_last_drift_and_summary_does_not_bypass_audit(tmp_path):
    history = _valid()
    change = history["snapshots"][-1]["change_from_previous_recorded_iteration"]
    change["max_absolute_room_pressure_change_pa"] = .00001
    history["last_saved_snapshot_change"] = copy.deepcopy(change)
    with pytest.raises(ValueError, match="max_absolute_room_pressure_change_pa"):
        triage_recorded_convergence(history)
    target = tmp_path / "must-not-be-created"
    with pytest.raises(ValueError, match="max_absolute_room_pressure_change_pa"):
        export_recorded_iteration_history(history, target)
    assert not target.exists()


def test_altered_snapshot_room_speed_cannot_be_exported(tmp_path):
    history = _valid()
    history["snapshots"][1]["rooms"]["A"]["mean_speed_m_s"] += 1
    target = tmp_path / "bad-history"
    with pytest.raises(ValueError, match="max_absolute_room_speed_change_m_s"):
        export_recorded_iteration_history(history, target)
    assert not target.exists()


def test_valid_history_csv_and_json_still_export(tmp_path):
    destination = tmp_path / "recorded-iterations"
    saved = export_recorded_iteration_history(_valid(), destination)
    assert saved.is_file()
    assert (destination / "iteration-evolution.csv").is_file()
    assert "max_absolute_room_speed_change_m_s" in (
        destination / "iteration-evolution.csv").read_text()
