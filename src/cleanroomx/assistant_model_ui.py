"""Opt-in, source-revision-checked model dialog for the existing project reviewer.

Opening this window does not contact a model. Tk state belongs to the GUI
thread; the model call runs on one worker, with bounded polling and no
automatic persistence of project data, prompts or model answers.
"""
from __future__ import annotations

from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import ttk

from .assistant_model_gateway import ask_model_about_saved_project
from .gui_windowing import fit_window_to_display


class ModelAssistantWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc, project_path: str | Path):
        super().__init__(parent)
        self.source = Path(project_path)
        self.title("CleanroomX | Optional Model Assistant")
        self.transient(parent)
        fit_window_to_display(
            self, preferred_width=880, preferred_height=585,
            minimum_width=640, minimum_height=420,
        )
        self._messages: Queue[tuple[str, str, str]] = Queue()
        self._after_id: str | None = None
        self._busy = False
        self._closed = False
        self.status_var = tk.StringVar(
            value="Ready. No network request has been made."
        )

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame, text="Optional AI suggestions — NOT engineering evidence",
        ).pack(anchor="w")
        ttk.Label(
            frame, wraplength=790, justify="left",
            text=(
                "Only a bounded excerpt of canonical saved-project diagnostic "
                "rules and the question is transmitted after you press Ask. "
                "Local Ollama is the default; OpenAI cloud requires explicit "
                "environment opt-in. No CFD fields, source paths or geometry "
                "are sent. No project edits or solver commands can be made."
            ),
        ).pack(fill="x", pady=(6, 10))
        ttk.Label(frame, text="Question (up to 1,200 characters)").pack(anchor="w")
        self.question = tk.Text(frame, height=4, wrap="word")
        self.question.pack(fill="x", pady=(3, 8))
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x")
        self.ask_button = ttk.Button(
            toolbar, text="Ask configured model (opt-in)", command=self.ask
        )
        self.ask_button.pack(side="left")
        ttk.Button(toolbar, text="Close", command=self._close).pack(side="right")
        ttk.Label(frame, textvariable=self.status_var, wraplength=790).pack(
            anchor="w", pady=(8, 6)
        )
        ttk.Label(
            frame, text="Unverified model suggestion (never an approval)"
        ).pack(anchor="w")
        view = ttk.Frame(frame)
        view.pack(fill="both", expand=True)
        self.output = tk.Text(view, height=11, wrap="word", state="disabled")
        scrollbar = ttk.Scrollbar(view, orient="vertical", command=self.output.yview)
        self.output.configure(yscrollcommand=scrollbar.set)
        self.output.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _set_output(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def ask(self) -> None:
        if self._busy or self._closed:
            return
        question = self.question.get("1.0", "end-1c").strip()
        if not question or len(question) > 1200:
            self.status_var.set("Enter a question of at most 1,200 characters.")
            return
        self._busy = True
        self.ask_button.configure(state="disabled")
        self._set_output("Request in progress. No model response is engineering evidence.")
        self.status_var.set("Checking saved-source diagnostics and model configuration…")
        Thread(target=self._worker, args=(question,), daemon=True).start()
        self._poll()

    def _worker(self, question: str) -> None:
        try:
            answer, digest = ask_model_about_saved_project(self.source, question)
            self._messages.put(("result", answer, digest))
        except Exception as exc:
            # Do not move Tk work into the network/diagnostic thread.
            # Never show secret-bearing exception representations or API headers.
            self._messages.put((
                "error",
                f"{type(exc).__name__}: {exc}" if isinstance(exc, (ValueError, RuntimeError, OSError))
                else "Unexpected model request failure.",
                "",
            ))

    def _poll(self) -> None:
        self._after_id = None
        if self._closed:
            return
        try:
            state, message, digest = self._messages.get_nowait()
        except Empty:
            if self._busy:
                self._after_id = self.after(100, self._poll)
            return
        self._busy = False
        self.ask_button.configure(state="normal")
        if state == "result":
            self._set_output(
                "UNVERIFIED AI SUGGESTION — NOT CFD/ENGINEERING EVIDENCE\n\n"
                + message
            )
            self.status_var.set(
                "Response tied to saved project SHA-256 "
                + digest[:16] + "…; never use as an acceptance verdict."
            )
        else:
            self._set_output("No trusted model response was published.")
            self.status_var.set("Request refused: " + message)

    def _close(self) -> None:
        self._closed = True
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
        self.destroy()
