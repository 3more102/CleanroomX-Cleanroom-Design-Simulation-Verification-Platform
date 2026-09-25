from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .autosave import (
    RecoveryCandidate,
    RecoveryScan,
    RecoveryScanIssue,
    discard_recovery_artifact,
    load_recovery_artifact,
    quarantine_recovery_artifact,
)


_RELATION_LABELS = {
    "unsaved": "Unsaved project",
    "source_missing": "Original file missing",
    "source_unchanged": "Original unchanged",
    "source_changed": "Original changed",
    "source_newer": "Original is newer",
}

_INTEGRITY_LABELS = {
    "verified": "Verified SHA-256",
    "legacy_unverified": "Legacy / unverified",
}


def recovery_relation_label(candidate: RecoveryCandidate) -> str:
    return _RELATION_LABELS.get(candidate.source_relation, candidate.source_relation)


def recovery_integrity_label(candidate: RecoveryCandidate) -> str:
    return _INTEGRITY_LABELS.get(candidate.integrity_status, candidate.integrity_status)


def recovery_safety_message(candidate: RecoveryCandidate) -> str:
    if candidate.source_relation == "source_newer":
        return (
            "The original project is newer than this recovery. Restoring opens a "
            "separate unsaved copy and never overwrites the newer file."
        )
    if candidate.source_relation == "source_changed":
        return (
            "The original project differs from the file fingerprint captured by this "
            "recovery. Restoring opens a separate unsaved copy so both versions are preserved."
        )
    if candidate.source_relation == "source_missing":
        return (
            "The original project file is missing. Restoring opens an unsaved copy; "
            "use Save Project As to choose a destination."
        )
    if candidate.source_relation == "source_unchanged":
        return (
            "The original file still matches the fingerprint captured by this recovery. "
            "Restoring still opens a separate unsaved copy."
        )
    return (
        "This recovery came from a project that had not been explicitly saved. "
        "Restoring opens it as an unsaved project."
    )


@dataclass(frozen=True)
class RecoveryInspection:
    project_name: str
    project_identity: str
    saved_at_utc: str
    source_path: str
    source_status: str
    application_version: str
    analysis_count: int
    analysis_names: tuple[str, ...]
    editor_analysis_id: str | None
    editor_json_valid: bool | None
    editor_text: str
    integrity_status: str = "Legacy / unverified"


def inspect_recovery(candidate: RecoveryCandidate) -> RecoveryInspection:
    payload = load_recovery_artifact(candidate.path)
    snapshot = payload["snapshot"]
    project = snapshot.get("project", {})
    project_block = project.get("project", {}) if isinstance(project, dict) else {}
    analyses = project.get("analyses", []) if isinstance(project, dict) else []
    if not isinstance(analyses, list):
        analyses = []
    names: list[str] = []
    for item in analyses:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        kind = item.get("kind")
        if isinstance(name, str) and isinstance(kind, str):
            names.append(f"{name} [{kind}]")
        elif isinstance(name, str):
            names.append(name)

    ui_state = snapshot.get("ui_state", {})
    if not isinstance(ui_state, dict):
        ui_state = {}
    editor_id = ui_state.get("editor_analysis_id")
    if not isinstance(editor_id, str):
        editor_id = None
    editor_valid = ui_state.get("editor_json_valid")
    if not isinstance(editor_valid, bool):
        editor_valid = None
    editor_text = ui_state.get("editor_text", "")
    if not isinstance(editor_text, str):
        editor_text = ""

    project_name = project_block.get("name", candidate.project_name)
    if not isinstance(project_name, str) or not project_name:
        project_name = candidate.project_name
    source_path = str(candidate.source_path) if candidate.source_path else "Not yet saved"
    return RecoveryInspection(
        project_name=project_name,
        project_identity=candidate.project_identity,
        saved_at_utc=candidate.saved_at_utc,
        source_path=source_path,
        source_status=recovery_relation_label(candidate),
        integrity_status=recovery_integrity_label(candidate),
        application_version=str(payload.get("application_version", "unknown")),
        analysis_count=len(analyses),
        analysis_names=tuple(names),
        editor_analysis_id=editor_id,
        editor_json_valid=editor_valid,
        editor_text=editor_text,
    )


class RecoveryInspectDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, candidate: RecoveryCandidate):
        super().__init__(parent)
        self.title("Inspect recovery")
        self.geometry("760x580")
        self.minsize(620, 430)
        self.transient(parent)
        self.grab_set()

        inspection = inspect_recovery(candidate)

        header = ttk.Frame(self, padding=12)
        header.pack(fill="x")
        ttk.Label(
            header,
            text=inspection.project_name,
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            header,
            text=recovery_safety_message(candidate),
            wraplength=710,
        ).pack(anchor="w", pady=(6, 0))

        details = ttk.LabelFrame(self, text="Recovery evidence", padding=10)
        details.pack(fill="x", padx=12, pady=(0, 10))
        rows = (
            ("Project identity", inspection.project_identity),
            ("Recovered at", inspection.saved_at_utc),
            ("Source status", inspection.source_status),
            ("Recovery integrity", inspection.integrity_status),
            ("Original project", inspection.source_path),
            ("CleanroomX version", inspection.application_version),
            ("Analyses", str(inspection.analysis_count)),
            (
                "Editor draft",
                (
                    "Valid JSON"
                    if inspection.editor_json_valid is True
                    else "Invalid/incomplete JSON preserved"
                    if inspection.editor_json_valid is False
                    else "No editor validity evidence"
                ),
            ),
        )
        for row, (label, value) in enumerate(rows):
            ttk.Label(details, text=label + ":", font=("TkDefaultFont", 9, "bold")).grid(
                row=row, column=0, sticky="nw", padx=(0, 8), pady=2
            )
            ttk.Label(details, text=value, wraplength=540).grid(
                row=row, column=1, sticky="nw", pady=2
            )
        details.columnconfigure(1, weight=1)

        analyses_frame = ttk.LabelFrame(self, text="Recovered analyses", padding=8)
        analyses_frame.pack(fill="x", padx=12, pady=(0, 10))
        analyses_text = ", ".join(inspection.analysis_names) or "No analyses"
        ttk.Label(analyses_frame, text=analyses_text, wraplength=700).pack(anchor="w")

        draft_frame = ttk.LabelFrame(self, text="Recovered editor draft", padding=8)
        draft_frame.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        draft = tk.Text(draft_frame, wrap="none", height=10)
        yscroll = ttk.Scrollbar(draft_frame, orient="vertical", command=draft.yview)
        xscroll = ttk.Scrollbar(draft_frame, orient="horizontal", command=draft.xview)
        draft.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        draft.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        draft_frame.rowconfigure(0, weight=1)
        draft_frame.columnconfigure(0, weight=1)
        draft.insert("1.0", inspection.editor_text or "(No raw editor draft captured)")
        draft.configure(state="disabled")

        ttk.Button(self, text="Close", command=self.destroy).pack(
            side="right", padx=12, pady=(0, 12)
        )


class RecoveryCenter(tk.Toplevel):
    """Startup recovery chooser.

    Restore always returns an artifact path to the application. The application
    opens it as an unsaved copy; this dialog never writes an explicit project file.
    """

    def __init__(self, parent: tk.Misc, scan: RecoveryScan):
        super().__init__(parent)
        self.title("Recover unsaved CleanroomX work")
        self.geometry("980x520")
        self.minsize(780, 400)
        self.transient(parent)
        self.grab_set()
        self.result: Path | None = None
        self._candidates = {str(item.path): item for item in scan.candidates}
        self._issues: list[RecoveryScanIssue] = list(scan.issues)

        header = ttk.Frame(self, padding=(12, 12, 12, 6))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Recover unsaved work",
            font=("TkDefaultFont", 13, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            header,
            text=(
                "CleanroomX found recovery data from an earlier session. "
                "Restoring always opens a separate unsaved copy; original project files "
                "are never overwritten automatically."
            ),
            wraplength=920,
        ).pack(anchor="w", pady=(4, 0))

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=8)
        self.tree = ttk.Treeview(
            frame,
            columns=("time", "state", "integrity", "source"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Project")
        self.tree.heading("time", text="Recovery timestamp (UTC)")
        self.tree.heading("state", text="Original project")
        self.tree.heading("integrity", text="Integrity")
        self.tree.heading("source", text="Source path")
        self.tree.column("#0", width=210, stretch=False)
        self.tree.column("time", width=205, stretch=False)
        self.tree.column("state", width=150, stretch=False)
        self.tree.column("integrity", width=135, stretch=False)
        self.tree.column("source", width=300, stretch=True)
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        for candidate in scan.candidates:
            self.tree.insert(
                "",
                "end",
                iid=str(candidate.path),
                text=candidate.project_name,
                values=(
                    candidate.saved_at_utc,
                    recovery_relation_label(candidate),
                    recovery_integrity_label(candidate),
                    str(candidate.source_path) if candidate.source_path else "Not yet saved",
                ),
            )

        self.message_var = tk.StringVar()
        message = ttk.Label(
            self,
            textvariable=self.message_var,
            wraplength=940,
            anchor="w",
            padding=(12, 0, 12, 0),
        )
        message.pack(fill="x")

        self.issue_var = tk.StringVar(self)
        self.issue_label = ttk.Label(
            self,
            textvariable=self.issue_var,
            wraplength=940,
            padding=(12, 6, 12, 0),
        )
        self.issue_label.pack(fill="x")
        self._refresh_issue_summary()

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=12)
        ttk.Button(buttons, text="Continue without restoring", command=self.destroy).pack(
            side="right"
        )
        self.restore_button = ttk.Button(
            buttons,
            text="Restore as Unsaved Copy",
            command=self._restore,
        )
        self.restore_button.pack(side="right", padx=(0, 6))
        self.discard_button = ttk.Button(
            buttons, text="Discard Recovery", command=self._discard
        )
        self.discard_button.pack(side="left")
        self.inspect_button = ttk.Button(
            buttons, text="Inspect…", command=self._inspect
        )
        self.inspect_button.pack(side="left", padx=(6, 0))
        self.quarantine_button = ttk.Button(
            buttons,
            text="Quarantine Invalid Artifacts…",
            command=self._quarantine_issues,
        )
        self.quarantine_button.pack(side="left", padx=(6, 0))
        self._refresh_quarantine_button()

        self.tree.bind("<<TreeviewSelect>>", lambda event: self._selection_changed())
        self.tree.bind("<Double-1>", lambda event: self._inspect())
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
        self._selection_changed()

    def _selected_candidate(self) -> RecoveryCandidate | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._candidates.get(selection[0])

    def _refresh_issue_summary(self) -> None:
        if not self._issues:
            self.issue_var.set("")
            return
        issue_lines = "; ".join(
            f"{issue.path.name}: {issue.error}" for issue in self._issues[:3]
        )
        suffix = f" (+{len(self._issues) - 3} more)" if len(self._issues) > 3 else ""
        self.issue_var.set(
            f"{len(self._issues)} recovery artifact(s) could not be read and were "
            f"preserved. They can be moved to the recovery quarantine without "
            f"changing their bytes: {issue_lines}{suffix}"
        )

    def _refresh_quarantine_button(self) -> None:
        if hasattr(self, "quarantine_button"):
            self.quarantine_button.configure(
                state="normal" if self._issues else "disabled"
            )

    def _selection_changed(self) -> None:
        candidate = self._selected_candidate()
        state = "normal" if candidate is not None else "disabled"
        self.restore_button.configure(state=state)
        self.discard_button.configure(state=state)
        self.inspect_button.configure(state=state)
        self.message_var.set(
            recovery_safety_message(candidate) if candidate is not None else ""
        )

    def _inspect(self) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            return
        try:
            dialog = RecoveryInspectDialog(self, candidate)
            self.wait_window(dialog)
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "Recovery inspection failed",
                str(exc),
                parent=self,
            )

    def _restore(self) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            return
        self.result = candidate.path
        self.destroy()

    def _quarantine_issues(self) -> None:
        if not self._issues:
            return
        count = len(self._issues)
        if not messagebox.askyesno(
            "Quarantine invalid recovery artifacts",
            (
                f"Move {count} unreadable recovery artifact(s) into the private "
                "recovery quarantine?\n\n"
                "The original bytes are preserved with SHA-256 audit metadata. "
                "Quarantined artifacts are removed from normal startup recovery scans "
                "but are not treated as valid projects."
            ),
            parent=self,
        ):
            return

        remaining: list[RecoveryScanIssue] = []
        quarantined = 0
        failures: list[str] = []
        for issue in self._issues:
            try:
                quarantine_recovery_artifact(
                    issue.path,
                    recovery_dir=issue.path.parent,
                    reason=issue.error,
                )
            except (OSError, ValueError) as exc:
                remaining.append(issue)
                failures.append(f"{issue.path.name}: {exc}")
            else:
                quarantined += 1

        self._issues = remaining
        self._refresh_issue_summary()
        self._refresh_quarantine_button()
        if failures:
            messagebox.showerror(
                "Quarantine incomplete",
                (
                    f"Quarantined {quarantined} artifact(s), but "
                    f"{len(failures)} could not be moved:\n\n"
                    + "\n".join(failures[:5])
                ),
                parent=self,
            )
            return
        self.message_var.set(
            f"Quarantined {quarantined} invalid recovery artifact(s); "
            "their original bytes and audit metadata were preserved."
        )

    def _discard(self) -> None:
        candidate = self._selected_candidate()
        if candidate is None:
            return
        if not messagebox.askyesno(
            "Discard recovery",
            (
                f"Discard this recovery for {candidate.project_name!r}?\n\n"
                "This deletes only the selected recovery artifact. "
                "The original project file is not changed."
            ),
            parent=self,
        ):
            return
        try:
            discard_recovery_artifact(
                candidate.path,
                recovery_dir=candidate.path.parent,
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("Discard failed", str(exc), parent=self)
            return
        key = str(candidate.path)
        self._candidates.pop(key, None)
        if self.tree.exists(key):
            self.tree.delete(key)
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self.message_var.set("Selected recovery discarded.")
        else:
            self.message_var.set("No recoverable sessions remain.")
        self._selection_changed()
