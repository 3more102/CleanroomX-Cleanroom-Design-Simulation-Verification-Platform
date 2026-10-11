"""Synthetic tests; no OpenFOAM execution or scientific qualification."""
from cleanroomx.cfd_convergence_triage import diagnose_log


def test_complete_log_is_diagnostic_only(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_text(
        "Time = 1\n"
        "smoothSolver:  Solving for Ux, Initial residual = 0.01, Final residual = 1e-06, No Iterations 3\n"
        "smoothSolver:  Solving for Uy, Initial residual = 0.02, Final residual = 2e-06, No Iterations 3\n"
        "smoothSolver:  Solving for Uz, Initial residual = 0.03, Final residual = 3e-06, No Iterations 3\n"
        "GAMG:  Solving for p, Initial residual = 0.04, Final residual = 4e-06, No Iterations 3\n"
        "time step continuity errors : sum local = 1e-07, global = 2e-08, cumulative = 2e-08\n"
        "End\n"
    )
    result = diagnose_log(log)
    assert result["status"] == "DIAGNOSTIC_ONLY"
    assert result["scientific_validation"] == "BLOCKED"
    assert result["fields"]["p"]["last_initial"] == 0.04
    assert result["recent_global_continuity"] == [2e-08]


def test_truncated_log_fails_closed(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_text("Time = 1\nSolving for p, Initial residual = 0.1, Final residual = 0.01, No Iterations 2\n")
    result = diagnose_log(log)
    assert result["status"] == "INCOMPLETE_OR_INVALID"
    assert "MISSING_TERMINAL_END" in result["problems"]
    assert "MISSING_REQUIRED_FIELD" in result["problems"]


def test_fatal_marker_blocks(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_text("Time = 1\nFOAM FATAL ERROR\nEnd\n")
    assert "FATAL_OR_NONFINITE_TOKEN" in diagnose_log(log)["problems"]
