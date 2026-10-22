"""Incremental parsing contracts. Synthetic logs are not solver execution evidence."""
from __future__ import annotations

import gzip
import os
from pathlib import Path

import pytest

from cleanroomx.cfd_live_monitor import LiveLogFollower, LiveSolverMonitor, PREVIEW_SCHEMA
from cleanroomx.cfd_multizone_results import solver_iteration_diagnostics
from cleanroomx.cfd_residual_plot import residual_plot_data


def _iteration(number):
    return (f"Time = {number}\r\n" + "\n".join(
        f"smoothSolver: Solving for {field}, Initial residual = {initial}, "
        "Final residual = 1e-12, No Iterations 2"
        for field, initial in (("Ux", 0), ("Uy", .02), ("Uz", .03), ("p", .1), ("p", .05)))
        + "\ntime step continuity errors : sum local = 1e-4, global = -2e-5, cumulative = -1e-5\n").encode()


def test_arbitrary_byte_boundaries_preserve_repeated_solves_and_signed_continuity():
    data = _iteration(1) + _iteration(8)
    monitor = LiveSolverMonitor()
    for byte in data:
        monitor.feed(bytes([byte]))
    canonical, _ = solver_iteration_diagnostics(data.decode(), "", "8")
    assert list(monitor.history) == canonical
    assert monitor.total_samples == 10
    assert monitor.pending == b""
    assert monitor.continuity == {"iteration": 8., "sum_local": 1e-4,
                                  "global": -2e-5, "cumulative": -1e-5}
    snapshot = monitor.plot_snapshot()
    assert snapshot["schema"] == PREVIEW_SCHEMA
    assert snapshot["time_name"] is None
    assert "solver_reported_convergence" not in snapshot
    model = residual_plot_data(snapshot)
    assert model["selected_iteration"] is None
    assert model["limits"] == {}
    assert [row["solve_index"] for row in model["samples"] if row["field"] == "p"] == [1, 2, 1, 2]
    assert not monitor.feed(b"")


def test_incomplete_lines_do_not_supply_residuals_and_snapshots_are_copies():
    monitor = LiveSolverMonitor()
    monitor.feed(b"Time = 2\nSolving for p, Initial residual = 0.1, Final residual = 0")
    assert monitor.total_samples == 0
    assert monitor.plot_snapshot() is None
    monitor.feed(b"\n")
    snapshot = monitor.plot_snapshot()
    assert snapshot["residual_history"][0]["final"] == 0
    snapshot["residual_history"][0]["initial"] = 999
    assert monitor.latest["p"]["initial"] == .1
    monitor.feed(b"SIMPLE solution converged in 2 iterations\nEnd\n")
    assert "solver_reported_convergence" not in monitor.plot_snapshot()


@pytest.mark.parametrize("line", [
    b"Time = nan\n", b"Time = -1\n", b"Time = 1 extra\n",
    b"Time = 1\nSolving for p, Initial residual = nan, Final residual = 0\n",
    b"Time = 1\nSolving for p, Initial residual = -1, Final residual = 0\n",
    b"Time = 1\nSolving for p, Initial residual = 1, Final residual = inf\n",
    b"Time = 1\nSolving for p, Initial residual = 1\n",
    b"Solving for p, Initial residual = 1, Final residual = 0\n",
    b"Time = 2\nTime = 1\n",
    b"Time = 1\ntime step continuity errors : sum local = nan, global = 0, cumulative = 0\n",
])
def test_invalid_or_restarted_records_stop_the_preview_without_a_verdict(line):
    monitor = LiveSolverMonitor()
    monitor.feed(line)
    assert monitor.error
    assert monitor.plot_snapshot() is None
    assert not monitor.feed(_iteration(10))


def test_bounds_discard_whole_iterations_and_keep_original_log_indices():
    monitor = LiveSolverMonitor(max_samples=8)
    for i in range(1, 41):
        monitor.feed(_iteration(i))
        assert len(monitor.history) <= 8
    assert monitor.total_samples == 200
    assert monitor.discarded_samples == 195
    model = residual_plot_data(monitor.plot_snapshot())
    assert {row["iteration"] for row in model["samples"]} == {40}
    assert [row["log_index"] for row in model["samples"]] == list(range(196, 201))
    assert [row["solve_index"] for row in model["samples"] if row["field"] == "p"] == [1, 2]
    single = LiveSolverMonitor(max_samples=4)
    single.feed(_iteration(1))
    assert "single iteration" in single.error
    for data in (b"x" * 129, b"x" * 129 + b"\n"):
        bounded = LiveSolverMonitor(max_line_bytes=128)
        bounded.feed(data)
        assert "line limit" in bounded.error
        assert bounded.pending == b""
    with pytest.raises(ValueError, match="128 KiB"):
        monitor.feed(b"x" * (128 * 1024 + 1))
    with pytest.raises(ValueError, match="binary chunks"):
        monitor.feed("text")


def test_follower_reads_each_append_once_and_resets_after_truncation_or_replacement(tmp_path):
    path = tmp_path / "simpleFoam.log"
    follower = LiveLogFollower(path)
    assert not follower.poll()
    path.write_bytes(_iteration(1))
    assert follower.poll()
    assert not follower.poll()
    with path.open("ab") as stream:
        stream.write(_iteration(2))
    assert follower.poll()
    assert follower.monitor.total_samples == 10
    path.write_bytes(_iteration(3))
    assert follower.poll()
    assert follower.monitor.total_samples == 5
    assert "truncated" in follower.notice
    replacement = tmp_path / "replacement.log"
    replacement.write_bytes(_iteration(4))
    replacement.replace(path)
    assert follower.poll()
    assert follower.monitor.iteration == 4
    assert follower.monitor.total_samples == 5
    path.unlink()
    assert follower.poll()
    assert follower.monitor.plot_snapshot() is None
    assert "removed" in follower.notice


def test_stale_logs_and_symlinks_never_enter_a_new_run_preview(tmp_path):
    path = tmp_path / "simpleFoam.log"
    path.write_bytes(_iteration(1))
    stale = LiveLogFollower(path, allow_existing=False)
    assert stale.poll()
    assert "fresh run" in stale.error
    assert stale.monitor.total_samples == 0
    link = tmp_path / "link.log"
    try:
        link.symlink_to(path)
    except OSError as exc:
        pytest.skip(f"Symlink capability unavailable: {exc}")
    follower = LiveLogFollower(link)
    assert follower.poll()
    assert "Symbolic" in follower.error


def test_nonregular_logs_cannot_block_the_preview_reader(tmp_path):
    directory = tmp_path / "directory.log"
    directory.mkdir()
    follower = LiveLogFollower(directory)
    assert follower.poll()
    assert "regular" in follower.error
    if hasattr(os, "mkfifo"):
        fifo = tmp_path / "fifo.log"
        os.mkfifo(fifo)
        follower = LiveLogFollower(fifo)
        assert follower.poll()
        assert "regular" in follower.error


def test_large_log_reads_are_bounded_and_eventually_complete(tmp_path):
    path = tmp_path / "simpleFoam.log"
    path.write_bytes(b"".join(_iteration(i) for i in range(1, 501)))
    follower = LiveLogFollower(path)
    previous = 0
    for _ in range(20):
        changed = follower.poll()
        assert 0 <= follower.offset - previous <= 128 * 1024
        previous = follower.offset
        if not changed:
            break
    assert follower.offset == path.stat().st_size
    assert follower.monitor.total_samples == 2500
    assert follower.monitor.iteration == 500


def test_archived_actual_openfoam_log_agrees_exactly_with_canonical_parser():
    # Historical executed data; replaying these bytes is not new execution.
    archive = Path(__file__).resolve().parents[1] / "reports/engineering-session-20261021/simpleFoam.log.gz"
    data = gzip.decompress(archive.read_bytes())
    monitor = LiveSolverMonitor()
    for offset in range(0, len(data), 113):
        monitor.feed(data[offset:offset + 113])
    assert monitor.error is None
    canonical, numerics = solver_iteration_diagnostics(data.decode(), "", "100")
    assert list(monitor.history) == canonical
    assert monitor.total_samples == 400
    assert monitor.iteration == 100
    assert not numerics["run_reported_convergence"]
