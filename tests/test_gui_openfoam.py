from __future__ import annotations

import hashlib
import json
import os
import queue
import signal
import subprocess
import tkinter as tk
from types import SimpleNamespace

import pytest

from cleanroomx import gui_openfoam
from cleanroomx.gui_openfoam import (
    build_openfoam_generate_command,
    build_openfoam_run_command,
    build_openfoam_sync_vtk_command,
    read_openfoam_evidence_preview,
)


def test_case_generation_command_keeps_paths_as_single_arguments() -> None:
    command = build_openfoam_generate_command(
        "/tmp/spec with spaces.json",
        "/tmp/new case bundle",
        python_executable="/python",
    )

    assert command == [
        "/python",
        "-m",
        "cleanroomx.cfd_pipeline_cli",
        "generate",
        "/tmp/spec with spaces.json",
        "/tmp/new case bundle",
    ]


def test_run_command_only_enables_sync_with_a_safe_simulation_id() -> None:
    command = build_openfoam_run_command(
        "/tmp/case bundle",
        result_directory="/tmp/results",
        simulation_id="run-001",
        python_executable="/python",
    )

    assert command[-4:] == [
        "--sync-results",
        "/tmp/results",
        "--simulation-id",
        "run-001",
    ]
    with pytest.raises(ValueError, match="safe simulation ID"):
        build_openfoam_run_command(
            "/tmp/case bundle",
            result_directory="/tmp/results",
            simulation_id="../../outside",
        )
    with pytest.raises(ValueError, match="requires a result directory"):
        build_openfoam_run_command(
            "/tmp/case bundle",
            simulation_id="run-001",
        )


def test_sync_vtk_command_is_a_single_scan_and_preserves_source_paths() -> None:
    command = build_openfoam_sync_vtk_command(
        "/tmp/VTK output",
        "/tmp/imported results",
        "/tmp/case bundle/manifest.json",
        "vtk-run-01",
        python_executable="/python",
    )

    assert command[0] == "/python"
    assert command[4:6] == ["/tmp/VTK output", "/tmp/imported results"]
    assert command[-1] == "--once"


def test_live_vtk_command_watches_and_keeps_extra_field_map_path_intact() -> None:
    command = build_openfoam_sync_vtk_command(
        "/tmp/VTK output",
        "/tmp/imported results",
        "/tmp/case bundle/manifest.json",
        "vtk-run-01",
        field_map_file="/tmp/maps with spaces.json",
        once=False,
        interval_seconds=0.25,
        python_executable="/python",
    )

    assert command[0] == "/python"
    assert command[4:6] == ["/tmp/VTK output", "/tmp/imported results"]
    assert "--once" not in command
    assert command[command.index("--field-map-file") + 1] == "/tmp/maps with spaces.json"
    assert command[command.index("--interval-seconds") + 1] == "0.25"
    assert command[command.index("--stable-seconds") + 1] == "0.5"
    assert "--quiet-unchanged" in command


@pytest.mark.parametrize("interval", [0, 0.099, 3600.1, float("nan"), float("inf")])
def test_live_vtk_command_rejects_invalid_scan_intervals(interval) -> None:
    with pytest.raises(ValueError, match="Scan interval"):
        build_openfoam_sync_vtk_command(
            "/tmp/VTK output",
            "/tmp/imported results",
            "/tmp/case bundle/manifest.json",
            "vtk-run-01",
            once=False,
            interval_seconds=interval,
        )


def test_process_event_queue_drops_old_output_and_preserves_completion() -> None:
    events: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=2)
    dropped = []

    for line in ("one", "two", "three"):
        gui_openfoam._enqueue_process_event(
            events,
            ("output", line),
            on_output_dropped=lambda: dropped.append(True),
        )
    gui_openfoam._enqueue_process_event(
        events,
        ("finished", 0),
        on_output_dropped=lambda: dropped.append(True),
    )

    assert list(events.queue) == [("output", "three"), ("finished", 0)]
    assert len(dropped) == 2


def test_output_trim_plan_keeps_one_notice_and_bounds_retained_text() -> None:
    limit = 512
    current_chars = limit + 32

    remove_chars, add_notice = gui_openfoam._output_trim_plan(
        current_chars,
        already_trimmed=False,
        max_chars=limit,
        notice_chars=48,
    )
    assert add_notice is True
    assert current_chars + 48 - remove_chars == limit

    remove_chars, add_notice = gui_openfoam._output_trim_plan(
        limit + 12,
        already_trimmed=True,
        max_chars=limit,
        notice_chars=48,
    )
    assert add_notice is False
    assert remove_chars == 12


def test_openfoam_output_log_is_bounded_and_can_be_cleared_or_copied():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    statuses = []
    workspace = gui_openfoam.OpenFOAMWorkspace(
        root,
        status_setter=statuses.append,
    )
    try:
        workspace._append("x" * (gui_openfoam._MAX_OUTPUT_CHARS + 500))
        retained = workspace.output.get("1.0", "end-1c")
        assert len(retained) == gui_openfoam._MAX_OUTPUT_CHARS
        assert retained.startswith(gui_openfoam._OUTPUT_TRIM_NOTICE)
        assert retained.endswith("x" * 500)
        assert workspace._output_truncated is True

        workspace.clear_output()
        assert workspace.output.get("1.0", "end-1c") == ""
        assert workspace._output_chars == 0
        assert workspace._output_truncated is False

        workspace._append("retained command log")
        workspace.copy_output()
        assert root.clipboard_get() == "retained command log"
        assert statuses[-1].startswith("Copied 20 characters")
    finally:
        root.destroy()


def test_evidence_preview_reports_digest_and_diagnostic_status(tmp_path) -> None:
    manifest = {
        "schema_version": "cleanroomx.openfoam.v1",
        "status": "executed_requires_convergence_review",
        "files": {"configuration_1/system/blockMeshDict": "0" * 64},
    }
    path = tmp_path / "manifest.json"
    raw = (json.dumps(manifest, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)

    previews = read_openfoam_evidence_preview(tmp_path)

    assert len(previews) == 1
    assert previews[0]["path"] == "manifest.json"
    assert previews[0]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert previews[0]["summary"]["status"] == "executed_requires_convergence_review"


def test_evidence_preview_rejects_a_symlink_directory(tmp_path) -> None:
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")

    with pytest.raises(ValueError, match="regular directory"):
        read_openfoam_evidence_preview(link)

def test_sync_vtk_command_rejects_ids_longer_than_backend_limit() -> None:
    with pytest.raises(ValueError, match="1-64 safe ASCII"):
        build_openfoam_sync_vtk_command(
            "/tmp/VTK output",
            "/tmp/imported results",
            "/tmp/case bundle/manifest.json",
            "v" * 65,
        )

    command = build_openfoam_sync_vtk_command(
        "/tmp/VTK output",
        "/tmp/imported results",
        "/tmp/case bundle/manifest.json",
        "v" * 64,
    )
    assert command[-5] == "--simulation-id"
    assert command[-4] == "v" * 64


def test_process_group_launch_options_isolate_solver_children(monkeypatch) -> None:
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)

    assert gui_openfoam._process_group_launch_options(windows=False) == {
        "start_new_session": True
    }
    assert gui_openfoam._process_group_launch_options(windows=True) == {
        "creationflags": 512
    }


@pytest.mark.parametrize(
    ("force", "expected_signal"),
    ((False, signal.SIGTERM), (True, signal.SIGKILL)),
)
def test_posix_process_stop_signals_the_openfoam_process_group(
    monkeypatch, force, expected_signal
) -> None:
    calls = []
    monkeypatch.setattr(
        gui_openfoam.os,
        "killpg",
        lambda process_group, received_signal: calls.append(
            (process_group, received_signal)
        ),
    )
    process = SimpleNamespace(pid=4321)

    gui_openfoam._signal_process_tree(process, force=force, windows=False)

    assert calls == [(4321, expected_signal)]


def test_windows_graceful_process_stop_uses_console_group_signal(monkeypatch) -> None:
    monkeypatch.setattr(gui_openfoam.signal, "CTRL_BREAK_EVENT", 999, raising=False)
    received = []
    process = SimpleNamespace(pid=4321, send_signal=received.append)

    gui_openfoam._signal_process_tree(process, windows=True)

    assert received == [999]


def test_windows_force_stop_uses_taskkill_tree(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        gui_openfoam.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )
    process = SimpleNamespace(pid=4321, poll=lambda: 0, kill=lambda: None)

    gui_openfoam._signal_process_tree(process, force=True, windows=True)

    assert calls[0][0] == ["taskkill", "/PID", "4321", "/T", "/F"]
    assert calls[0][1].get("shell", False) is False


