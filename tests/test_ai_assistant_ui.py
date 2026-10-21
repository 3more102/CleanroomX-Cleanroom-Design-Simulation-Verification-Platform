from __future__ import annotations

import tkinter as tk

import pytest

from cleanroomx.ai_assistant_chat import project_chat_key
from cleanroomx.ai_assistant_ui import AssistantWindow
from cleanroomx.project import new_project


def _root():
    try:
        return tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable; GUI test requires xvfb/desktop")


def test_ai_window_offline_review_and_project_isolation():
    root = _root()
    root.withdraw()
    state = {
        "project": new_project(),
        "key": project_chat_key(None, unsaved_id="unsaved-1"),
    }
    window = AssistantWindow(
        root,
        project_getter=lambda: state["project"],
        base_dir_getter=lambda: None,
        project_key_getter=lambda: state["key"],
    )
    try:
        original_chat = window._session_id
        window.review_project()
        window.review_action_plan()
        window.review_focus.set("cfd")
        window.review_specialist()
        text = window.transcript.get("1.0", "end")
        assert "LOCAL EVIDENCE REVIEW" in text
        assert "ENGINEERING NEXT-ACTIONS PLAN" in text
        assert "SPECIALIST ENGINEERING REVIEW" in text
        assert "CFD_EXPORT | NOT_EVIDENCED" in text
        assert "No CleanroomX analyses" in text
        assert "No model, network or design edits" in window.status.get()
        window.new_chat()
        assert len(window._conversations.sessions(state["key"])) == 2
        assert window._session_id != original_chat

        state["project"] = new_project()
        state["key"] = project_chat_key(None, unsaved_id="unsaved-2")
        window._ensure_session()
        assert window._session_id not in (original_chat,)
        assert len(window._conversations.sessions(state["key"])) == 1
        assert len(window._conversations.sessions(
            project_chat_key(None, unsaved_id="unsaved-1")
        )) == 2
        assert "LOCAL EVIDENCE REVIEW" not in window.transcript.get("1.0", "end")
    finally:
        window._close()
        root.destroy()


def test_ai_window_explicit_save_load_does_not_overwrite_project(tmp_path, monkeypatch):
    root = _root()
    root.withdraw()
    key = project_chat_key(tmp_path / "working-project.json")
    window = AssistantWindow(
        root,
        project_getter=new_project,
        base_dir_getter=lambda: None,
        project_key_getter=lambda: key,
    )
    file = tmp_path / "assistant-chats.json"
    try:
        monkeypatch.setattr(
            "cleanroomx.ai_assistant_ui.filedialog.asksaveasfilename",
            lambda **kwargs: str(file),
        )
        monkeypatch.setattr(
            "cleanroomx.ai_assistant_ui.filedialog.askopenfilename",
            lambda **kwargs: str(file),
        )
        monkeypatch.setattr(
            "cleanroomx.ai_assistant_ui.messagebox.askyesno",
            lambda *_args, **_kwargs: True,
        )
        window.save_chats()
        assert file.is_file()
        assert "saved locally" in window.status.get()

        window.new_chat()
        assert len(window._conversations.sessions(key)) == 2
        window.load_chats()
        assert len(window._conversations.sessions(key)) == 1
        assert "workspace loaded" in window.status.get()
    finally:
        window._close()
        root.destroy()



def test_ai_window_attaches_matching_cfd_export_to_snapshot_only(tmp_path, monkeypatch):
    root = _root()
    root.withdraw()
    key = project_chat_key(tmp_path / "facility.json")
    export = tmp_path / "computed"
    export.mkdir()
    (export / "report.json").write_text("{}", encoding="utf-8")
    observed = []

    def fake_bound(directory, *, project, project_path):
        observed.append((directory, project_path))
        return {"schema": "cleanroomx.ai-cfd-evidence", "engineering_release": "HOLD"}

    monkeypatch.setattr(
        "cleanroomx.ai_assistant_ui.bound_cfd_evidence", fake_bound
    )
    monkeypatch.setattr(
        "cleanroomx.ai_assistant_ui.format_cfd_evidence",
        lambda *_args: "Recorded CFD: HOLD",
    )
    monkeypatch.setattr(
        "cleanroomx.ai_assistant_ui.filedialog.askopenfilename",
        lambda **kwargs: str(export / "report.json"),
    )
    window = AssistantWindow(
        root,
        project_getter=new_project,
        base_dir_getter=lambda: None,
        project_key_getter=lambda: key,
        project_path_getter=lambda: tmp_path / "facility.json",
    )
    try:
        window.review_cfd_export()
        assert window._cfd_export_dir == export
        assert window._snapshot()["cfd_evidence"]["engineering_release"] == "HOLD"
        assert observed[-1] == (export, tmp_path / "facility.json")
        assert "Recorded CFD: HOLD" in window.transcript.get("1.0", "end")
        window.clear_cfd_export()
        assert window._cfd_export_dir is None
        assert "cfd_evidence" not in window._snapshot()
    finally:
        window._close()
        root.destroy()


def test_ai_window_clears_imported_cfd_on_project_switch(tmp_path, monkeypatch):
    root = _root()
    root.withdraw()
    state = {
        "project_key": project_chat_key(None, unsaved_id="facility-a"),
    }
    window = AssistantWindow(
        root,
        project_getter=new_project,
        base_dir_getter=lambda: None,
        project_key_getter=lambda: state["project_key"],
    )
    try:
        window._cfd_export_dir = tmp_path / "old-export"
        window._cfd_project_key = state["project_key"]
        state["project_key"] = project_chat_key(None, unsaved_id="facility-b")
        window._ensure_session()
        assert window._cfd_export_dir is None
        assert window._cfd_project_key is None
        assert "cfd_evidence" not in window._snapshot()
    finally:
        window._close()
        root.destroy()


def test_ai_window_rejects_unmatched_cfd_without_attaching(tmp_path, monkeypatch):
    root = _root()
    root.withdraw()
    key = project_chat_key(tmp_path / "facility.json")
    export = tmp_path / "computed"
    export.mkdir()
    (export / "report.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "cleanroomx.ai_assistant_ui.filedialog.askopenfilename",
        lambda **kwargs: str(export / "report.json"),
    )

    def reject(*_args, **_kwargs):
        raise ValueError("different saved project revision")

    monkeypatch.setattr("cleanroomx.ai_assistant_ui.bound_cfd_evidence", reject)
    window = AssistantWindow(
        root,
        project_getter=new_project,
        base_dir_getter=lambda: None,
        project_key_getter=lambda: key,
        project_path_getter=lambda: tmp_path / "facility.json",
    )
    try:
        window.review_cfd_export()
        assert window._cfd_export_dir is None
        assert "different saved project revision" in window.transcript.get("1.0", "end")
    finally:
        window._close()
        root.destroy()
