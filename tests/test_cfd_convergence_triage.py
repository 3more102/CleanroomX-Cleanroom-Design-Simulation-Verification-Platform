"""Synthetic tests; no OpenFOAM execution or scientific qualification."""
import json

import pytest

from cleanroomx.cfd_convergence_triage import diagnose_log, main


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


def _complete_step(stamp, *, fields=("Ux", "Uy", "Uz", "p"), continuity=True):
    """Synthetic single SIMPLE step; not evidence of an OpenFOAM run."""
    lines = [f"Time = {stamp}"]
    for field in fields:
        lines.append(
            f"solver: Solving for {field}, Initial residual = 0.01, "
            f"Final residual = 0.0001, No Iterations 2"
        )
    if continuity:
        lines.append(
            "time step continuity errors : sum local = 1e-7, "
            "global = 2e-8, cumulative = 2e-8"
        )
    return "\n".join(lines) + "\n"


def test_two_complete_monotonic_time_steps_remain_diagnostic_only(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_text(_complete_step("1e-3") + _complete_step("2e-3") + "End\n")
    report = diagnose_log(log)
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["scientific_validation"] == "BLOCKED"
    assert report["time_steps"] == 2
    assert report["time_sequence_monotonic"] is True
    assert report["last_time"] == "2e-3"
    assert report["last_step_missing_fields"] == []
    assert report["last_step_continuity_samples"] == 1


def test_historical_solver_data_cannot_satisfy_missing_last_fields(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_text(
        _complete_step("1")
        + _complete_step("2", fields=("p",))
        + "End\n"
    )
    report = diagnose_log(log)
    assert report["fields"]["Ux"]["missing"] is False
    assert report["last_step_missing_fields"] == ["Ux", "Uy", "Uz"]
    assert "INCOMPLETE_FINAL_TIME_STEP" in report["problems"]
    assert report["status"] == "INCOMPLETE_OR_INVALID"


def test_historical_continuity_cannot_satisfy_missing_last_continuity(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_text(_complete_step("1") + _complete_step("2", continuity=False) + "End\n")
    report = diagnose_log(log)
    assert report["continuity_samples"] == 1
    assert report["last_step_continuity_samples"] == 0
    assert "INCOMPLETE_FINAL_TIME_STEP" in report["problems"]


@pytest.mark.parametrize("second", ["1", "0.5", "not_a_number", "nan", "inf"])
def test_replayed_reversed_or_invalid_timestamps_are_rejected(tmp_path, second):
    log = tmp_path / "simpleFoam.log"
    log.write_text(_complete_step("1") + _complete_step(second) + "End\n")
    report = diagnose_log(log)
    assert "INVALID_OR_NONMONOTONIC_TIME_STEPS" in report["problems"]
    assert report["time_sequence_monotonic"] is False
    assert report["scientific_validation"] == "BLOCKED"


def test_negative_linear_solver_residual_is_not_accepted(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_text(
        _complete_step("1").replace("Initial residual = 0.01", "Initial residual = -0.01", 1)
        + "End\n"
    )
    report = diagnose_log(log)
    assert "INVALID_RESIDUAL_VALUE" in report["problems"]
    assert report["status"] == "INCOMPLETE_OR_INVALID"


def test_orphan_solver_record_before_first_time_is_rejected(tmp_path):
    log = tmp_path / "simpleFoam.log"
    solver = (
        "solver: Solving for Ux, Initial residual = 0.1, "
        "Final residual = 0.01, No Iterations 2\n"
    )
    log.write_text(solver + _complete_step("1") + "End\n")
    report = diagnose_log(log)
    assert "ORPHAN_SOLVER_RECORDS" in report["problems"]


def test_multiple_terminal_markers_are_not_accepted(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_text(_complete_step("1") + "End\nEnd\n")
    report = diagnose_log(log)
    assert report["terminal_end"] is True
    assert "MULTIPLE_END_MARKERS" in report["problems"]


@pytest.mark.parametrize("fields", [(), ("Ux", "Ux"), ("",), ("bad field",)])
def test_invalid_field_selection_is_rejected(tmp_path, fields):
    log = tmp_path / "simpleFoam.log"
    log.write_text(_complete_step("1") + "End\n")
    with pytest.raises(ValueError, match="fields"):
        diagnose_log(log, fields=fields)


def test_cli_valid_evidence_remains_blocked(tmp_path, monkeypatch, capsys):
    log = tmp_path / "solver.log"
    log.write_text(_complete_step("1") + "End\n")
    monkeypatch.setattr("sys.argv", ["cfd_convergence_triage", str(log)])
    assert main() == 0
    report = json.loads(capsys.readouterr().out)[str(log)]
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["scientific_validation"] == "BLOCKED"
    assert report["last_step_missing_fields"] == []


def test_cli_incomplete_last_step_fails_closed(tmp_path, monkeypatch, capsys):
    log = tmp_path / "solver.log"
    log.write_text(_complete_step("1") + _complete_step("2", fields=("p",)) + "End\n")
    monkeypatch.setattr("sys.argv", ["cfd_convergence_triage", str(log)])
    assert main() == 3
    report = json.loads(capsys.readouterr().out)[str(log)]
    assert "INCOMPLETE_FINAL_TIME_STEP" in report["problems"]
    assert report["scientific_validation"] == "BLOCKED"



def test_incomplete_middle_step_cannot_be_hidden_by_a_complete_final_step(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_text(
        _complete_step("1")
        + _complete_step("2", fields=("p",))
        + _complete_step("3")
        + "End\n"
    )
    report = diagnose_log(log)
    assert report["incomplete_prior_time_steps"] == 1
    assert report["last_step_missing_fields"] == []
    assert "INCOMPLETE_PRIOR_TIME_STEP" in report["problems"]
    assert report["status"] == "INCOMPLETE_OR_INVALID"
    assert report["scientific_validation"] == "BLOCKED"


def test_missing_middle_continuity_cannot_be_hidden_by_later_steps(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_text(
        _complete_step("1")
        + _complete_step("2", continuity=False)
        + _complete_step("3")
        + "End\n"
    )
    report = diagnose_log(log)
    assert report["incomplete_prior_time_steps"] == 1
    assert report["last_step_continuity_samples"] == 1
    assert "INCOMPLETE_PRIOR_TIME_STEP" in report["problems"]


@pytest.mark.parametrize("bad_value", ["not_a_number", "1e309"])
def test_malformed_continuity_not_masked_by_earlier_valid_record(tmp_path, bad_value):
    log = tmp_path / "simpleFoam.log"
    bad = (
        f"time step continuity errors : sum local = {bad_value}, "
        "global = 2e-8, cumulative = 2e-8\n"
    )
    log.write_text(_complete_step("1") + bad + "End\n")
    report = diagnose_log(log)
    assert report["continuity_samples"] == 1
    assert "MALFORMED_CONTINUITY_RECORD" in report["problems"]
    assert report["status"] == "INCOMPLETE_OR_INVALID"


@pytest.mark.parametrize("bad_value", ["not_a_number", "1e309"])
def test_malformed_solver_record_not_masked_by_valid_residuals(tmp_path, bad_value):
    log = tmp_path / "simpleFoam.log"
    bad = (
        f"solver: Solving for p, Initial residual = {bad_value}, "
        "Final residual = 1e-5, No Iterations 2\n"
    )
    log.write_text(_complete_step("1") + bad + "End\n")
    report = diagnose_log(log)
    assert report["status"] == "INCOMPLETE_OR_INVALID"
    if bad_value == "not_a_number":
        assert "MALFORMED_SOLVER_RECORD" in report["problems"]
    else:
        assert "INVALID_RESIDUAL_VALUE" in report["problems"]


def test_rejects_log_under_symlinked_parent_directory(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    (actual / "simpleFoam.log").write_text(_complete_step("1") + "End\n")
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(actual, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks are unavailable on this platform")
    with pytest.raises(ValueError, match="symlinked"):
        diagnose_log(alias / "simpleFoam.log")


@pytest.mark.parametrize("invalid_marker", [
    "Time =",
    "Time = 2 trailing",
    "Time = 2 3",
])
def test_malformed_intermediate_time_marker_cannot_be_skipped(tmp_path, invalid_marker):
    log = tmp_path / "simpleFoam.log"
    log.write_text(
        _complete_step("1")
        + invalid_marker + "\n"
        + _complete_step("3")
        + "End\n"
    )
    report = diagnose_log(log)
    assert "MALFORMED_TIME_MARKER" in report["problems"]
    assert report["time_sequence_monotonic"] is False
    assert report["status"] == "INCOMPLETE_OR_INVALID"
    assert report["scientific_validation"] == "BLOCKED"


@pytest.mark.parametrize("suffix", [
    " injected_tail",
    " Solving for p, Initial residual = 0.1, Final residual = 0.01, No Iterations 1",
])
def test_solver_record_trailing_data_cannot_pass_as_complete(tmp_path, suffix):
    log = tmp_path / "simpleFoam.log"
    source = _complete_step("1")
    log.write_text(source.replace("No Iterations 2\n", "No Iterations 2" + suffix + "\n", 1) + "End\n")
    report = diagnose_log(log)
    assert "MALFORMED_SOLVER_RECORD" in report["problems"]
    assert report["status"] == "INCOMPLETE_OR_INVALID"


@pytest.mark.parametrize("suffix", [
    " forged_tail",
    " time step continuity errors : sum local = 1, global = 1, cumulative = 1",
])
def test_continuity_record_trailing_data_cannot_pass_as_complete(tmp_path, suffix):
    log = tmp_path / "simpleFoam.log"
    source = _complete_step("1")
    log.write_text(source.replace("cumulative = 2e-8\n", "cumulative = 2e-8" + suffix + "\n", 1) + "End\n")
    report = diagnose_log(log)
    assert "MALFORMED_CONTINUITY_RECORD" in report["problems"]
    assert report["status"] == "INCOMPLETE_OR_INVALID"


def test_excessively_long_iteration_integer_fails_closed(tmp_path):
    log = tmp_path / "simpleFoam.log"
    source = _complete_step("1")
    log.write_text(source.replace("No Iterations 2\n", "No Iterations " + ("9" * 5000) + "\n", 1) + "End\n")
    report = diagnose_log(log)
    assert report["status"] == "INCOMPLETE_OR_INVALID"
    assert "MALFORMED_SOLVER_RECORD" in report["problems"]


def test_record_trailing_whitespace_is_accepted(tmp_path):
    log = tmp_path / "simpleFoam.log"
    source = _complete_step("1")
    source = source.replace("No Iterations 2\n", "No Iterations 2   \n")
    source = source.replace("cumulative = 2e-8\n", "cumulative = 2e-8  \n")
    log.write_text(source + "End\n")
    report = diagnose_log(log)
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["problems"] == []
    assert report["scientific_validation"] == "BLOCKED"


def test_cli_rejects_identical_log_bytes_from_distinct_paths(tmp_path, monkeypatch, capsys):
    first = tmp_path / "case_a.log"
    second = tmp_path / "case_b.log"
    for path in (first, second):
        path.write_text(_complete_step("1") + "End\n")
    monkeypatch.setattr("sys.argv", ["cfd_convergence_triage", str(first), str(second)])
    assert main() == 3
    reports = json.loads(capsys.readouterr().out)
    assert reports[str(first)]["source_sha256"] == reports[str(second)]["source_sha256"]
    for path, other in ((first, second), (second, first)):
        result = reports[str(path)]
        assert result["status"] == "INCOMPLETE_OR_INVALID"
        assert result["scientific_validation"] == "BLOCKED"
        assert "DUPLICATE_LOG_BYTES" in result["problems"]
        assert result["duplicate_log_paths"] == [str(other)]


def test_cli_allows_distinct_complete_log_bytes(tmp_path, monkeypatch, capsys):
    first = tmp_path / "case_a.log"
    second = tmp_path / "case_b.log"
    first.write_text(_complete_step("1") + "End\n")
    second.write_text(_complete_step("2") + "End\n")
    monkeypatch.setattr("sys.argv", ["cfd_convergence_triage", str(first), str(second)])
    assert main() == 0
    reports = json.loads(capsys.readouterr().out)
    assert set(reports) == {str(first), str(second)}
    assert all(x["status"] == "DIAGNOSTIC_ONLY" for x in reports.values())
    assert all(x["scientific_validation"] == "BLOCKED" for x in reports.values())
    assert all("DUPLICATE_LOG_BYTES" not in x["problems"] for x in reports.values())


def test_cli_rejects_duplicate_input_path(tmp_path, monkeypatch, capsys):
    log = tmp_path / "solver.log"
    log.write_text(_complete_step("1") + "End\n")
    monkeypatch.setattr("sys.argv", ["cfd_convergence_triage", str(log), str(log)])
    assert main() == 3
    result = json.loads(capsys.readouterr().out)[str(log)]
    assert result["status"] == "INCOMPLETE_OR_INVALID"
    assert "DUPLICATE_INPUT_PATH" in result["problems"]
    assert result["scientific_validation"] == "BLOCKED"
    assert "DUPLICATE_LOG_BYTES" not in result["problems"]


def test_cli_replay_is_reported_even_with_one_other_invalid_log(tmp_path, monkeypatch, capsys):
    first = tmp_path / "case_a.log"
    second = tmp_path / "case_b.log"
    broken = tmp_path / "broken.log"
    first.write_text(_complete_step("1") + "End\n")
    second.write_bytes(first.read_bytes())
    broken.write_text("Time = 1\nEnd\n")
    monkeypatch.setattr(
        "sys.argv",
        ["cfd_convergence_triage", str(first), str(broken), str(second)],
    )
    assert main() == 3
    reports = json.loads(capsys.readouterr().out)
    assert "DUPLICATE_LOG_BYTES" in reports[str(first)]["problems"]
    assert "DUPLICATE_LOG_BYTES" in reports[str(second)]["problems"]
    assert reports[str(broken)]["status"] == "INCOMPLETE_OR_INVALID"
    assert "DUPLICATE_LOG_BYTES" not in reports[str(broken)]["problems"]
