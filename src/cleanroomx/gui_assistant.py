"""Desktop read-only project evidence assistant dialog.

Only the worker thread touches engineering code; all Tk operations stay on
the main GUI thread. The caller must require the opened project to be saved.
"""
from __future__ import annotations

from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import ttk

from .assistant_review import build_assistant_review, markdown_assistant_review
from .gui_windowing import fit_window_to_display


class ProjectAssistantDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, project_path: str | Path):
        super().__init__(parent)
        self.title("CleanroomX Project Assistant — Evidence Review")
        self.transient(parent)
        fit_window_to_display(
            self, preferred_width=1080, preferred_height=720,
            minimum_width=760, minimum_height=490,
        )
        self.source = Path(project_path)
        self._messages: Queue[tuple[str, object]] = Queue()
        self._after_id: str | None = None
        self._busy = False
        self._review: dict | None = None
        self._markdown = ""
        self.status_var = tk.StringVar(value="Ready to review the saved project.")

        header = ttk.Frame(self, padding=(12, 10))
        header.pack(fill="x")
        ttk.Label(
            header, text="Evidence-first Project Assistant",
            style="CX.Section.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            header,
            text="Read-only project checks. No AI model, solver execution or certification.",
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            header, textvariable=self.status_var, wraplength=930,
        ).pack(anchor="w", pady=(7, 0))

        body = ttk.Frame(self, padding=(12, 0, 12, 8))
        body.pack(fill="both", expand=True)
        list_frame = ttk.Frame(body)
        list_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            list_frame, columns=("severity", "rule", "action"),
            show="headings", height=9,
        )
        self.tree.heading("severity", text="Severity")
        self.tree.heading("rule", text="Canonical rule")
        self.tree.heading("action", text="Corrective action")
        self.tree.column("severity", width=90, stretch=False)
        self.tree.column("rule", width=260, stretch=False)
        self.tree.column("action", width=620, stretch=True)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        ttk.Label(
            body, text="Selected finding and source evidence",
        ).pack(anchor="w", pady=(9, 4))
        details = ttk.Frame(body)
        details.pack(fill="both", expand=True)
        self.details = tk.Text(details, height=10, wrap="word", state="disabled")
        detail_scroll = ttk.Scrollbar(details, orient="vertical", command=self.details.yview)
        self.details.configure(yscrollcommand=detail_scroll.set)
        self.details.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)

        buttons = ttk.Frame(self, padding=(12, 5, 12, 12))
        buttons.pack(fill="x")
        self.refresh_button = ttk.Button(
            buttons, text="Review saved project", command=self.refresh,
        )
        self.refresh_button.pack(side="left")
        self.copy_button = ttk.Button(
            buttons, text="Copy Markdown report",
            command=self.copy_report, state="disabled",
        )
        self.copy_button.pack(side="left", padx=8)
        ttk.Button(buttons, text="Close", command=self._close).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.refresh()

    def _set_details(self, content: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", content)
        self.details.configure(state="disabled")

    def refresh(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._review = None
        self._markdown = ""
        self.copy_button.configure(state="disabled")
        self.refresh_button.configure(state="disabled")
        self.status_var.set("Checking saved project revision and canonical diagnostics…")
        self._set_details("No result available until the source revision check completes.")
        for item in self.tree.get_children():
            self.tree.delete(item)
        Thread(target=self._review_worker, daemon=True).start()
        self._poll()

    def _review_worker(self) -> None:
        try:
            review = build_assistant_review(self.source, max_findings=50)
            self._messages.put(("result", review))
        except Exception as exc:
            # Do not create or manipulate Tk objects from the background thread.
            self._messages.put(("error", f"{type(exc).__name__}: {exc}"))

    def _poll(self) -> None:
        self._after_id = None
        try:
            state, payload = self._messages.get_nowait()
        except Empty:
            if self._busy:
                self._after_id = self.after(100, self._poll)
            return
        self._busy = False
        self.refresh_button.configure(state="normal")
        if state != "result":
            self.status_var.set("Review failed: " + str(payload))
            self._set_details(
                "The assistant refused to publish a review. Save or reload the project "
                "and inspect the error above; no verdict was produced."
            )
            return
        self._review = payload
        self._markdown = markdown_assistant_review(payload)
        self.copy_button.configure(state="normal")
        summary = payload["summary"]
        self.status_var.set(
            f"{payload['decision']}: {summary['error_count']} errors, "
            f"{summary['warning_count']} warnings, {summary['info_count']} information; "
            f"source SHA-256 {payload['source']['sha256'][:16]}… "
            "(not CFD or cleanroom certification)"
        )
        for i, finding in enumerate(payload["findings"]):
            self.tree.insert(
                "", "end", iid=str(i),
                values=(
                    finding["severity"], finding["rule"],
                    finding["suggested_action"],
                ),
            )
        if self.tree.get_children():
            self.tree.selection_set(self.tree.get_children()[0])
            self._show_selected()
        else:
            self._set_details(
                "No diagnostic findings. This is not evidence of CFD convergence, "
                "cleanroom compliance or engineering acceptance."
            )

    def _show_selected(self, event=None) -> None:
        if self._review is None or not self.tree.selection():
            return
        index = int(self.tree.selection()[0])
        finding = self._review["findings"][index]
        self._set_details(
            f"Evidence: {finding['evidence_ref']}\n"
            f"Rule: {finding['rule']}\n"
            f"Severity: {finding['severity']}\n"
            f"Finding: {finding['finding']}\n"
            f"Action: {finding['suggested_action']}\n"
            f"Source SHA-256: {self._review['source']['sha256']}\n"
        )

    def copy_report(self) -> None:
        if not self._markdown:
            return
        self.clipboard_clear()
        self.clipboard_append(self._markdown)
        self.status_var.set("Copied evidence-grounded Markdown review to clipboard.")

    def _close(self) -> None:
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
        self.destroy()
