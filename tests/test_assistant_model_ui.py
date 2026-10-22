"""Actual Tk regression of opt-in model window, display gated."""
from __future__ import annotations

import os
import tkinter as tk

import pytest

import cleanroomx.assistant_model_ui as ui


@pytest.fixture
def window(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Actual Tk display unavailable: {exc}")
    errors = []
    root.report_callback_exception = lambda *args: errors.append(args)
    root.withdraw()
    dialog = ui.ModelAssistantWindow(root, tmp_path / "saved-project.json")
    root.update()
    try:
        yield root, dialog
        assert errors == []
    finally:
        if dialog.winfo_exists():
            dialog._close()
        root.destroy()


def test_open_does_not_auto_transmit_or_run_review(window, monkeypatch):
    root, dialog = window
    calls = []
    monkeypatch.setattr(
        ui, "ask_model_about_saved_project",
        lambda *args: calls.append(args) or ("unverified", "a" * 64),
    )
    root.update()
    assert calls == []
    assert "No network request" in dialog.status_var.get()
    dialog.ask()  # empty question is refused without a request
    root.update()
    assert calls == []


def test_explicit_ask_uses_worker_and_shows_unverified_label(window, monkeypatch):
    root, dialog = window
    calls = []

    def fake_ask(path, question):
        calls.append((path, question))
        return ("Recommended additional checks.", "a" * 64)

    class SynchronousThread:
        def __init__(self, *, target, args, daemon):
            self.target = target
            self.args = args
            assert daemon
        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(ui, "ask_model_about_saved_project", fake_ask)
    monkeypatch.setattr(ui, "Thread", SynchronousThread)
    dialog.question.insert("1.0", "What evidence is missing?")
    dialog.ask()
    root.update()
    assert len(calls) == 1
    assert calls[0][1] == "What evidence is missing?"
    assert "UNVERIFIED AI SUGGESTION" in dialog.output.get("1.0", "end")
    assert "Recommended additional checks." in dialog.output.get("1.0", "end")
    assert "saved project SHA-256" in dialog.status_var.get()


def test_failed_opt_in_model_call_does_not_publish_suggestion(window, monkeypatch):
    root, dialog = window
    def refuse(*args):
        raise ValueError("Saved project revision changed")
    class SynchronousThread:
        def __init__(self, *, target, args, daemon):
            self.target, self.args = target, args
        def start(self):
            self.target(*self.args)
    monkeypatch.setattr(ui, "ask_model_about_saved_project", refuse)
    monkeypatch.setattr(ui, "Thread", SynchronousThread)
    dialog.question.insert("1.0", "Review missing evidence")
    dialog.ask()
    root.update()
    assert "No trusted model response was published." in dialog.output.get("1.0", "end")
    assert "changed" in dialog.status_var.get()
