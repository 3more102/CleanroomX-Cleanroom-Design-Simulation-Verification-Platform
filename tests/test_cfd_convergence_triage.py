"""Synthetic tests; no OpenFOAM execution or scientific qualification."""
import pytest

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


@pytest.mark.parametrize("bad_token", ["NaN", "-inf", "+INF", "infinity"])
def test_nonfinite_tokens_fail_closed(tmp_path, bad_token):
    log = tmp_path / "simpleFoam.log"
    log.write_text(f"Time = 1\nsolver diagnostic: {bad_token}\nEnd\n")
    report = diagnose_log(log)
    assert "FATAL_OR_NONFINITE_TOKEN" in report["problems"]
    assert report["status"] == "INCOMPLETE_OR_INVALID"
    assert report["scientific_validation"] == "BLOCKED"


def test_end_in_middle_is_not_terminal(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_text("Time = 1\nEnd\nunexpected solver output after end\n")
    report = diagnose_log(log)
    assert report["terminal_end"] is False
    assert "MISSING_TERMINAL_END" in report["problems"]


def test_trailing_blank_lines_after_end_are_valid_terminator(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_text("Time = 1\nEnd\n\n   \n")
    assert diagnose_log(log)["terminal_end"] is True


def test_invalid_utf8_log_is_rejected_not_silently_replaced(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_bytes(b"Time = 1\nEnd\n\xff\n")
    with pytest.raises(UnicodeDecodeError):
        diagnose_log(log)
