from __future__ import annotations

import hashlib
import queue
import tkinter as tk
import json
import signal
import subprocess
import time
from types import SimpleNamespace

import pytest

from cleanroomx import gui_openfoam
from cleanroomx.gui_openfoam import (
    OpenFOAMConsoleLog,
    OpenFOAMWorkspace,
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


def test_case_verification_summary_keeps_validation_limit_clear() -> None:
    summary = OpenFOAMWorkspace._format_case_verification(
        {
            "files_checked": 24,
            "files_expected": 24,
            "boundary_audits_passed": 3,
            "total_bytes_checked": 2048,
            "manifest_sha256": "a" * 64,
        }
    )

    assert "Case-input hashes: MATCH local manifest" in summary
    assert "Generated inputs: 24/24" in summary
    assert "Boundary-input consistency: 3/3 configurations passed" in summary
    assert "Manifest trust: local file; not digitally signed" in summary
    assert "Scientific validation: BLOCKED" in summary



def test_openfoam_console_log_bounds_live_view_and_saves_full_session(tmp_path) -> None:
    console = OpenFOAMConsoleLog(
        max_display_chars=128,
        max_display_lines=3,
        spool_max_bytes=32,
    )
    full_output = "".join(f"solver line {index:03d}\n" for index in range(12))
    visible = ""
    try:
        for line in full_output.splitlines(keepends=True):
            removed = console.append(line)
            visible = (visible + line)[removed:]

        assert console.truncated is True
        assert visible == console.display_text
        assert visible == "solver line 009\nsolver line 010\nsolver line 011\n"

        saved = tmp_path / "complete-openfoam-session.log"
        assert console.save_to(saved) == saved
        assert saved.read_text(encoding="utf-8") == full_output

        console.append("final status\n")
        saved_again = tmp_path / "complete-openfoam-session-2.log"
        console.save_to(saved_again)
        assert saved_again.read_text(encoding="utf-8") == full_output + "final status\n"
    finally:
        console.close()


def test_openfoam_console_log_bounds_an_unterminated_long_line() -> None:
    console = OpenFOAMConsoleLog(
        max_display_chars=8,
        max_display_lines=2,
        spool_max_bytes=8,
    )
    try:
        removed = console.append("0123456789")
        assert removed == 2
        assert console.display_text == "23456789"
        assert console.truncated is True
    finally:
        console.close()


def test_openfoam_console_log_save_requires_an_available_session(tmp_path) -> None:
    console = OpenFOAMConsoleLog()
    console.close()

    with pytest.raises(OSError, match="session log is closed"):
        console.save_to(tmp_path / "closed.log")


def test_openfoam_console_log_save_failure_preserves_existing_destination(
    monkeypatch, tmp_path
) -> None:
    console = OpenFOAMConsoleLog()
    console.append("new session output\n")
    destination = tmp_path / "existing.log"
    destination.write_text("previous file\n", encoding="utf-8")

    def fail_copy(*_args, **_kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(gui_openfoam.shutil, "copyfileobj", fail_copy)
    try:
        with pytest.raises(OSError, match="simulated disk failure"):
            console.save_to(destination)
        assert destination.read_text(encoding="utf-8") == "previous file\n"
        assert list(tmp_path.glob(".cleanroomx-console-*.tmp")) == []
    finally:
        console.close()


def test_openfoam_event_drain_batches_output_and_yields_to_tk() -> None:
    workspace = OpenFOAMWorkspace.__new__(OpenFOAMWorkspace)
    workspace._destroyed = False
    workspace._events = queue.Queue()
    expected = [f"solver output {index:03d}\n" for index in range(300)]
    for line in expected:
        workspace._events.put(("output", line))
    appended: list[str] = []
    scheduled: list[tuple[int, object]] = []
    workspace._append = appended.append
    workspace.after = lambda delay, callback: scheduled.append((delay, callback))

    workspace._drain_events()

    assert appended == ["".join(expected[:256])]
    assert workspace._events.qsize() == 44
    assert scheduled[0][0] == 15

    scheduled.clear()
    workspace._drain_events()
    assert appended[1] == "".join(expected[256:])
    assert workspace._events.empty()
    assert scheduled[0][0] == 120


def test_openfoam_workspace_compact_console_stays_scrollable() -> None:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    try:
        root.geometry("900x300")
        workspace = OpenFOAMWorkspace(root)
        workspace.pack(fill="both", expand=True)
        root.update()

        assert workspace._output_frame.winfo_height() == 122
        assert workspace._workflow_canvas.winfo_height() > 0
        assert (
            workspace._workflow_canvas.winfo_height()
            < workspace._workflow_content.winfo_height()
        )
        assert workspace.save_log_button.winfo_viewable()
        assert "disabled" in workspace.save_log_button.state()
        assert "disabled" in workspace.export_graph_button.state()
    finally:
        root.destroy()


def test_openfoam_proofgraph_export_button_loads_export_into_viewer(
    monkeypatch, tmp_path
) -> None:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    destination = tmp_path / "openfoam-proofgraph.json"
    document = {"graph_sha256": "a" * 64}
    loaded: list[dict] = []
    monkeypatch.setattr(
        gui_openfoam.filedialog,
        "asksaveasfilename",
        lambda **_kwargs: str(destination),
    )
    monkeypatch.setattr(
        gui_openfoam,
        "export_openfoam_proofgraph",
        lambda *_args: document,
    )
    try:
        workspace = OpenFOAMWorkspace(
            root,
            on_proofgraph_loaded=loaded.append,
        )
        workspace.pack(fill="both", expand=True)
        workspace.result_directory_var.set(str(tmp_path))
        workspace.vtk_simulation_id_var.set("simulation-001")
        root.update()

        assert "disabled" not in workspace.export_graph_button.state()
        workspace.export_graph_button.invoke()
        deadline = time.monotonic() + 2.0
        while not loaded and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        root.update()

        assert loaded == [document]
        assert not workspace._busy
    finally:
        root.destroy()
