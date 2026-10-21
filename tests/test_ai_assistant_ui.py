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



def test_ai_window_next_actions_includes_bound_cfd_followups(monkeypatch):
    """Synthetic evidence tests UI wiring; does not assert solver authenticity."""
    from cleanroomx.ai_assistant import build_assistant_context

    root = _root()
    root.withdraw()
    project = new_project()
    key = project_chat_key(None, unsaved_id="cfd-next-checks")
    window = AssistantWindow(
        root,
        project_getter=lambda: project,
        base_dir_getter=lambda: None,
        project_key_getter=lambda: key,
    )
    evidence = {
        "schema": "cleanroomx.ai-cfd-evidence",
        "schema_version": 1,
        "evidence_type": "exported_recorded_open_door_cfd",
        "scenario": "all_doors_open",
        "report_sha256": "a" * 64,
        "saved_project_source_sha256": "b" * 64,
        "engineering_release": "HOLD",
        "closed_door_5pa_demonstrated": False,
        "review_reasons": [
            {"code": "OPEN_DOOR_SCENARIO", "message": "Open door recording."},
        ],
        "non_prescriptive_checks": ["Review original solver inputs."],
    }
    context = build_assistant_context(project)
    context["cfd_evidence"] = evidence
    monkeypatch.setattr(window, "_snapshot", lambda: context)
    try:
        window.review_action_plan()
        transcript = window.transcript.get("1.0", "end")
        assert "ENGINEERING NEXT-ACTIONS PLAN" in transcript
        assert "RECORDED CFD NEXT CHECKS" in transcript
        assert "SOLVER_ORIGIN_UNVERIFIED" in transcript
        assert "No network or design changes" in window.status.get()
    finally:
        window._close()
        root.destroy()


def test_gui_generated_case_handoff_requires_explicit_confirmation(tmp_path, monkeypatch):
    """The assistant never runs OpenFOAM; handoff only opens the existing GUI."""
    root = _root()
    root.withdraw()
    project = new_project()
    key = project_chat_key(None, unsaved_id="handoff")
    opened = []
    validated = []
    proposal = {"schema": "cleanroomx.ai-cfd-run-handoff"}
    case = tmp_path / "generated"
    monkeypatch.setattr(
        "cleanroomx.ai_assistant_ui.filedialog.askdirectory",
        lambda **_kwargs: str(case),
    )
    monkeypatch.setattr(
        "cleanroomx.ai_assistant_ui.prepare_cfd_run_handoff",
        lambda *_args, **_kwargs: proposal,
    )
    monkeypatch.setattr(
        "cleanroomx.ai_assistant_ui.render_cfd_run_handoff",
        lambda *_args: "CASE PREVIEW — NOT EXECUTED",
    )
    def validate(_proposal, *, project, project_path):
        validated.append((project, project_path))
        return case
    monkeypatch.setattr(
        "cleanroomx.ai_assistant_ui.revalidate_cfd_run_handoff", validate,
    )
    window = AssistantWindow(
        root, project_getter=lambda: project,
        base_dir_getter=lambda: None, project_key_getter=lambda: key,
        project_path_getter=lambda: tmp_path / "saved.json",
        open_cfd_case=opened.append,
    )
    try:
        monkeypatch.setattr(
            "cleanroomx.ai_assistant_ui.messagebox.askyesno",
            lambda *_args, **_kwargs: False,
        )
        window.handoff_cfd_case()
        assert opened == []
        assert validated == []
        assert "CASE PREVIEW" in window.transcript.get("1.0", "end")
        assert "not confirmed" in window.status.get()

        monkeypatch.setattr(
            "cleanroomx.ai_assistant_ui.messagebox.askyesno",
            lambda *_args, **_kwargs: True,
        )
        window.handoff_cfd_case()
        assert opened == [case]
        assert len(validated) == 1
        assert "Solver NOT started" in window.status.get()
    finally:
        window._close()
        root.destroy()


def test_gui_handoff_blocks_mutation_between_preview_and_consent(tmp_path, monkeypatch):
    root = _root()
    root.withdraw()
    key = project_chat_key(None, unsaved_id="handoff-stale")
    opened = []
    monkeypatch.setattr(
        "cleanroomx.ai_assistant_ui.filedialog.askdirectory",
        lambda **_kwargs: str(tmp_path / "generated"),
    )
    monkeypatch.setattr(
        "cleanroomx.ai_assistant_ui.prepare_cfd_run_handoff",
        lambda *_args, **_kwargs: {"schema": "cleanroomx.ai-cfd-run-handoff"},
    )
    monkeypatch.setattr(
        "cleanroomx.ai_assistant_ui.render_cfd_run_handoff",
        lambda *_args: "Read-only preview",
    )
    monkeypatch.setattr(
        "cleanroomx.ai_assistant_ui.messagebox.askyesno",
        lambda *_args, **_kwargs: True,
    )
    def reject(*_args, **_kwargs):
        raise ValueError("CFD case changed since preview")
    monkeypatch.setattr(
        "cleanroomx.ai_assistant_ui.revalidate_cfd_run_handoff", reject,
    )
    window = AssistantWindow(
        root, project_getter=new_project,
        base_dir_getter=lambda: None, project_key_getter=lambda: key,
        project_path_getter=lambda: tmp_path / "saved.json",
        open_cfd_case=opened.append,
    )
    try:
        window.handoff_cfd_case()
        assert opened == []
        assert "changed since preview" in window.transcript.get("1.0", "end")
        assert "failed safely" in window.status.get()
    finally:
        window._close()
        root.destroy()


def test_cancelled_model_reply_is_dropped_after_new_request(monkeypatch):
    """Delayed provider replies cannot overwrite the newer conversation."""
    from cleanroomx import ai_assistant_ui

    root = _root()
    root.withdraw()
    project = new_project()
    key = project_chat_key(None, unsaved_id="cancelled-model")
    deferred = []

    class DeferredThread:
        def __init__(self, *, target, **_kwargs):
            self.worker = target
            deferred.append(self)
        def start(self):
            pass

    monkeypatch.setattr(ai_assistant_ui.threading, "Thread", DeferredThread)
    monkeypatch.setattr(
        ai_assistant_ui, "ask_model",
        lambda question, *_args, **_kwargs: "Reply: " + question,
    )
    window = AssistantWindow(
        root, project_getter=lambda: project,
        base_dir_getter=lambda: None, project_key_getter=lambda: key,
    )
    try:
        session_id = window._session_id
        window.question.insert(0, "Discard this question")
        window.ask_ai()
        assert window._busy
        assert str(window.cancel_button.cget("state")) == "normal"
        assert len(deferred) == 1

        window.cancel_ai()
        assert not window._busy
        assert window._active_request_id is None
        assert str(window.cancel_button.cget("state")) == "disabled"
        assert "may continue until timeout" in window.status.get()
        assert not window._conversations.require_session(session_id, key).messages

        window.question.insert(0, "Keep this question")
        window.ask_ai()
        assert len(deferred) == 2
        assert window._busy

        # Old provider completes first, then the current request. Only the
        # second request can be committed; no stale first Q/A may leak.
        deferred[0].worker()
        deferred[1].worker()
        window._poll()

        messages = window._conversations.require_session(session_id, key).messages
        assert [item.content for item in messages] == [
            "Keep this question", "Reply: Keep this question",
        ]
        assert "Discard this question" not in window.transcript.get("1.0", "end")
        assert not window._busy
        assert window._active_request_id is None
        assert str(window.cancel_button.cget("state")) == "disabled"
    finally:
        window._close()
        root.destroy()


def test_cancelled_response_without_successor_does_not_change_chat(monkeypatch):
    from cleanroomx import ai_assistant_ui

    root = _root()
    root.withdraw()
    project = new_project()
    key = project_chat_key(None, unsaved_id="cancel-alone")
    workers = []

    class DeferredThread:
        def __init__(self, *, target, **_kwargs):
            workers.append(target)
        def start(self):
            pass

    monkeypatch.setattr(ai_assistant_ui.threading, "Thread", DeferredThread)
    monkeypatch.setattr(
        ai_assistant_ui, "ask_model",
        lambda question, *_args, **_kwargs: "Late answer",
    )
    window = AssistantWindow(
        root, project_getter=lambda: project,
        base_dir_getter=lambda: None, project_key_getter=lambda: key,
    )
    try:
        window.question.insert(0, "Old pending question")
        window.ask_ai()
        window.cancel_ai()
        workers[0]()
        window._poll()
        assert not window._conversations.require_session(
            window._session_id, key,
        ).messages
        assert "Late answer" not in window.transcript.get("1.0", "end")
        assert "cancelled in this window" in window.status.get()
    finally:
        window._close()
        root.destroy()


def test_assistant_snapshot_rejects_mutation_during_diagnostics(monkeypatch):
    """Do not send diagnostics for a project revision that no longer exists."""
    from cleanroomx import ai_assistant_ui

    root = _root()
    root.withdraw()
    project = new_project("Original review")
    key = project_chat_key(None, unsaved_id="mutating-diagnostics")
    window = AssistantWindow(
        root, project_getter=lambda: project,
        base_dir_getter=lambda: None, project_key_getter=lambda: key,
    )
    original = ai_assistant_ui.build_assistant_context

    def mutate_after_build(source, **kwargs):
        context = original(source, **kwargs)
        source.name = "Changed after diagnostics"
        return context

    try:
        monkeypatch.setattr(
            ai_assistant_ui, "build_assistant_context", mutate_after_build,
        )
        with pytest.raises(ValueError, match="changed during assistant snapshot"):
            window._snapshot()
        assert not window._conversations.require_session(
            window._session_id, key,
        ).messages
    finally:
        window._close()
        root.destroy()


def test_assistant_snapshot_rejects_cross_project_cfd_binding(
    tmp_path, monkeypatch,
):
    """Switching project during an export read must never mix snapshots."""
    from cleanroomx import ai_assistant_ui

    root = _root()
    root.withdraw()
    old_project = new_project("Old facility")
    new_project_doc = new_project("New facility")
    old_key = project_chat_key(None, unsaved_id="snapshot-old")
    new_key = project_chat_key(None, unsaved_id="snapshot-new")
    state = {"project": old_project, "key": old_key}
    case_export = tmp_path / "recorded-export"
    window = AssistantWindow(
        root, project_getter=lambda: state["project"],
        base_dir_getter=lambda: None,
        project_key_getter=lambda: state["key"],
        project_path_getter=lambda: tmp_path / "facility.json",
    )
    window._cfd_export_dir = case_export
    window._cfd_project_key = old_key
    observed = []

    def bind_and_switch(directory, *, project, project_path):
        observed.append((directory, project, project_path))
        state["project"] = new_project_doc
        state["key"] = new_key
        return {"schema": "cleanroomx.ai-cfd-evidence", "report_sha256": "a" * 64}

    try:
        monkeypatch.setattr(
            ai_assistant_ui, "bound_cfd_evidence", bind_and_switch,
        )
        with pytest.raises(ValueError, match="changed during assistant snapshot"):
            window._snapshot()
        assert len(observed) == 1
        assert observed[0][1] is old_project
        assert not window._conversations.require_session(
            window._session_id, old_key,
        ).messages
    finally:
        window._close()
        root.destroy()


def test_assistant_snapshot_rejects_save_as_during_cfd_read(
    tmp_path, monkeypatch,
):
    """A changed saved-project path invalidates the selected CFD binding."""
    from cleanroomx import ai_assistant_ui

    root = _root()
    root.withdraw()
    project = new_project("Path-sensitive export")
    key = project_chat_key(None, unsaved_id="saved-source-revision")
    state = {"path": tmp_path / "first.json"}
    window = AssistantWindow(
        root, project_getter=lambda: project,
        base_dir_getter=lambda: None, project_key_getter=lambda: key,
        project_path_getter=lambda: state["path"],
    )
    window._cfd_export_dir = tmp_path / "export"
    window._cfd_project_key = key

    def bind_and_save_as(directory, *, project, project_path):
        state["path"] = tmp_path / "second.json"
        return {"schema": "cleanroomx.ai-cfd-evidence", "report_sha256": "a" * 64}

    try:
        monkeypatch.setattr(
            ai_assistant_ui, "bound_cfd_evidence", bind_and_save_as,
        )
        with pytest.raises(ValueError, match="changed during assistant snapshot"):
            window._snapshot()
    finally:
        window._close()
        root.destroy()


def test_stale_assistant_reply_remains_marked_after_redraw(monkeypatch):
    """Persisted UI rendering must not promote old-revision AI advice."""
    from cleanroomx import ai_assistant_ui

    root = _root()
    root.withdraw()
    project = new_project("Before request")
    key = project_chat_key(None, unsaved_id="stale-reply")
    delayed = []

    class DeferredThread:
        def __init__(self, *, target, **_kwargs):
            delayed.append(target)
        def start(self):
            pass

    monkeypatch.setattr(ai_assistant_ui.threading, "Thread", DeferredThread)
    monkeypatch.setattr(
        ai_assistant_ui, "ask_model",
        lambda *_args, **_kwargs: "Advice based on old project",
    )
    window = AssistantWindow(
        root, project_getter=lambda: project,
        base_dir_getter=lambda: None, project_key_getter=lambda: key,
    )
    try:
        window.question.insert(0, "Review project")
        window.ask_ai()
        project.name = "After request"
        delayed[0]()
        window._poll()
        chat = window._conversations.require_session(window._session_id, key)
        assert [message.role for message in chat.messages] == ["user", "assistant"]
        assert chat.messages[1].metadata["stale_project_on_receipt"] is True
        assert "STALE project/CFD snapshot" in window.transcript.get("1.0", "end")
        window._redraw()
        assert "STALE project/CFD snapshot" in window.transcript.get("1.0", "end")
        assert "Advice based on old project" in window.transcript.get("1.0", "end")
    finally:
        window._close()
        root.destroy()
