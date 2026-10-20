"""Parser regression fixtures only; real solver evidence is tested separately."""
import pytest

from cleanroomx.cfd_multizone_results import solver_iteration_diagnostics


CONTROLS = "SIMPLE { residualControl { p 1e-5; U 1e-6; } }"


def _iteration(number, initial):
    return f"Time = {number}s\n" + "\n".join(
        f"solver: Solving for {field}, Initial residual = {initial}, Final residual = 1e-9, No Iterations 2"
        for field in ("p", "Ux", "Uy", "Uz")
    ) + "\ntime step continuity errors : sum local = 1e-8, global = -2e-10, cumulative = -3e-9\n"


def test_earlier_fields_never_inherit_later_convergence_or_linear_final_residuals():
    log = _iteration(1, ".01") + _iteration(2, "1e-7") + "SIMPLE solution converged in 2 iterations\n"
    history, first = solver_iteration_diagnostics(log, CONTROLS, "1")
    assert len(history) == 8
    assert first["run_reported_convergence"]
    assert first["solver_convergence_iteration"] == 2
    assert not first["selected_iteration_reported_convergence"]
    assert not first["selected_initial_residuals_below_limits"]
    assert first["fields"]["p"]["last_final_linear_residual"] < 1e-5
    assert first["fields"]["p"]["first_initial_residual"] > 1e-5
    assert first["selected_log_continuity_errors"]["global"] == -2e-10
    _, last = solver_iteration_diagnostics(log, CONTROLS, "2")
    assert last["selected_iteration_reported_convergence"]
    assert last["selected_initial_residuals_below_limits"]


def test_limits_are_explicit_and_no_marker_is_inferred_from_small_residuals():
    log = _iteration(1, "1e-9")
    _, report = solver_iteration_diagnostics(log, "SIMPLE {}", "1")
    assert report["selected_initial_residuals_below_limits"] is None
    assert report["fields"]["p"]["configured_initial_residual_limit"] is None
    assert not report["run_reported_convergence"]
    _, report = solver_iteration_diagnostics(log, CONTROLS, "1")
    assert report["selected_initial_residuals_below_limits"]
    assert not report["selected_iteration_reported_convergence"]


@pytest.mark.parametrize("log,selected,match", [
    (_iteration(1, ".01"), "2", "lack complete"),
    (_iteration(1, "-1"), "1", "Invalid solver residual"),
    (_iteration(1, "1e999"), "1", "Invalid solver residual"),
    (_iteration(1, ".01") + "SIMPLE solution converged in 2 iterations", "1", "Inconsistent"),
])
def test_missing_or_inconsistent_numerical_evidence_is_rejected(log, selected, match):
    with pytest.raises(ValueError, match=match):
        solver_iteration_diagnostics(log, CONTROLS, selected)
