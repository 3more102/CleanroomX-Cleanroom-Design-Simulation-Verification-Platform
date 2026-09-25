from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from .autosave import (
    RecoveryCandidate,
    RecoveryScan,
    discard_recovery_artifact,
    load_recovery_artifact,
)
from .project import load_project_document, project_from_dict


_RELATION_LABELS = {
    "unsaved": "Unsaved project",
    "source_missing": "Original file missing",
    "source_unchanged": "Original unchanged",
    "source_changed": "Original changed",
    "source_newer": "Original is newer",
}


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
    return (
        "This recovery came from a project that had not been explicitly saved. "
        "Restoring opens it as an unsaved project."
    )


@dataclass(frozen=True)
class RecoveryDifference:
    path: str
    change: str
    original: Any
    recovered: Any


@dataclass(frozen=True)
class RecoveryComparison:
    state: str
    summary: str
    differences: tuple[RecoveryDifference, ...]
    truncated: bool = False


def _identified_list(items: list[Any]) -> dict[str, Any] | None:
    mapped: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict):
            return None
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id or item_id in mapped:
            return None
        mapped[item_id] = item
    return mapped


def _project_differences(
    original: Any,
    recovered: Any,
    *,
    max_changes: int,
) -> tuple[tuple[RecoveryDifference, ...], bool]:
    changes: list[RecoveryDifference] = []
    truncated = False

    def add(path: str, change: str, before: Any, after: Any) -> None:
        nonlocal truncated
        if len(changes) >= max_changes:
            truncated = True
            return
        changes.append(
            RecoveryDifference(
                path=path or "<project>",
                change=change,
                original=before,
                recovered=after,
            )
        )

    def walk(before: Any, after: Any, path: str, depth: int = 0) -> None:
        nonlocal truncated
        if before == after:
            return
        if len(changes) >= max_changes:
            truncated = True
            return
        if depth >= 64:
            add(path, "changed", before, after)
            return
        if isinstance(before, dict) and isinstance(after, dict):
            for key in sorted(set(before) | set(after), key=str):
                child = f"{path}.{key}" if path else str(key)
                if key not in before:
                    add(child, "added", None, after[key])
                elif key not in after:
                    add(child, "removed", before[key], None)
                else:
                    walk(before[key], after[key], child, depth + 1)
            return
        if isinstance(before, list) and isinstance(after, list):
            before_by_id = _identified_list(before) if path == "analyses" else None
            after_by_id = _identified_list(after) if path == "analyses" else None
            if before_by_id is not None and after_by_id is not None:
                for item_id in sorted(set(before_by_id) | set(after_by_id)):
                    child = f"{path}[{item_id}]"
                    if item_id not in before_by_id:
                        add(child, "added", None, after_by_id[item_id])
                    elif item_id not in after_by_id:
                        add(child, "removed", before_by_id[item_id], None)
                    else:
                        walk(
                            before_by_id[item_id],
                            after_by_id[item_id],
                            child,
                            depth + 1,
                        )
                return
            common = min(len(before), len(after))
            for index in range(common):
                walk(before[index], after[index], f"{path}[{index}]", depth + 1)
            for index in range(common, len(before)):
                add(f"{path}[{index}]", "removed", before[index], None)
            for index in range(common, len(after)):
                add(f"{path}[{index}]", "added", None, after[index])
            return
        add(path, "changed", before, after)

    walk(original, recovered, "")
    return tuple(changes), truncated


def compare_recovery_to_source(
    candidate: RecoveryCandidate,
    *,
    max_changes: int = 200,
) -> RecoveryComparison:
    """Compare recovered project semantics with the current original project.

    File timestamps, whitespace, and serialized application-version text do not
    count as project changes. Analysis lists are matched by stable analysis id so
    harmless ordering differences do not obscure the recovered engineering edits.
    """
    if max_changes < 1:
        raise ValueError("max_changes must be at least 1")
    if candidate.source_path is None:
        return RecoveryComparison(
            state="unsaved",
            summary="No original project had been saved, so there is no source file to compare.",
            differences=(),
        )
    source = candidate.source_path
    if not source.exists():
        return RecoveryComparison(
            state="source_missing",
            summary="The original project file is missing; semantic comparison is unavailable.",
            differences=(),
        )
    try:
        payload = load_recovery_artifact(candidate.path)
        raw_project = payload["snapshot"].get("project")
        if not isinstance(raw_project, dict):
            raise ValueError("snapshot.project must be an object")
        recovered_project = project_from_dict(raw_project).to_dict()
        source_project = load_project_document(source).to_dict()
    except (OSError, UnicodeError, ValueError) as exc:
        return RecoveryComparison(
            state="unavailable",
            summary=f"Project comparison is unavailable: {exc}",
            differences=(),
        )

    # Application version is serialization/runtime evidence, not an operator edit.
    recovered_project.pop("application_version", None)
    source_project.pop("application_version", None)
    differences, truncated = _project_differences(
        source_project,
        recovered_project,
        max_changes=max_changes,
    )
    if not differences:
        return RecoveryComparison(
            state="identical",
            summary=(
                "Recovered project content matches the current original project. "
                "Any fingerprint difference is file-level only."
            ),
            differences=(),
        )
    count_text = f"{len(differences)}+" if truncated else str(len(differences))
    return RecoveryComparison(
        state="different",
        summary=(
            f"{count_text} semantic project difference(s) found. "
            "Review the exact paths below before restoring."
        ),
        differences=differences,
        truncated=truncated,
    )


def _display_difference_value(value: Any, *, limit: int = 180) -> str:
    try:
        text = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        text = repr(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


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
    comparison: RecoveryComparison


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
        application_version=str(payload.get("application_version", "unknown")),
        analysis_count=len(analyses),
        analysis_names=tuple(names),
        editor_analysis_id=editor_id,
        editor_json_valid=editor_valid,
        editor_text=editor_text,
        comparison=compare_recovery_to_source(candidate),
    )


class RecoveryInspectDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, candidate: RecoveryCandidate):
        super().__init__(parent)
        self.title("Inspect recovery")
        self.geometry("920x760")
        self.minsize(720, 560)
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
            wraplength=860,
        ).pack(anchor="w", pady=(6, 0))

        details = ttk.LabelFrame(self, text="Recovery evidence", padding=10)
        details.pack(fill="x", padx=12, pady=(0, 10))
        rows = (
            ("Project identity", inspection.project_identity),
            ("Recovered at", inspection.saved_at_utc),
            ("Source status", inspection.source_status),
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
        ttk.Label(analyses_frame, text=analyses_text, wraplength=860).pack(anchor="w")

        comparison_frame = ttk.LabelFrame(
            self, text="Changes versus original project", padding=8
        )
        comparison_frame.pack(fill="both", padx=12, pady=(0, 10))
        ttk.Label(
            comparison_frame,
            text=inspection.comparison.summary,
            wraplength=860,
        ).pack(anchor="w")
        if inspection.comparison.differences:
            table = ttk.Frame(comparison_frame)
            table.pack(fill="both", expand=True, pady=(6, 0))
            diff_tree = ttk.Treeview(
                table,
                columns=("change", "original", "recovered"),
                show="tree headings",
                height=min(8, len(inspection.comparison.differences)),
            )
            diff_tree.heading("#0", text="Project path")
            diff_tree.heading("change", text="Change")
            diff_tree.heading("original", text="Original")
            diff_tree.heading("recovered", text="Recovered")
            diff_tree.column("#0", width=260, stretch=True)
            diff_tree.column("change", width=85, stretch=False)
            diff_tree.column("original", width=230, stretch=True)
            diff_tree.column("recovered", width=230, stretch=True)
            yscroll = ttk.Scrollbar(table, orient="vertical", command=diff_tree.yview)
            diff_tree.configure(yscrollcommand=yscroll.set)
            diff_tree.pack(side="left", fill="both", expand=True)
            yscroll.pack(side="right", fill="y")
            for difference in inspection.comparison.differences:
                diff_tree.insert(
                    "",
                    "end",
                    text=difference.path,
                    values=(
                        difference.change,
                        _display_difference_value(difference.original),
                        _display_difference_value(difference.recovered),
                    ),
                )

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
            columns=("time", "state", "source"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Project")
        self.tree.heading("time", text="Recovery timestamp (UTC)")
        self.tree.heading("state", text="Original project")
        self.tree.heading("source", text="Source path")
        self.tree.column("#0", width=210, stretch=False)
        self.tree.column("time", width=205, stretch=False)
        self.tree.column("state", width=150, stretch=False)
        self.tree.column("source", width=360, stretch=True)
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

        if scan.issues:
            issue_lines = "; ".join(
                f"{issue.path.name}: {issue.error}" for issue in scan.issues[:3]
            )
            suffix = (
                f" (+{len(scan.issues) - 3} more)" if len(scan.issues) > 3 else ""
            )
            ttk.Label(
                self,
                text=(
                    f"{len(scan.issues)} recovery artifact(s) could not be read and "
                    f"were preserved: {issue_lines}{suffix}"
                ),
                wraplength=940,
                padding=(12, 6, 12, 0),
            ).pack(fill="x")

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
