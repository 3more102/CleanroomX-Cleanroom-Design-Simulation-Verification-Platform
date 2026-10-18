"""GUI integration tests for receipt-verified OpenFOAM diagnostics."""
import tkinter as tk

import pytest

from cleanroomx import gui_openfoam
from cleanroomx.gui_openfoam import OpenFOAMWorkspace


def _root():
    try:
        return tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")


def test_export_verified_diagnostics_uses_case_receipt_and_safe_destination(monkeypatch, tmp_path):
    root = _root()
    calls = []
    monkeypatch.setattr(gui_openfoam.filedialog, "askdirectory", lambda **kwargs: str(tmp_path))
    try:
        workspace = OpenFOAMWorkspace(root)
        workspace.two_room_case_directory_var.set(str(tmp_path / "case with spaces"))
        workspace.two_room_receipt_directory_var.set(str(tmp_path / "receipt folder"))
        monkeypatch.setattr(workspace, "_start_command", lambda label, command: calls.append((label, command)))
        workspace.two_room_verified_button.invoke()
        assert len(calls) == 1
        command = calls[0][1]
        assert command[3] == "two-room-verified-bundle"
        assert command[4] == str(tmp_path / "case with spaces")
        assert command[5] == str(tmp_path / "receipt folder" / "two_room_run_receipt.json")
        assert command[6] == str(tmp_path / "two-room-verified-diagnostics")
    finally:
        root.destroy()


def test_export_does_not_overwrite_existing_directory(monkeypatch, tmp_path):
    root = _root()
    (tmp_path / "two-room-verified-diagnostics").mkdir()
    calls = []
    monkeypatch.setattr(gui_openfoam.filedialog, "askdirectory", lambda **kwargs: str(tmp_path))
    monkeypatch.setattr(gui_openfoam.messagebox, "showerror", lambda *args, **kwargs: None)
    try:
        workspace = OpenFOAMWorkspace(root)
        workspace.two_room_case_directory_var.set("case")
        workspace.two_room_receipt_directory_var.set("receipt")
        monkeypatch.setattr(workspace, "_start_command", lambda *args: calls.append(args))
        workspace.two_room_verified_button.invoke()
        assert not calls
    finally:
        root.destroy()


def test_audit_verified_diagnostics_launches_cli(monkeypatch, tmp_path):
    root = _root()
    calls = []
    monkeypatch.setattr(gui_openfoam.filedialog, "askdirectory", lambda **kwargs: str(tmp_path))
    try:
        workspace = OpenFOAMWorkspace(root)
        monkeypatch.setattr(workspace, "_start_command", lambda label, command: calls.append(command))
        workspace.two_room_audit_button.invoke()
        assert len(calls) == 1
        assert calls[0][3:] == ["two-room-bundle-audit", str(tmp_path)]
    finally:
        root.destroy()
