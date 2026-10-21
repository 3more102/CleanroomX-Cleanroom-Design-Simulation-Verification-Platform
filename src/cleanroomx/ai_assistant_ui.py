"""Read-only project-aware AI conversation window for CleanroomX desktop."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .ai_assistant import (
    AssistantConfiguration,
    ask_model,
    build_assistant_context,
    format_offline_review,
    project_snapshot_sha256,
)
from .ai_assistant_chat import AssistantConversations
from .ai_cfd_evidence import bound_cfd_evidence, format_cfd_evidence
from .ai_cfd_followup import build_cfd_followup_plan, render_cfd_followup_plan
from .ai_cfd_handoff import (
    prepare_cfd_run_handoff, revalidate_cfd_run_handoff, render_cfd_run_handoff,
)
from .ai_assistant_plan import build_assistant_action_plan, render_assistant_action_plan
from .ai_assistant_specialist import build_specialist_review, render_specialist_review
from .project import ProjectDocument


class AssistantWindow(tk.Toplevel):
    """Model requests never block Tk; messages cannot mutate project state."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        project_getter: Callable[[], ProjectDocument],
        base_dir_getter: Callable[[], str | Path | None],
        project_key_getter: Callable[[], str],
        project_path_getter: Callable[[], str | Path | None] | None = None,
        open_cfd_case: Callable[[Path], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("CleanroomX | AI Engineering Assistant")
        self.geometry("875x660")
        self.minsize(620, 440)
        self.transient(parent)
        self._project_getter = project_getter
        self._base_dir_getter = base_dir_getter
        self._project_key_getter = project_key_getter
        self._project_path_getter = project_path_getter or (lambda: None)
        self._open_cfd_case = open_cfd_case
        self._cfd_export_dir: Path | None = None
        self._cfd_project_key: str | None = None
        self._on_close = on_close
        self._conversations = AssistantConversations()
        self._active_project_key: str | None = None
        self._session_id: str | None = None
        self._session_ids: list[str] = []
        self._pending: Queue[dict] = Queue()
        self._busy = False
        self._closed = False

        content = ttk.Frame(self, padding=12)
        content.pack(fill="both", expand=True)
        ttk.Label(
            content, text="AI Engineering Assistant | Read-only",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            content,
            text=(
                "Project-bound conversations, canonical diagnostics, and "
                "optional AI suggestions. No changes to design or CFD results."
            ),
            wraplength=810, justify="left",
        ).pack(anchor="w", pady=(4, 10))

        sessions = ttk.Frame(content)
        sessions.pack(fill="x", pady=(0, 8))
        ttk.Label(sessions, text="Conversation").pack(side="left", padx=(0, 6))
        self.session_choice = ttk.Combobox(sessions, state="readonly", width=25)
        self.session_choice.pack(side="left", fill="x", expand=True)
        self.session_choice.bind("<<ComboboxSelected>>", self._on_session_selected)
        ttk.Button(sessions, text="New", command=self.new_chat).pack(side="left", padx=(6, 0))
        ttk.Button(sessions, text="Save chats...", command=self.save_chats).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(sessions, text="Load chats...", command=self.load_chats).pack(
            side="left", padx=(6, 0)
        )

        self.transcript = scrolledtext.ScrolledText(
            content, height=18, wrap="word", state="disabled",
        )
        self.transcript.pack(fill="both", expand=True)
        ttk.Label(content, text="Question").pack(anchor="w", pady=(10, 2))
        self.question = ttk.Entry(content)
        self.question.pack(fill="x")
        self.question.bind("<Return>", self._on_return)
        buttons = ttk.Frame(content)
        buttons.pack(fill="x", pady=(8, 4))
        self.review_button = ttk.Button(
            buttons, text="Review project (offline)", command=self.review_project
        )
        self.review_button.pack(side="left")
        self.plan_button = ttk.Button(
            buttons, text="Next actions (offline)", command=self.review_action_plan
        )
        self.plan_button.pack(side="left", padx=(6, 0))
        self.ask_button = ttk.Button(
            buttons, text="Ask AI", command=self.ask_ai
        )
        self.ask_button.pack(side="left", padx=8)
        ttk.Label(buttons, text="Review focus:").pack(side="left", padx=(14, 5))
        self.review_focus = tk.StringVar(value="general")
        ttk.Combobox(
            buttons, textvariable=self.review_focus, state="readonly",
            values=("general", "cfd", "hvac", "particles", "verification"),
            width=16,
        ).pack(side="left")

        evidence_buttons = ttk.Frame(content)
        evidence_buttons.pack(fill="x", pady=(0, 6))
        ttk.Label(evidence_buttons, text="Recorded CFD:").pack(side="left")
        self.cfd_button = ttk.Button(
            evidence_buttons, text="Review CFD export...",
            command=self.review_cfd_export,
        )
        self.cfd_button.pack(side="left", padx=(8, 0))
        ttk.Button(
            evidence_buttons, text="Clear evidence",
            command=self.clear_cfd_export,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            evidence_buttons, text="Specialist review (offline)",
            command=self.review_specialist,
        ).pack(side="left", padx=(12, 0))

        handoff_buttons = ttk.Frame(content)
        handoff_buttons.pack(fill="x", pady=(0, 6))
        ttk.Label(handoff_buttons, text="Generated CFD case:").pack(side="left")
        ttk.Button(
            handoff_buttons, text="Review and open CFD workspace...",
            command=self.handoff_cfd_case,
        ).pack(side="left", padx=(8, 0))

        self.status = tk.StringVar(
            value="Local Ollama by default. Save chats explicitly to preserve them."
        )
        ttk.Label(content, textvariable=self.status, wraplength=810).pack(anchor="w")

        self._ensure_session()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(125, self._poll)

    def _append(self, speaker: str, text: str) -> None:
        self.transcript.configure(state="normal")
        self.transcript.insert("end", speaker + "\n" + text + "\n\n")
        self.transcript.configure(state="disabled")
        self.transcript.see("end")

    def _clear(self) -> None:
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")

    def _ensure_session(self) -> None:
        key = self._project_key_getter()
        sessions = self._conversations.sessions(key)
        if not sessions:
            sessions = (self._conversations.new(key),)
        if key != self._active_project_key or self._session_id not in {
            session.id for session in sessions
        }:
            if key != self._active_project_key:
                # Imported evidence is never shared with another project.
                self._cfd_export_dir = None
                self._cfd_project_key = None
            self._active_project_key = key
            self._session_id = sessions[-1].id
            self._redraw()
        self._refresh_sessions()

    def _refresh_sessions(self) -> None:
        sessions = self._conversations.sessions(self._active_project_key)
        self._session_ids = [item.id for item in sessions]
        self.session_choice["values"] = [
            item.title + " (" + str(item.revision // 2) + ")"
            for item in sessions
        ]
        if self._session_id in self._session_ids:
            self.session_choice.current(self._session_ids.index(self._session_id))

    def _redraw(self) -> None:
        self._clear()
        self._append(
            "CleanroomX",
            "Conversations are in memory until explicitly saved. "
            "Responses are suggestions, not verified CFD or compliance evidence.",
        )
        if self._session_id is None:
            return
        chat = self._conversations.require_session(
            self._session_id, self._active_project_key
        )
        for message in chat.messages:
            self._append(
                "You" if message.role == "user" else "AI suggestion (unverified)",
                message.content,
            )

    def _on_session_selected(self, _event: tk.Event) -> None:
        selection = self.session_choice.current()
        if 0 <= selection < len(self._session_ids):
            self._session_id = self._session_ids[selection]
            self._redraw()

    def new_chat(self) -> None:
        self._ensure_session()
        count = len(self._conversations.sessions(self._active_project_key)) + 1
        session = self._conversations.new(self._active_project_key, "Engineering review " + str(count))
        self._session_id = session.id
        self._refresh_sessions()
        self._redraw()

    def save_chats(self) -> None:
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Save AI conversations (contains full questions and answers)",
            defaultextension=".json",
            filetypes=[("CleanroomX AI workspace", "*.json")],
        )
        if not destination:
            return
        path = Path(destination)
        try:
            if path.exists():
                # Never overwrite arbitrary JSON, especially a CleanroomX project file.
                AssistantConversations.load(path)
                if not messagebox.askyesno(
                    "Replace existing AI conversation file?",
                    "The selected AI conversation file already exists. Replace it?",
                    parent=self,
                ):
                    return
            self._conversations.save(path)
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("AI conversation save failed", str(exc), parent=self)
            return
        self.status.set("AI conversations saved locally. This file contains full chat text.")

    def load_chats(self) -> None:
        if self._busy:
            self.status.set("Finish the current request before loading another workspace.")
            return
        source = filedialog.askopenfilename(
            parent=self, title="Load AI conversations",
            filetypes=[("CleanroomX AI workspace", "*.json")],
        )
        if not source:
            return
        try:
            loaded = AssistantConversations.load(source)
            if not messagebox.askyesno(
                "Replace chats in this window?",
                "Loading a workspace replaces unsaved chats currently in this window. Continue?",
                parent=self,
            ):
                return
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("AI conversation load failed", str(exc), parent=self)
            return
        self._conversations = loaded
        self._active_project_key = None
        self._session_id = None
        self._ensure_session()
        self.status.set("AI workspace loaded; only conversations for this project are shown.")

    def _snapshot(self) -> dict:
        context = build_assistant_context(
            self._project_getter(), base_dir=self._base_dir_getter()
        )
        if self._cfd_export_dir is not None:
            if self._cfd_project_key != self._project_key_getter():
                raise ValueError("CFD evidence belongs to another project.")
            path = self._project_path_getter()
            if path is None:
                raise ValueError("Save the project before attaching CFD evidence.")
            # Re-read the export on every request; stale or modified evidence
            # must not be silently forwarded to the model.
            context["cfd_evidence"] = bound_cfd_evidence(
                self._cfd_export_dir,
                project=self._project_getter(),
                project_path=path,
            )
        return context

    def clear_cfd_export(self) -> None:
        """Detach recorded CFD evidence from subsequent model requests."""
        if self._busy:
            self.status.set("Finish the current request before clearing CFD evidence.")
            return
        self._cfd_export_dir = None
        self._cfd_project_key = None
        self.status.set("CFD export detached. Future AI questions use project diagnostics only.")

    def review_cfd_export(self) -> None:
        """Explicitly inspect an existing CFD export without any model request."""
        if self._busy:
            self.status.set("Finish the current request before changing CFD evidence.")
            return
        self._ensure_session()
        project_path = self._project_path_getter()
        if project_path is None:
            self._append(
                "CFD evidence unavailable",
                "Save this project and export matching recorded CFD evidence first.",
            )
            return
        source = filedialog.askopenfilename(
            parent=self,
            title="Select computed CFD export report.json",
            filetypes=[("CleanroomX CFD report", "report.json"), ("JSON", "*.json")],
        )
        if not source:
            return
        try:
            candidate = Path(source)
            if candidate.name != "report.json":
                raise ValueError("Select the CleanroomX exported report.json file.")
            report = bound_cfd_evidence(
                candidate.parent, project=self._project_getter(),
                project_path=project_path,
            )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._append("CFD evidence rejected", str(exc))
            self.status.set("CFD export not attached; no network request made.")
            return
        self._cfd_export_dir = candidate.parent
        self._cfd_project_key = self._project_key_getter()
        self._append("Recorded CFD export (offline)", format_cfd_evidence(report))
        self.status.set(
            "Matching CFD evidence loaded for read-only AI Q&A. "
            "Engineering release remains HOLD."
        )

    def handoff_cfd_case(self) -> None:
        """Explicit two-stage handoff; opening a workspace never starts OpenFOAM."""
        if self._busy:
            self.status.set("Finish the model request before opening CFD workspace.")
            return
        if self._open_cfd_case is None:
            self.status.set("This GUI does not provide a CFD workspace handoff.")
            return
        try:
            self._ensure_session()
            project_path = self._project_path_getter()
            if project_path is None:
                raise ValueError("Save the project before choosing a generated CFD case.")
            key = self._project_key_getter()
            candidate = filedialog.askdirectory(
                parent=self, title="Select a generated, not-yet-executed OpenFOAM case",
            )
            if not candidate:
                return
            preview = prepare_cfd_run_handoff(
                candidate, project=self._project_getter(), project_path=project_path,
            )
            self._append("CFD case handoff preview (offline)", render_cfd_run_handoff(preview))
            self.status.set("CFD case verified for handoff. No solver started.")
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            self._append("CFD case handoff rejected", str(exc))
            self.status.set("No CFD workspace opened; no solver started.")
            return
        if not messagebox.askyesno(
            "Open existing CFD workspace?",
            "The preview matches the saved project and has no recorded solver run.\n\n"
            "Open the existing Multiroom CFD workspace for independent review?\n"
            "This action does NOT run OpenFOAM. Running the solver requires a "
            "separate deliberate action in that workspace.",
            parent=self,
        ):
            self.status.set("CFD handoff not confirmed. No solver started.")
            return
        try:
            if key != self._project_key_getter():
                raise ValueError("Project changed while awaiting CFD handoff confirmation")
            current_project_path = self._project_path_getter()
            if current_project_path is None:
                raise ValueError("Current project is not saved")
            approved_case = revalidate_cfd_run_handoff(
                preview, project=self._project_getter(), project_path=current_project_path,
            )
            self._open_cfd_case(approved_case)
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            self._append("CFD case handoff rejected after confirmation", str(exc))
            self.status.set("CFD handoff failed safely. No solver started by AI.")
            return
        self.status.set(
            "Existing CFD workspace opened. Solver NOT started by AI; "
            "use separate Run control only after independent review."
        )

    def review_project(self) -> None:
        try:
            self._ensure_session()
            context = self._snapshot()
            self._append("Local project diagnostics", format_offline_review(context))
            self.status.set("Offline review complete. No network request made.")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._append("Offline review failed", str(exc))
            self.status.set("Could not obtain a canonical diagnostic snapshot.")

    def review_action_plan(self) -> None:
        try:
            self._ensure_session()
            context = self._snapshot()
            plan = build_assistant_action_plan(context)
            self._append("Engineering next actions (not executed)", render_assistant_action_plan(plan))
            if "cfd_evidence" in context:
                cfd_plan = build_cfd_followup_plan(context["cfd_evidence"])
                self._append(
                    "Recorded CFD next checks (not executed)",
                    render_cfd_followup_plan(cfd_plan),
                )
            self.status.set("Offline action plan proposed. No network or design changes.")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._append("Action plan unavailable", str(exc))
            self.status.set("Could not build a traceable engineering action plan.")

    def review_specialist(self) -> None:
        """Review one evidence-bound engineering specialty without network use."""
        if self._busy:
            self.status.set("Finish the current request before reviewing evidence.")
            return
        try:
            self._ensure_session()
            review = build_specialist_review(
                self._snapshot(), focus=self.review_focus.get(),
            )
            self._append("Offline specialist review", render_specialist_review(review))
            self.status.set("Specialist review complete. No model, network or design edits.")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._append("Specialist review unavailable", str(exc))
            self.status.set("Could not review this specialty from canonical evidence.")

    def _on_return(self, _event: tk.Event) -> None:
        self.ask_ai()

    def ask_ai(self) -> None:
        if self._busy:
            return
        question = self.question.get().strip()
        try:
            self._ensure_session()
            cfg = AssistantConfiguration.from_environment()
            if not question or len(question) > 4000:
                raise ValueError("Enter a question of at most 4000 characters.")
            context = self._snapshot()
            key = self._active_project_key
            chat = self._conversations.require_session(self._session_id, key)
            evidence_sha = (
                context["cfd_evidence"]["report_sha256"]
                if "cfd_evidence" in context else None
            )
            history = self._conversations.model_history(
                chat.id, key,
                snapshot_sha256=context["project"]["in_memory_sha256"],
                cfd_report_sha256=evidence_sha,
            )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._append("Assistant setup", str(exc))
            return

        self._busy = True
        self.ask_button.configure(state="disabled")
        self._append("You (pending)", question)
        self.question.delete(0, "end")
        snapshot_sha = context["project"]["in_memory_sha256"]
        focus = self.review_focus.get()
        self.status.set(
            "Asking " + cfg.provider + " (" + cfg.model + "), snapshot " + snapshot_sha[:12]
            + ", focus: " + focus
        )

        def worker() -> None:
            payload = {
                "project_key": key,
                "session_id": chat.id,
                "revision": chat.revision,
                "instance_id": chat.instance_id,
                "snapshot_sha": snapshot_sha,
                "cfd_report_sha256": evidence_sha,
                "provider": cfg.provider,
                "model": cfg.model,
                "question": question,
            }
            try:
                payload["answer"] = ask_model(
                    question, context, configuration=cfg, history=history,
                    focus=focus,
                )
                payload["kind"] = "ok"
            except Exception as exc:
                payload["kind"] = "error"
                payload["error"] = str(exc)
            self._pending.put(payload)

        threading.Thread(target=worker, name="CleanroomX-AI", daemon=True).start()

    def _poll(self) -> None:
        if self._closed:
            return
        # A Save As / Open Project / New Project can change the active binding
        # while the assistant is open. Do not show another project's transcript.
        if self._project_key_getter() != self._active_project_key:
            self._ensure_session()
        while True:
            try:
                response = self._pending.get_nowait()
            except Empty:
                break
            self._busy = False
            self.ask_button.configure(state="normal")
            same_view = (
                response["project_key"] == self._project_key_getter()
                and response["session_id"] == self._session_id
            )
            if response["kind"] == "error":
                if same_view:
                    self._redraw()  # Discard uncommitted pending question.
                    self._append("AI request failed", response["error"])
                self.status.set("Model request failed. No chat or project changes made.")
                continue
            try:
                stale = (
                    response["project_key"] != self._project_key_getter()
                    or response["snapshot_sha"]
                    != project_snapshot_sha256(self._project_getter())
                )
                if response["cfd_report_sha256"] is not None:
                    try:
                        current = self._snapshot()
                        current_sha = current["cfd_evidence"]["report_sha256"]
                    except (OSError, ValueError, KeyError, TypeError):
                        current_sha = None
                    if current_sha != response["cfd_report_sha256"]:
                        stale = True
                self._conversations.commit_exchange(
                    response["session_id"], response["project_key"],
                    question=response["question"], answer=response["answer"],
                    snapshot_sha256=response["snapshot_sha"],
                    expected_revision=response["revision"],
                    expected_instance_id=response["instance_id"],
                    provider=response["provider"], model=response["model"],
                    stale_project=stale,
                    cfd_report_sha256=response["cfd_report_sha256"],
                )
            except (KeyError, ValueError, RuntimeError) as exc:
                if same_view:
                    self._redraw()
                    self._append("AI conversation conflict", str(exc))
                self.status.set("AI response discarded: conversation changed.")
                continue
            if same_view:
                self._redraw()
                if stale:
                    self._append(
                        "Snapshot warning",
                        "Project or CFD evidence changed. This answer used an older snapshot.",
                    )
                self._refresh_sessions()
            self.status.set("AI suggestion recorded in local chat; project unchanged.")
        self.after(125, self._poll)

    def _close(self) -> None:
        self._closed = True
        self.destroy()
        if self._on_close is not None:
            self._on_close()
