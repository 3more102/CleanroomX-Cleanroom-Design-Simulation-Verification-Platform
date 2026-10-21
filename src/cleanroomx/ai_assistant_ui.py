"""Small read-only AI workspace for the existing CleanroomX Tk desktop."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from queue import Empty, Queue
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk

from .ai_assistant import (
    AssistantConfiguration,
    ask_model,
    build_assistant_context,
    format_offline_review,
    project_snapshot_sha256,
)
from .project import ProjectDocument


class AssistantWindow(tk.Toplevel):
    """No project mutations. All model I/O runs outside Tk's UI thread."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        project_getter: Callable[[], ProjectDocument],
        base_dir_getter: Callable[[], str | Path | None],
        on_close: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("CleanroomX | AI Engineering Assistant")
        self.geometry("850x630")
        self.minsize(620, 430)
        self.transient(parent)
        self._project_getter = project_getter
        self._base_dir_getter = base_dir_getter
        self._on_close = on_close
        self._pending: Queue[tuple[str, str, str]] = Queue()
        self._busy = False

        content = ttk.Frame(self, padding=12)
        content.pack(fill="both", expand=True)
        ttk.Label(
            content,
            text="AI Engineering Assistant | Read-only",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            content,
            text=(
                "Review project diagnostics locally or ask a configured model. "
                "No design edits, CFD runs, or standards claims are performed."
            ),
            wraplength=790,
            justify="left",
        ).pack(anchor="w", pady=(4, 10))

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
        self.ask_button = ttk.Button(
            buttons, text="Ask AI", command=self.ask_ai
        )
        self.ask_button.pack(side="left", padx=8)
        self.status = tk.StringVar(
            value="AI defaults to local Ollama. Cloud use requires explicit environment opt-in."
        )
        ttk.Label(content, textvariable=self.status, wraplength=790).pack(anchor="w")

        self._append("CleanroomX", (
            "Only the bounded project name, analysis index, diagnostic findings "
            "and verification summaries are sent to a selected model. "
            "Raw geometry, CFD fields and project metadata are not included. "
            "The offline review does not send data."
        ))
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(125, self._poll)

    def _append(self, speaker: str, text: str) -> None:
        self.transcript.configure(state="normal")
        self.transcript.insert("end", speaker + "\n" + text + "\n\n")
        self.transcript.configure(state="disabled")
        self.transcript.see("end")

    def _snapshot(self) -> dict:
        return build_assistant_context(
            self._project_getter(), base_dir=self._base_dir_getter()
        )

    def review_project(self) -> None:
        try:
            context = self._snapshot()
            self._append("Project diagnostics", format_offline_review(context))
            self.status.set("Offline review complete. No model request made.")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._append("Review failed", str(exc))
            self.status.set("Could not obtain an authoritative project diagnostic snapshot.")

    def _on_return(self, _event: tk.Event) -> None:
        self.ask_ai()

    def ask_ai(self) -> None:
        if self._busy:
            return
        question = self.question.get().strip()
        try:
            configuration = AssistantConfiguration.from_environment()
            if not question:
                raise ValueError("Enter a question first.")
            context = self._snapshot()
            if len(question) > 4000:
                raise ValueError("Question exceeds the 4000-character limit.")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._append("Assistant setup", str(exc))
            return

        self._busy = True
        self.ask_button.configure(state="disabled")
        self._append("You", question)
        self.question.delete(0, "end")
        self.status.set(
            "Asking " + configuration.provider + " (" + configuration.model
            + ") using project snapshot " + context["project"]["in_memory_sha256"][:12]
        )

        def worker() -> None:
            try:
                answer = ask_model(question, context, configuration=configuration)
                self._pending.put(("ok", context["project"]["in_memory_sha256"], answer))
            except Exception as exc:
                # The backend reports sanitized endpoint errors, never key contents.
                self._pending.put(("error", context["project"]["in_memory_sha256"], str(exc)))

        threading.Thread(target=worker, name="CleanroomX-AI", daemon=True).start()

    def _poll(self) -> None:
        try:
            kind, snapshot_sha, message = self._pending.get_nowait()
        except Empty:
            self.after(125, self._poll)
            return
        self._busy = False
        self.ask_button.configure(state="normal")
        if kind == "error":
            self._append("AI request failed", message)
            self.status.set("Model request failed; project unchanged.")
        else:
            try:
                current_sha = project_snapshot_sha256(self._project_getter())
            except (ValueError, TypeError) as exc:
                current_sha = ""
            if current_sha != snapshot_sha:
                self._append(
                    "Snapshot warning",
                    "Project changed after the request. The response refers to an older snapshot."
                )
            self._append("AI suggestion (not verified engineering evidence)", message)
            self.status.set("Model response received. No changes applied.")
        self.after(125, self._poll)

    def _close(self) -> None:
        self.destroy()
        if self._on_close is not None:
            self._on_close()
