from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from .autosave import (
    RecoveryCandidate,
    RecoveryScan,
    discard_recovery_artifact,
    load_recovery_artifact,
    quarantine_recovery_artifact,
)
from .recovery_diff import compare_recovery_to_source, format_recovery_comparison
from .gui_geometry import configure_toplevel_geometry


_RELATION_LABELS = {
    "unsaved": "Unsaved project",
    "source_missing": "Original file missing",
    "source_unchanged": "Original unchanged",
    "source_changed": "Original changed",
    "source_newer": "Original is newer",
    "source_oversized": "Original exceeds supported size limit",
    "source_unavailable": "Original could not be read",
}

_INTEGRITY_LABELS = {
    "verified": "Verified SHA-256",
    "legacy_unverified": "Legacy artifact — no embedded checksum",
}


def recovery_integrity_label(candidate: RecoveryCandidate) -> str:
    return _INTEGRITY_LABELS.get(candidate.integrity_status, candidate.integrity_status)


def recovery_relation_label(candidate: RecoveryCandidate) -> str:
    return _RELATION_LABELS.get(candidate.source_relation, candidate.source_relation)


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
    if candidate.source_relation == "source_oversized":
        return (
            "The original project exceeds the supported source fingerprint size limit. "
            "This recovery remains valid; restoring opens a separate unsaved copy and "
            "does not overwrite the original file."
        )
    if candidate.source_relation == "source_unavailable":
        return (
            "The original project could not be read reliably. This recovery remains "
            "valid; restoring opens a separate unsaved copy and does not overwrite "
            "the original file."
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
    integrity_status: str
    application_version: str
    analysis_count: int
    analysis_names: tuple[str, ...]
    editor_analysis_id: str | None
    editor_json_valid: bool | None
    editor_text: str
    source_comparison_summary: str
    source_comparison_details: tuple[str, ...]


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
    comparison = compare_recovery_to_source(candidate)
    comparison_summary, comparison_details = format_recovery_comparison(comparison)
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
        source_comparison_summary=comparison_summary,
        source_comparison_details=comparison_details,
    )


class RecoveryInspectDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, candidate: RecoveryCandidate):
        super().__init__(parent)
        self.title("Inspect recovery")
        configure_toplevel_geometry(
            self,
            width=820,
            height=700,
            min_width=680,
            min_height=500,
        )
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
            wraplength=770,
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
            ttk.Label(details, text=value, wraplength=590).grid(
                row=row, column=1, sticky="nw", pady=2
            )
        details.columnconfigure(1, weight=1)

        analyses_frame = ttk.LabelFrame(self, text="Recovered analyses", padding=8)
        analyses_frame.pack(fill="x", padx=12, pady=(0, 10))
        analyses_text = ", ".join(inspection.analysis_names) or "No analyses"
        ttk.Label(analyses_frame, text=analyses_text, wraplength=760).pack(anchor="w")

        comparison_frame = ttk.LabelFrame(
            self, text="Recovery vs current source", padding=8
        )
        comparison_frame.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Label(
            comparison_frame,
            text=inspection.source_comparison_summary,
            font=("TkDefaultFont", 9, "bold"),
            wraplength=760,
        ).pack(anchor="w")
        for line in inspection.source_comparison_details:
            ttk.Label(
                comparison_frame,
                text="• " + line,
                wraplength=750,
            ).pack(anchor="w", pady=(2, 0))

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
        configure_toplevel_geometry(
            self,
            width=980,
            height=520,
            min_width=780,
            min_height=400,
        )
        self.transient(parent)
        self.grab_set()
        self.result: Path | None = None
        self._candidates = {str(item.path): item for item in scan.candidates}
        self._issues = list(scan.issues)
        self.search_var = tk.StringVar()
        self.relation_var = tk.StringVar(value="All")
        self.integrity_var = tk.StringVar(value="All")
        self.count_var = tk.StringVar()

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

        filters = ttk.Frame(self)
        filters.pack(fill="x", padx=12, pady=(2, 6))
        ttk.Label(filters, text="Search").pack(side="left")
        self.search_entry = ttk.Entry(
            filters,
            textvariable=self.search_var,
            width=28,
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(4, 8))

        relation_values = sorted(
            {recovery_relation_label(item) for item in scan.candidates},
            key=str.casefold,
        )
        ttk.Label(filters, text="Source").pack(side="left")
        self.relation_combo = ttk.Combobox(
            filters,
            textvariable=self.relation_var,
            values=("All", *relation_values),
            state="readonly",
            width=20,
        )
        self.relation_combo.pack(side="left", padx=(4, 8))

        integrity_values = sorted(
            {recovery_integrity_label(item) for item in scan.candidates},
            key=str.casefold,
        )
        ttk.Label(filters, text="Integrity").pack(side="left")
        self.integrity_combo = ttk.Combobox(
            filters,
            textvariable=self.integrity_var,
            values=("All", *integrity_values),
            state="readonly",
            width=22,
        )
        self.integrity_combo.pack(side="left", padx=(4, 8))
        ttk.Button(filters, text="Clear", command=self._clear_filters).pack(side="left")
        ttk.Button(
            filters,
            text="Previous",
            command=lambda: self._select_relative(-1),
        ).pack(side="left", padx=(10, 2))
        ttk.Button(
            filters,
            text="Next",
            command=lambda: self._select_relative(1),
        ).pack(side="left", padx=2)
        ttk.Label(filters, textvariable=self.count_var).pack(side="right", padx=(12, 0))

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
        self.tree.heading("integrity", text="Recovery integrity")
        self.tree.heading("source", text="Source path")
        self.tree.column("#0", width=170, stretch=False)
        self.tree.column("time", width=185, stretch=False)
        self.tree.column("state", width=120, stretch=False)
        self.tree.column("integrity", width=170, stretch=False)
        self.tree.column("source", width=285, stretch=True)
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")


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
        ttk.Label(
            self,
            textvariable=self.issue_var,
            wraplength=940,
            padding=(12, 6, 12, 0),
        ).pack(fill="x")
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

        self.search_var.trace_add("write", lambda *_: self._populate_candidates())
        self.relation_var.trace_add("write", lambda *_: self._populate_candidates())
        self.integrity_var.trace_add("write", lambda *_: self._populate_candidates())
        self.tree.bind("<<TreeviewSelect>>", lambda event: self._selection_changed())
        self.tree.bind("<Double-1>", lambda event: self._inspect())
        self.tree.bind("<Return>", lambda event: self._inspect())
        self.tree.bind("<F4>", lambda event: self._select_relative(1))
        self.tree.bind("<Shift-F4>", lambda event: self._select_relative(-1))
        self.bind("<Control-f>", lambda event: self.search_entry.focus_set())
        self.bind("<Escape>", lambda event: self.destroy())
        self._populate_candidates()

    def _filtered_candidates(self) -> list[RecoveryCandidate]:
        query = self.search_var.get().strip().casefold()
        relation = self.relation_var.get().strip().casefold()
        integrity = self.integrity_var.get().strip().casefold()
        visible: list[RecoveryCandidate] = []
        for candidate in self._candidates.values():
            relation_text = recovery_relation_label(candidate)
            integrity_text = recovery_integrity_label(candidate)
            if relation and relation != "all" and relation_text.casefold() != relation:
                continue
            if integrity and integrity != "all" and integrity_text.casefold() != integrity:
                continue
            if query:
                haystack = " ".join(
                    (
                        candidate.project_name,
                        candidate.saved_at_utc,
                        candidate.project_identity,
                        str(candidate.path),
                        str(candidate.source_path or ""),
                        relation_text,
                        integrity_text,
                    )
                ).casefold()
                if query not in haystack:
                    continue
            visible.append(candidate)
        visible.sort(
            key=lambda item: (item.saved_at_utc, item.project_name.casefold()),
            reverse=True,
        )
        return visible

    def _populate_candidates(self) -> None:
        selection = self.tree.selection()
        selected_path = selection[0] if selection else None
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        visible = self._filtered_candidates()
        for candidate in visible:
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

        self.count_var.set(
            f"{len(visible)} of {len(self._candidates)} recoverable sessions"
        )
        children = self.tree.get_children()
        target = (
            selected_path
            if selected_path is not None and self.tree.exists(selected_path)
            else children[0]
            if children
            else None
        )
        if target is not None:
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
        self._selection_changed()

    def _clear_filters(self) -> None:
        self.search_var.set("")
        self.relation_var.set("All")
        self.integrity_var.set("All")
        self.search_entry.focus_set()

    def _select_relative(self, step: int):
        children = list(self.tree.get_children())
        if not children:
            return "break"
        selection = self.tree.selection()
        if selection and selection[0] in children:
            index = children.index(selection[0])
            target = children[(index + step) % len(children)]
        else:
            target = children[0 if step >= 0 else -1]
        self.tree.selection_set(target)
        self.tree.focus(target)
        self.tree.see(target)
        self._selection_changed()
        return "break"

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
            f"{len(self._issues)} invalid recovery artifact(s) were preserved. "
            f"They can be quarantined without changing their suspect bytes: "
            f"{issue_lines}{suffix}"
        )

    def _refresh_quarantine_button(self) -> None:
        if hasattr(self, "quarantine_button"):
            self.quarantine_button.configure(
                state="normal" if self._issues else "disabled"
            )

    def _quarantine_issues(self) -> None:
        if not self._issues:
            return
        if not messagebox.askyesno(
            "Quarantine invalid recovery artifacts",
            (
                f"Move {len(self._issues)} invalid recovery artifact(s) into the "
                "private recovery quarantine?\n\nOriginal bytes are preserved "
                "with SHA-256, size, reason, and timestamp audit metadata."
            ),
            parent=self,
        ):
            return
        remaining = []
        failures: list[str] = []
        quarantined = 0
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
                f"Quarantined {quarantined}; {len(failures)} failed:\n\n"
                + "\n".join(failures[:5]),
                parent=self,
            )
        else:
            self.message_var.set(
                f"Quarantined {quarantined} invalid recovery artifact(s)."
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
        self._populate_candidates()
        if self._candidates:
            self.message_var.set("Selected recovery discarded.")
        else:
            self.message_var.set("No recoverable sessions remain.")
