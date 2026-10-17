"""Synthetic tests; no OpenFOAM execution or scientific qualification."""
import io
import json
import os
from pathlib import Path

import pytest

import cleanroomx.cfd_convergence_triage as triage

from cleanroomx.cfd_convergence_triage import (
    audit_grid_family_inputs,
    diagnose_grid_family,
    diagnose_grid_flux,
    diagnose_log,
    grid_family_main,
    main,
)


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


def test_foundation_v10_seconds_and_sigfpe_startup_are_valid(tmp_path):
    log = tmp_path / "simpleFoam.log"
    step = _complete_step("1s")
    log.write_text(
        "sigFpe : Enabling floating point exception trapping (FOAM_SIGFPE).\n"
        + step
        + _complete_step("2s")
        + "End\n"
    )
    report = diagnose_log(log)
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["time_sequence_monotonic"] is True
    assert report["last_time"] == "2s"


def test_terminal_residual_control_screen_uses_strict_limit_and_vector_proxy(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_text(
        "SIMPLE: Convergence criteria found\n"
        "        p: tolerance 0.01\n"
        "        U: tolerance 0.1\n"
        + _complete_step("1").replace("Initial residual = 0.01", "Initial residual = 0.1", 1)
        + "End\n"
    )
    report = diagnose_log(log)
    screen = report["terminal_residual_control_screen"]
    assert screen["status"] == "AVAILABLE"
    assert screen["fields"]["p"]["status"] == "NOT_BELOW_TOLERANCE"
    assert screen["fields"]["U"]["status"] == "NOT_BELOW_TOLERANCE"
    assert screen["fields"]["U"]["observed_initial_residual"] == 0.1
    assert report["scientific_validation"] == "BLOCKED"


@pytest.mark.parametrize(
    "criteria",
    [
        "SIMPLE: Convergence criteria found\np: tolerance 1e-5\np: tolerance 1e-4\n",
        "SIMPLE: Convergence criteria found\np: tolerance nan\n",
        "SIMPLE: Convergence criteria found\np: tolerance 1e-5 trailing\n",
    ],
)
def test_malformed_or_duplicate_residual_controls_are_unknown(tmp_path, criteria):
    log = tmp_path / "simpleFoam.log"
    log.write_text(criteria + _complete_step("1") + "End\n")
    screen = diagnose_log(log)["terminal_residual_control_screen"]
    assert screen["status"] == "UNKNOWN"
    assert all(item["status"] == "UNKNOWN" for item in screen["fields"].values())


def test_missing_control_block_and_incomplete_final_step_are_unknown(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_text(_complete_step("1", fields=("p",)) + "End\n")
    screen = diagnose_log(log)["terminal_residual_control_screen"]
    assert screen["status"] == "UNKNOWN"
    assert screen["fields"] == {}

    log.write_text(
        "SIMPLE: Convergence criteria found\np: tolerance 1e-5\n"
        + _complete_step("1", fields=("p",))
        + "End\n"
    )
    report = diagnose_log(log)
    assert report["terminal_residual_control_screen"]["fields"]["p"]["status"] == "UNKNOWN"


def test_floating_point_exception_error_line_blocks(tmp_path):
    log = tmp_path / "simpleFoam.log"
    log.write_text("Time = 1s\nFloating point exception (core dumped)\nEnd\n")
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



def test_recent_window_retains_counts_across_many_steps(tmp_path):
    """Each field still reports all samples while storing just the requested window."""
    log = tmp_path / "many_steps.log"
    log.write_text(
        "".join(_complete_step(str(i)) for i in range(1, 251)) + "End\n"
    )
    result = diagnose_log(log, window=3)
    assert result["status"] == "DIAGNOSTIC_ONLY"
    assert result["scientific_validation"] == "BLOCKED"
    assert result["time_steps"] == 250
    assert result["continuity_samples"] == 250
    assert result["recent_global_continuity"] == [2e-8] * 3
    for field in ("Ux", "Uy", "Uz", "p"):
        info = result["fields"][field]
        assert info["samples"] == 250
        assert info["recent_initial"] == [0.01] * 3
        assert info["recent_final"] == [0.0001] * 3
    trend = result["residual_trend"]
    assert trend["status"] == "DESCRIPTIVE_ONLY"
    assert trend["window_samples_requested"] == 50
    assert trend["fields"]["p"]["window_samples"] == 50
    assert trend["fields"]["p"]["tail_to_initial_median_ratio"] == 1.0


def test_residual_trend_compares_first_and_tail_medians(tmp_path):
    log = tmp_path / "trending.log"
    values = [0.8, 0.4, 0.2, 0.1, 0.05, 0.025]
    records = []
    for index, value in enumerate(values, start=1):
        records.append(
            f"Time = {index}\n"
            f"GAMG: Solving for p, Initial residual = {value}, "
            "Final residual = 1e-8, No Iterations 2\n"
            "time step continuity errors : sum local = 1e-8, "
            "global = 1e-8, cumulative = 1e-8\n"
        )
    log.write_text("".join(records) + "End\n")

    report = diagnose_log(log, fields=("p",), window=2, trend_window=3)
    trend = report["residual_trend"]
    pressure = trend["fields"]["p"]
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert trend["status"] == "DESCRIPTIVE_ONLY"
    assert pressure["status"] == "COMPUTED"
    assert pressure["sample_count"] == 6
    assert pressure["window_samples"] == 3
    assert pressure["initial_window_median"] == 0.4
    assert pressure["tail_window_median"] == 0.05
    assert pressure["tail_to_initial_median_ratio"] == pytest.approx(0.125)
    assert report["scientific_validation"] == "BLOCKED"


@pytest.mark.parametrize(
    ("values", "trend_window", "expected_status"),
    [
        ([0.0], 10, "INSUFFICIENT_SAMPLES"),
        ([0.0, 0.0], 1, "ZERO_INITIAL_MEDIAN"),
    ],
)
def test_residual_trend_does_not_divide_insufficient_or_zero_baselines(
    tmp_path, values, trend_window, expected_status
):
    log = tmp_path / "edge_trend.log"
    records = []
    for index, value in enumerate(values, start=1):
        records.append(
            f"Time = {index}\n"
            f"GAMG: Solving for p, Initial residual = {value}, "
            "Final residual = 0, No Iterations 1\n"
            "time step continuity errors : sum local = 0, "
            "global = 0, cumulative = 0\n"
        )
    log.write_text("".join(records) + "End\n")

    trend = diagnose_log(log, fields=("p",), trend_window=trend_window)["residual_trend"]
    assert trend["fields"]["p"]["status"] == expected_status
    assert trend["fields"]["p"]["tail_to_initial_median_ratio"] is None


def test_residual_trend_short_log_uses_disjoint_reduced_windows(tmp_path):
    log = tmp_path / "short_trend.log"
    values = [0.8, 0.4, 0.2, 0.1, 0.05, 0.025]
    records = []
    for index, value in enumerate(values, start=1):
        records.append(
            f"Time = {index}\n"
            f"GAMG: Solving for p, Initial residual = {value}, "
            "Final residual = 1e-8, No Iterations 2\n"
        )
    log.write_text("".join(records) + "End\n")

    pressure = diagnose_log(log, fields=("p",), trend_window=50)["residual_trend"]["fields"]["p"]
    assert pressure["status"] == "COMPUTED"
    assert pressure["window_samples"] == 3
    assert pressure["initial_window_median"] == 0.4
    assert pressure["tail_window_median"] == 0.05
    assert pressure["tail_to_initial_median_ratio"] == pytest.approx(0.125)


def test_residual_trend_nonfinite_ratio_is_json_safe(tmp_path):
    log = tmp_path / "extreme_trend.log"
    values = [5e-324, 5e-324, 1e308, 1e308]
    records = []
    for index, value in enumerate(values, start=1):
        records.append(
            f"Time = {index}\n"
            f"GAMG: Solving for p, Initial residual = {value}, "
            "Final residual = 0, No Iterations 1\n"
        )
    log.write_text("".join(records) + "End\n")

    report = diagnose_log(log, fields=("p",), trend_window=1)
    pressure = report["residual_trend"]["fields"]["p"]
    assert pressure["status"] == "NONFINITE_RATIO"
    assert pressure["initial_window_median"] == 5e-324
    assert pressure["tail_window_median"] == 1e308
    assert pressure["tail_to_initial_median_ratio"] is None
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("trend_window", [0, 10001, True, 1.0])
def test_residual_trend_window_requires_bounded_exact_integer(tmp_path, trend_window):
    log = tmp_path / "trend_window.log"
    log.write_text(_complete_step("1") + "End\n")
    with pytest.raises(ValueError, match="trend_window"):
        diagnose_log(log, trend_window=trend_window)


def test_grid_family_residual_trend_window_is_reported_and_configurable(
    tmp_path, capsys
):
    root = tmp_path / "family"
    _write_grid_family(root)
    report = diagnose_grid_family(root, trend_window=17)
    trend = report["cases"]["configuration_1/coarse"]["residual_trend"]
    assert trend["window_samples_requested"] == 17
    assert trend["fields"]["p"]["status"] == "INSUFFICIENT_SAMPLES"

    assert grid_family_main([str(root), "--trend-window", "23"]) == 0
    cli_report = json.loads(capsys.readouterr().out)
    cli_trend = cli_report["cases"]["configuration_1/coarse"]["residual_trend"]
    assert cli_trend["window_samples_requested"] == 23


def test_single_log_cli_accepts_trend_window(tmp_path, monkeypatch, capsys):
    log = tmp_path / "solver.log"
    log.write_text(_complete_step("1") + _complete_step("2") + "End\n")
    monkeypatch.setattr(
        "sys.argv", ["cfd_convergence_triage", str(log), "--trend-window", "7"]
    )
    assert main() == 0
    report = json.loads(capsys.readouterr().out)[str(log)]
    assert report["residual_trend"]["window_samples_requested"] == 7


def test_bounded_read_catches_growth_after_stat(tmp_path, monkeypatch):
    """An increasing file must not bypass the 64-MiB bounded-read guard."""
    log = tmp_path / "growing.log"
    log.write_text("Time = 1\nEnd\n")
    monkeypatch.setattr(triage, "_MAX_LOG_BYTES", 256)
    original_open = Path.open

    def growing_stream(self, *args, **kwargs):
        if self == log and args and args[0] == "rb":
            return io.BytesIO(b"x" * 257)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", growing_stream)
    with pytest.raises(ValueError, match="diagnostic limit"):
        diagnose_log(log)



def test_large_step_count_retains_only_latest_stamp(tmp_path):
    log = tmp_path / "long_steps.log"
    log.write_text(
        "".join(_complete_step(str(i)) for i in range(1, 1001)) + "End\n"
    )
    report = diagnose_log(log, window=2)
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["time_steps"] == 1000
    assert report["last_time"] == "1000"
    assert report["time_sequence_monotonic"] is True
    assert report["fields"]["p"]["samples"] == 1000
    assert report["fields"]["p"]["recent_initial"] == [0.01, 0.01]
    assert report["scientific_validation"] == "BLOCKED"


def test_cli_flags_dot_path_alias_as_duplicate_input(tmp_path, monkeypatch, capsys):
    log = tmp_path / "solver.log"
    log.write_text(_complete_step("1") + "End\n")
    # Explicit /./ segment survives in the CLI argument despite Path normalization.
    alias = str(tmp_path) + "/./solver.log"
    monkeypatch.setattr("sys.argv", ["cfd_convergence_triage", str(log), alias])
    assert main() == 3
    reports = json.loads(capsys.readouterr().out)
    assert len(reports) == 2
    assert "DUPLICATE_INPUT_PATH" in reports[str(log)]["problems"]
    assert "DUPLICATE_INPUT_PATH" in reports[alias]["problems"]
    assert reports[str(log)]["duplicate_input_paths"] == [alias]
    assert reports[alias]["duplicate_input_paths"] == [str(log)]
    assert all(r["scientific_validation"] == "BLOCKED" for r in reports.values())


def test_cli_flags_relative_absolute_alias(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    log = tmp_path / "solver.log"
    log.write_text(_complete_step("1") + "End\n")
    monkeypatch.setattr(
        "sys.argv", ["cfd_convergence_triage", "solver.log", str(log)]
    )
    assert main() == 3
    reports = json.loads(capsys.readouterr().out)
    assert "DUPLICATE_INPUT_PATH" in reports["solver.log"]["problems"]
    assert "DUPLICATE_INPUT_PATH" in reports[str(log)]["problems"]
    assert reports["solver.log"]["duplicate_input_paths"] == [str(log)]
    assert reports[str(log)]["duplicate_input_paths"] == ["solver.log"]


def test_cli_distinct_sources_do_not_flag_alias(tmp_path, monkeypatch, capsys):
    first = tmp_path / "first.log"
    second = tmp_path / "second.log"
    first.write_text(_complete_step("1") + "End\n")
    second.write_text(_complete_step("2") + "End\n")
    monkeypatch.setattr(
        "sys.argv", ["cfd_convergence_triage", str(first), str(second)]
    )
    assert main() == 0
    reports = json.loads(capsys.readouterr().out)
    assert all("DUPLICATE_INPUT_PATH" not in r["problems"] for r in reports.values())
    assert all("duplicate_input_paths" not in r for r in reports.values())



def test_diagnostic_rejects_in_place_growth_during_open(tmp_path, monkeypatch):
    log = tmp_path / "changing.log"
    log.write_text(_complete_step("1") + "End\n")
    original_open = Path.open

    def mutating_open(self, *args, **kwargs):
        if self == log and args and args[0] == "rb":
            with original_open(self, "ab") as stream:
                stream.write(b"concurrent appended bytes\n")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", mutating_open)
    with pytest.raises(ValueError, match="log changed during diagnostic read"):
        diagnose_log(log)


def test_diagnostic_rejects_atomic_same_size_path_swap(tmp_path, monkeypatch):
    log = tmp_path / "changing.log"
    replacement = tmp_path / "replacement.log"
    data = _complete_step("1") + "End\n"
    log.write_text(data)
    replacement.write_text(data)
    if not log.stat().st_ino or log.stat().st_ino == replacement.stat().st_ino:
        pytest.skip("stable distinct file identity is unavailable")
    original_open = Path.open

    def swapping_open(self, *args, **kwargs):
        if self == log and args and args[0] == "rb":
            os.replace(replacement, log)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", swapping_open)
    with pytest.raises(ValueError, match="log changed during diagnostic read"):
        diagnose_log(log)


def test_cli_reports_mutating_log_without_crashing(tmp_path, monkeypatch, capsys):
    log = tmp_path / "changing.log"
    log.write_text(_complete_step("1") + "End\n")
    original_open = Path.open

    def mutating_open(self, *args, **kwargs):
        if self == log and args and args[0] == "rb":
            with original_open(self, "ab") as stream:
                stream.write(b"late bytes\n")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", mutating_open)
    monkeypatch.setattr("sys.argv", ["cfd_convergence_triage", str(log)])
    assert main() == 3
    report = json.loads(capsys.readouterr().out)[str(log)]
    assert report["status"] == "INCOMPLETE_OR_INVALID"
    assert report["scientific_validation"] == "BLOCKED"
    assert any("log changed during diagnostic read" in p for p in report["problems"])



def _write_grid_family(root, *, velocity_tolerance="1e-6", pressure_tolerance="1e-5"):
    case_index = 0
    for configuration in (1, 2, 3):
        for level in ("coarse", "medium", "fine"):
            case_index += 1
            case = root / f"configuration_{configuration}" / level
            case.mkdir(parents=True)
            controls = (
                "SIMPLE: Convergence criteria found\n"
                f"    U: tolerance {velocity_tolerance}\n"
                f"    p: tolerance {pressure_tolerance}\n"
            )
            (case / "simpleFoam.log").write_text(
                controls + _complete_step(str(case_index)) + "End\n"
            )
            dictionaries = {
                "0/U": f"// configuration {configuration}\ninletVelocity {configuration};\n",
                "0/p": "internalField uniform 0;\n",
                "constant/physicalProperties": "nu 1e-5;\n",
                "constant/momentumTransport": "simulationType laminar;\n",
                "system/controlDict": "application simpleFoam;\n",
                "system/fvSchemes": "div(phi,U) Gauss upwind;\n",
                "system/fvSolution": "solver p solver GAMG;\n",
            }
            for relative, content in dictionaries.items():
                path = case / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            mesh = case / "system" / "blockMeshDict"
            mesh.write_text(f"// {configuration} {level}\nblocks (1 1 1);\n")


def _write_grid_flux_outputs(root, *, outlet_values=(0.21, -0.01)):
    case_index = 0
    for configuration in (1, 2, 3):
        for level in ("coarse", "medium", "fine"):
            case_index += 1
            case = root / f"configuration_{configuration}" / level
            mesh = case / "constant/polyMesh/boundary"
            mesh.parent.mkdir(parents=True)
            mesh.write_text(
                "3\n(\n"
                "inlet\n{\n type patch;\n nFaces 2;\n startFace 0;\n}\n"
                "outlet\n{\n type patch;\n nFaces 2;\n startFace 2;\n}\n"
                "walls\n{\n type wall;\n nFaces 1;\n startFace 4;\n}\n"
                ")\n"
            )
            phi = case / str(case_index) / "phi"
            phi.parent.mkdir()
            phi.write_text(
                "dimensions [0 3 -1 0 0 0 0];\n"
                "boundaryField\n{\n"
                "    inlet\n    {\n        type calculated;\n        value nonuniform List<scalar> 2(-0.1 -0.1);\n    }\n"
                f"    outlet\n    {{\n        type calculated;\n        value nonuniform List<scalar> 2({outlet_values[0]} {outlet_values[1]});\n    }}\n"
                "    walls\n    {\n        type calculated;\n        value uniform 0;\n    }\n"
                "}\n"
            )


def test_grid_family_input_screen_hashes_conditions_and_mesh_separately(tmp_path):
    root = tmp_path / "family"
    _write_grid_family(root)
    report = diagnose_grid_family(root)
    screen = report["solver_input_fingerprint_screen"]
    assert screen["status"] == "BYTE_IDENTICAL_ACROSS_GRID_LEVELS"
    assert screen["mesh_input_hashed_separately"] == "system/blockMeshDict"
    assert len(screen["condition_inputs_compared"]) == 7
    for configuration in ("configuration_1", "configuration_2", "configuration_3"):
        config = screen["configurations"][configuration]
        assert config["status"] == "BYTE_IDENTICAL_ACROSS_GRID_LEVELS"
        assert config["condition_fingerprint_sha256"]
        assert len({level["mesh_dictionary_sha256"] for level in config["levels"].values()}) == 3
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["scientific_validation"] == "BLOCKED"


def test_grid_family_condition_mismatch_does_not_change_log_status(tmp_path, capsys):
    root = tmp_path / "family"
    _write_grid_family(root)
    changed = root / "configuration_2" / "fine" / "0" / "U"
    changed.write_text("// changed only on fine grid\ninletVelocity 99;\n")
    report = diagnose_grid_family(root)
    screen = report["solver_input_fingerprint_screen"]
    assert screen["status"] == "DIFFERENT_ACROSS_GRID_LEVELS"
    assert screen["configurations"]["configuration_2"]["differing_condition_files"] == ["0/U"]
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["scientific_validation"] == "BLOCKED"
    assert grid_family_main([str(root)]) == 0
    cli_report = json.loads(capsys.readouterr().out)
    assert cli_report["status"] == "DIAGNOSTIC_ONLY"
    assert cli_report["solver_input_fingerprint_screen"]["status"] == "DIFFERENT_ACROSS_GRID_LEVELS"


def test_grid_family_missing_condition_input_is_separate_from_log_status(tmp_path):
    root = tmp_path / "family"
    _write_grid_family(root)
    (root / "configuration_1" / "fine" / "system" / "fvSolution").unlink()
    report = diagnose_grid_family(root)
    assert report["solver_input_fingerprint_screen"]["status"] == "INCOMPLETE_OR_UNREADABLE"
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["scientific_validation"] == "BLOCKED"


def test_grid_family_reports_nine_cases_and_separates_residual_screen(tmp_path):
    root = tmp_path / "family"
    _write_grid_family(root)
    report = diagnose_grid_family(root)
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["scientific_validation"] == "BLOCKED"
    assert report["case_count_expected"] == report["case_count_present"] == 9
    assert report["configured_residual_screen"]["status"] == "NOT_BELOW_TOLERANCE"
    assert len(report["cases"]) == 9
    assert all(case["status"] == "DIAGNOSTIC_ONLY" for case in report["cases"].values())


def test_grid_family_measures_final_phi_flux_without_inventing_acceptance(tmp_path):
    root = tmp_path / "family"
    _write_grid_family(root)
    _write_grid_flux_outputs(root)
    report = diagnose_grid_family(root)
    flux = report["cases"]["configuration_1/coarse"]["solver_flux_screen"]
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["configured_residual_screen"]["status"] == "NOT_BELOW_TOLERANCE"
    assert report["solver_flux_balance_screen"]["status"] == "MEASURED_DIAGNOSTIC_ONLY"
    assert report["solver_flux_balance_screen"]["case_count_measured"] == 9
    assert report["solver_flux_balance_screen"]["acceptance_criterion"] == "NOT_SET"
    assert flux["status"] == "MEASURED_DIAGNOSTIC_ONLY"
    assert flux["inlet"]["net_inward_m3_s"] == pytest.approx(0.2)
    assert flux["outlet"]["net_outward_m3_s"] == pytest.approx(0.2)
    assert flux["outlet"]["gross_outward_m3_s"] == pytest.approx(0.21)
    assert flux["outlet"]["reverse_inward_m3_s"] == pytest.approx(0.01)
    assert flux["relative_flux_imbalance_percent"] == pytest.approx(0)
    assert flux["flow_balance_assessment"] == "NO_PROJECT_ACCEPTANCE_CRITERION"
    assert flux["scientific_validation"] == "BLOCKED"


def test_two_room_flux_diagnostic_includes_partition_faces_as_wall_boundary(tmp_path):
    root = tmp_path / "family"
    case = root / "two_room"
    boundary = case / "constant" / "polyMesh" / "boundary"
    phi = case / "1" / "phi"
    boundary.parent.mkdir(parents=True)
    phi.parent.mkdir(parents=True)
    boundary.write_text(
        "4\n(\n"
        "inlet\n{\n type patch;\n nFaces 1;\n startFace 0;\n}\n"
        "outlet\n{\n type patch;\n nFaces 1;\n startFace 1;\n}\n"
        "walls\n{\n type wall;\n nFaces 1;\n startFace 2;\n}\n"
        "partition\n{\n type wall;\n nFaces 1;\n startFace 3;\n}\n)\n"
    )
    phi.write_text(
        "dimensions [0 3 -1 0 0 0 0];\n"
        "boundaryField\n{\n"
        "inlet\n{\n type calculated;\n value uniform -0.1;\n}\n"
        "outlet\n{\n type calculated;\n value uniform 0.098;\n}\n"
        "walls\n{\n type calculated;\n value uniform 0;\n}\n"
        "partition\n{\n type calculated;\n value uniform 0.002;\n}\n"
        "}\n"
    )

    report = diagnose_grid_flux(case, "1", family_root=root)

    assert report["status"] == "MEASURED_DIAGNOSTIC_ONLY"
    assert report["inlet"]["net_inward_m3_s"] == pytest.approx(0.1)
    assert report["outlet"]["net_outward_m3_s"] == pytest.approx(0.098)
    assert report["partition_net_outward_m3_s"] == pytest.approx(0.002)
    assert report["walls_net_outward_m3_s"] == pytest.approx(0.002)
    assert report["relative_flux_imbalance_percent"] == pytest.approx(0.0)
    assert report["flow_balance_assessment"] == "NO_PROJECT_ACCEPTANCE_CRITERION"


def test_missing_final_phi_is_separate_from_complete_solver_log_status(tmp_path):
    root = tmp_path / "family"
    _write_grid_family(root)
    _write_grid_flux_outputs(root)
    (root / "configuration_1" / "coarse" / "1" / "phi").unlink()
    report = diagnose_grid_family(root)
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["solver_flux_balance_screen"]["status"] == "PARTIAL_OR_UNAVAILABLE"
    assert report["cases"]["configuration_1/coarse"]["solver_flux_screen"]["status"] == "UNAVAILABLE"
    assert report["scientific_validation"] == "BLOCKED"


def test_malformed_phi_face_count_fails_closed_without_changing_log_status(tmp_path):
    root = tmp_path / "family"
    _write_grid_family(root)
    _write_grid_flux_outputs(root)
    phi = root / "configuration_1" / "coarse" / "1" / "phi"
    phi.write_text(phi.read_text().replace("2(-0.1 -0.1)", "2(-0.1 -0.1 -0.1)"))
    report = diagnose_grid_family(root)
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["solver_flux_balance_screen"]["status"] == "PARTIAL_OR_UNAVAILABLE"
    screen = report["cases"]["configuration_1/coarse"]["solver_flux_screen"]
    assert screen["status"] == "UNAVAILABLE"
    assert any("face-value count" in problem for problem in screen["problems"])


def test_grid_family_small_residuals_do_not_unlock_scientific_validation(tmp_path):
    root = tmp_path / "family"
    _write_grid_family(root, velocity_tolerance="1.0", pressure_tolerance="1.0")
    report = diagnose_grid_family(root)
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["configured_residual_screen"]["status"] == "BELOW_TOLERANCE"
    assert report["scientific_validation"] == "BLOCKED"


def test_grid_family_missing_case_fails_closed(tmp_path):
    root = tmp_path / "family"
    _write_grid_family(root)
    (root / "configuration_2" / "medium" / "simpleFoam.log").unlink()
    report = diagnose_grid_family(root)
    assert report["status"] == "INCOMPLETE_OR_INVALID"
    assert report["case_count_expected"] == 9
    assert report["case_count_present"] == 8
    assert "MISSING_OR_UNREADABLE_CASE_LOGS" in report["problems"]
    assert report["scientific_validation"] == "BLOCKED"


def test_grid_family_identical_logs_fail_closed(tmp_path):
    root = tmp_path / "family"
    _write_grid_family(root)
    source = root / "configuration_1" / "coarse" / "simpleFoam.log"
    duplicate = root / "configuration_3" / "fine" / "simpleFoam.log"
    duplicate.write_bytes(source.read_bytes())
    report = diagnose_grid_family(root)
    assert report["status"] == "INCOMPLETE_OR_INVALID"
    assert report["duplicate_log_case_groups"]
    assert "DUPLICATE_LOG_BYTES" in report["cases"]["configuration_1/coarse"]["problems"]


def test_grid_family_unexpected_log_fails_closed(tmp_path):
    root = tmp_path / "family"
    _write_grid_family(root)
    extra = root / "unexpected" / "simpleFoam.log"
    extra.parent.mkdir()
    extra.write_text(_complete_step("20") + "End\n")
    report = diagnose_grid_family(root)
    assert report["status"] == "INCOMPLETE_OR_INVALID"
    assert report["unexpected_simpleFoam_logs"] == ["unexpected/simpleFoam.log"]


def test_grid_family_rejects_symlinked_root(tmp_path):
    root = tmp_path / "family"
    _write_grid_family(root)
    alias = tmp_path / "family-link"
    alias.symlink_to(root, target_is_directory=True)
    report = diagnose_grid_family(alias)
    assert report["status"] == "INCOMPLETE_OR_INVALID"
    assert "GRID_FAMILY_DIRECTORY_MISSING_OR_SYMLINKED" in report["problems"]


def test_grid_family_cli_exit_code_means_complete_diagnostic_only(tmp_path, capsys):
    root = tmp_path / "family"
    _write_grid_family(root)
    assert grid_family_main([str(root)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "DIAGNOSTIC_ONLY"
    assert report["scientific_validation"] == "BLOCKED"

    (root / "configuration_1" / "fine" / "simpleFoam.log").unlink()
    assert grid_family_main([str(root)]) == 3
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "INCOMPLETE_OR_INVALID"
