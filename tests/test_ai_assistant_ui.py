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
        text = window.transcript.get("1.0", "end")
        assert "LOCAL EVIDENCE REVIEW" in text
        assert "No network request made" in window.status.get()
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
