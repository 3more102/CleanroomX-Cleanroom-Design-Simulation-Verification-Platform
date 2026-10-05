from __future__ import annotations

import copy
import json
from typing import Any, Callable

import tkinter as tk
from tkinter import messagebox, ttk

from .project import ProjectDocument, project_from_dict
from .runtime_diagnostics import record_gui_exception
from .project_requirements import (
    PROJECT_REQUIREMENTS_METADATA_KEY,
    PROJECT_REQUIREMENTS_SCHEMA,
    PROJECT_REQUIREMENTS_SCHEMA_VERSION,
    normalize_project_requirements_metadata,
    project_requirements_from_dict,
)


def requirements_snapshot(project: ProjectDocument) -> dict[str, Any]:
    raw = project.metadata.get(PROJECT_REQUIREMENTS_METADATA_KEY)
    if raw is None:
        return {
            "schema": PROJECT_REQUIREMENTS_SCHEMA,
            "schema_version": PROJECT_REQUIREMENTS_SCHEMA_VERSION,
            "sets": [],
            "requirements_sha256": None,
        }
    return project_requirements_from_dict(raw).to_dict()


def _editable_registry(project: ProjectDocument) -> dict[str, Any]:
    snapshot = requirements_snapshot(project)
    snapshot.pop("requirements_sha256", None)
    return snapshot


def _commit_registry(project: ProjectDocument, registry: dict[str, Any]) -> None:
    candidate_metadata = copy.deepcopy(project.metadata)
    candidate_metadata[PROJECT_REQUIREMENTS_METADATA_KEY] = copy.deepcopy(registry)
    candidate_metadata = normalize_project_requirements_metadata(candidate_metadata)

    # Validate the complete project, including existing requirement-evidence mappings,
    # before publishing candidate metadata into the mutable in-memory document.
    document = project.to_dict()
    document["project"]["metadata"] = candidate_metadata
    project_from_dict(document)
    project.metadata = candidate_metadata


def add_requirement_set(
    project: ProjectDocument,
    *,
    set_id: str,
    title: str,
    source: str,
    source_revision: str,
    description: str | None = None,
) -> None:
    registry = _editable_registry(project)
    registry["sets"].append(
        {
            "id": set_id,
            "title": title,
            "description": description,
            "source": source,
            "source_revision": source_revision,
            "requirements": [],
        }
    )
    _commit_registry(project, registry)


def update_requirement_set(
    project: ProjectDocument,
    current_set_id: str,
    *,
    set_id: str,
    title: str,
    source: str,
    source_revision: str,
    description: str | None = None,
) -> None:
    registry = _editable_registry(project)
    matches = [item for item in registry["sets"] if item["id"] == current_set_id]
    if len(matches) != 1:
        raise ValueError(f"requirement set {current_set_id!r} was not found uniquely")
    item = matches[0]
    item.update(
        {
            "id": set_id,
            "title": title,
            "description": description,
            "source": source,
            "source_revision": source_revision,
        }
    )
    _commit_registry(project, registry)


def remove_requirement_set(project: ProjectDocument, set_id: str) -> None:
    registry = _editable_registry(project)
    before = len(registry["sets"])
    registry["sets"] = [item for item in registry["sets"] if item["id"] != set_id]
    if len(registry["sets"]) != before - 1:
        raise ValueError(f"requirement set {set_id!r} was not found uniquely")
    _commit_registry(project, registry)


def add_requirement(
    project: ProjectDocument,
    set_id: str,
    requirement: dict[str, Any],
) -> None:
    registry = _editable_registry(project)
    matches = [item for item in registry["sets"] if item["id"] == set_id]
    if len(matches) != 1:
        raise ValueError(f"requirement set {set_id!r} was not found uniquely")
    matches[0]["requirements"].append(copy.deepcopy(requirement))
    _commit_registry(project, registry)


def update_requirement(
    project: ProjectDocument,
    set_id: str,
    requirement_id: str,
    requirement: dict[str, Any],
) -> None:
    registry = _editable_registry(project)
    sets = [item for item in registry["sets"] if item["id"] == set_id]
    if len(sets) != 1:
        raise ValueError(f"requirement set {set_id!r} was not found uniquely")
    requirements = sets[0]["requirements"]
    indexes = [
        index
        for index, item in enumerate(requirements)
        if item.get("id") == requirement_id
    ]
    if len(indexes) != 1:
        raise ValueError(f"requirement {requirement_id!r} was not found uniquely")
    requirements[indexes[0]] = copy.deepcopy(requirement)
    _commit_registry(project, registry)


def remove_requirement(
    project: ProjectDocument,
    set_id: str,
    requirement_id: str,
) -> None:
    registry = _editable_registry(project)
    sets = [item for item in registry["sets"] if item["id"] == set_id]
    if len(sets) != 1:
        raise ValueError(f"requirement set {set_id!r} was not found uniquely")
    requirements = sets[0]["requirements"]
    before = len(requirements)
    sets[0]["requirements"] = [
        item for item in requirements if item.get("id") != requirement_id
    ]
    if len(sets[0]["requirements"]) != before - 1:
        raise ValueError(f"requirement {requirement_id!r} was not found uniquely")
    _commit_registry(project, registry)


def _csv_values(text: str) -> list[str]:
    values = [item.strip() for item in text.split(",") if item.strip()]
    if len(values) != len(set(values)):
        raise ValueError("comma-separated values must not contain duplicates")
    return values


def _optional_float(text: str, field_name: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be numeric") from exc


class _RequirementSetDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, *, initial: dict[str, Any] | None = None):
        super().__init__(parent)
        self.title("Requirement Set")
        self.transient(parent)
        self.result: dict[str, Any] | None = None
        value = initial or {}
        fields = (
            ("Set ID", "set_id", value.get("id", "")),
            ("Title", "title", value.get("title", "")),
            ("Source", "source", value.get("source", "")),
            ("Source revision", "source_revision", value.get("source_revision", "")),
            ("Description", "description", value.get("description") or ""),
        )
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        self.vars: dict[str, tk.StringVar] = {}
        for row, (label, key, default) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=str(default))
            self.vars[key] = var
            ttk.Entry(body, textvariable=var, width=62).grid(
                row=row, column=1, sticky="ew", padx=(10, 0), pady=3
            )
        buttons = ttk.Frame(body)
        buttons.grid(row=len(fields), column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Apply", command=self._accept).pack(
            side="right", padx=(0, 6)
        )
        body.columnconfigure(1, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()

    def _accept(self) -> None:
        result = {key: var.get().strip() for key, var in self.vars.items()}
        required = ("set_id", "title", "source", "source_revision")
        if any(not result[key] for key in required):
            messagebox.showerror(
                "Incomplete requirement set",
                "Set ID, title, source, and source revision are required.",
                parent=self,
            )
            return
        result["description"] = result["description"] or None
        self.result = result
        self.destroy()


class _RequirementDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        initial: dict[str, Any] | None = None,
        lock_id: bool = False,
    ):
        super().__init__(parent)
        self.title("Project Requirement")
        self.transient(parent)
        self.result: dict[str, Any] | None = None
        value = initial or {}
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)

        self.vars: dict[str, tk.StringVar] = {}
        rows = (
            ("Requirement ID", "id", value.get("id", "")),
            ("Title", "title", value.get("title", "")),
            ("Description", "description", value.get("description", "")),
            ("Discipline", "discipline", value.get("discipline", "")),
            ("Category", "category", value.get("category", "")),
            ("Source", "source", value.get("source", "")),
            ("Source revision", "source_revision", value.get("source_revision", "")),
            ("Reference", "reference", value.get("reference") or ""),
            ("Unit", "unit", value.get("unit") or ""),
        )
        for row, (label, key, default) in enumerate(rows):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=str(default))
            self.vars[key] = var
            entry = ttk.Entry(body, textvariable=var, width=64)
            entry.grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=2)
            if key == "id" and lock_id:
                entry.configure(state="disabled")

        criterion = ttk.LabelFrame(body, text="Acceptance criterion", padding=8)
        criterion.grid(row=0, column=2, rowspan=9, sticky="nsew", padx=(14, 0))
        self.criterion_mode = tk.StringVar(
            value=(
                "target"
                if value.get("target") is not None
                else "bounds"
                if value.get("minimum") is not None or value.get("maximum") is not None
                else "none"
            )
        )
        for row, mode in enumerate(("target", "bounds", "none")):
            ttk.Radiobutton(
                criterion,
                text=mode.title(),
                variable=self.criterion_mode,
                value=mode,
            ).grid(row=row, column=0, sticky="w")
        self.target_var = tk.StringVar(
            value=(
                json.dumps(value.get("target"), ensure_ascii=False)
                if value.get("target") is not None
                else ""
            )
        )
        self.minimum_var = tk.StringVar(
            value="" if value.get("minimum") is None else str(value.get("minimum"))
        )
        self.maximum_var = tk.StringVar(
            value="" if value.get("maximum") is None else str(value.get("maximum"))
        )
        self.tolerance_var = tk.StringVar(
            value="" if value.get("tolerance") is None else str(value.get("tolerance"))
        )
        for row, (label, var) in enumerate(
            (
                ("Target JSON", self.target_var),
                ("Minimum", self.minimum_var),
                ("Maximum", self.maximum_var),
                ("Tolerance", self.tolerance_var),
            ),
            start=3,
        ):
            ttk.Label(criterion, text=label).grid(row=row, column=0, sticky="w", pady=(5, 0))
            ttk.Entry(criterion, textvariable=var, width=26).grid(
                row=row, column=1, sticky="ew", padx=(8, 0), pady=(5, 0)
            )

        start = len(rows)
        self.applicability_var = tk.StringVar(value=str(value.get("applicability", "unknown")))
        self.status_var = tk.StringVar(value=str(value.get("status", "draft")))
        ttk.Label(body, text="Applicability").grid(row=start, column=0, sticky="w", pady=2)
        ttk.Combobox(
            body,
            textvariable=self.applicability_var,
            values=("applicable", "conditional", "not_applicable", "unknown"),
            state="readonly",
        ).grid(row=start, column=1, sticky="w", padx=(10, 0), pady=2)
        ttk.Label(body, text="Status").grid(row=start + 1, column=0, sticky="w", pady=2)
        ttk.Combobox(
            body,
            textvariable=self.status_var,
            values=("draft", "approved", "superseded", "withdrawn"),
            state="readonly",
        ).grid(row=start + 1, column=1, sticky="w", padx=(10, 0), pady=2)

        extra = (
            ("Scope IDs (comma-separated)", "scope", ", ".join(value.get("scope", []))),
            ("Verification method", "verification_method", value.get("verification_method") or ""),
            ("Required evidence (comma-separated)", "required_evidence", ", ".join(value.get("required_evidence", []))),
            ("Assumptions (comma-separated)", "assumptions", ", ".join(value.get("assumptions", []))),
            ("Notes", "notes", value.get("notes") or ""),
        )
        for offset, (label, key, default) in enumerate(extra, start=start + 2):
            ttk.Label(body, text=label).grid(row=offset, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=str(default))
            self.vars[key] = var
            ttk.Entry(body, textvariable=var, width=64).grid(
                row=offset, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=2
            )

        buttons = ttk.Frame(body)
        buttons.grid(
            row=start + 2 + len(extra),
            column=0,
            columnspan=3,
            sticky="e",
            pady=(12, 0),
        )
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Apply", command=self._accept).pack(
            side="right", padx=(0, 6)
        )
        body.columnconfigure(1, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()

    def _accept(self) -> None:
        required_keys = (
            "id",
            "title",
            "description",
            "discipline",
            "category",
            "source",
            "source_revision",
        )
        values = {key: var.get().strip() for key, var in self.vars.items()}
        if any(not values[key] for key in required_keys):
            messagebox.showerror(
                "Incomplete requirement",
                "ID, title, description, discipline, category, source, and source revision are required.",
                parent=self,
            )
            return
        try:
            mode = self.criterion_mode.get()
            target: Any = None
            minimum = None
            maximum = None
            if mode == "target":
                text = self.target_var.get().strip()
                if not text:
                    raise ValueError("Target JSON is required in target mode")
                target = json.loads(text)
            elif mode == "bounds":
                minimum = _optional_float(self.minimum_var.get(), "Minimum")
                maximum = _optional_float(self.maximum_var.get(), "Maximum")
                if minimum is None and maximum is None:
                    raise ValueError("At least one minimum/maximum is required in bounds mode")
            tolerance = _optional_float(self.tolerance_var.get(), "Tolerance")
            requirement = {
                "id": values["id"],
                "title": values["title"],
                "description": values["description"],
                "discipline": values["discipline"],
                "category": values["category"],
                "source": values["source"],
                "source_revision": values["source_revision"],
                "reference": values["reference"] or None,
                "unit": values["unit"] or None,
                "target": target,
                "minimum": minimum,
                "maximum": maximum,
                "tolerance": tolerance,
                "applicability": self.applicability_var.get(),
                "scope": _csv_values(values["scope"]),
                "verification_method": values["verification_method"] or None,
                "required_evidence": _csv_values(values["required_evidence"]),
                "status": self.status_var.get(),
                "assumptions": _csv_values(values["assumptions"]),
                "notes": values["notes"] or None,
            }
        except (ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("Invalid requirement", str(exc), parent=self)
            return
        self.result = requirement
        self.destroy()


class RequirementsEditorDialog(tk.Toplevel):
    """Create and maintain canonical project requirement registries."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        project_getter: Callable[[], ProjectDocument],
        apply_project_edit: Callable[[str, Callable[[ProjectDocument], Any]], Any],
        on_changed: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.title("Project Requirements Editor")
        self.geometry("1260x700")
        self.minsize(980, 540)
        self.transient(parent)
        self._project_getter = project_getter
        self._apply_project_edit = apply_project_edit
        self._on_changed = on_changed
        self._sets: dict[str, dict[str, Any]] = {}
        self._requirements: dict[str, dict[str, Any]] = {}
        self.digest_var = tk.StringVar(value="Requirements SHA-256: not configured")

        header = ttk.Frame(self, padding=(10, 8))
        header.pack(fill="x")
        ttk.Label(header, text="PROJECT REQUIREMENTS", style="CX.Section.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.digest_var).pack(side="right")

        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        left = ttk.Frame(panes)
        right = ttk.Frame(panes)
        panes.add(left, weight=2)
        panes.add(right, weight=4)

        set_toolbar = ttk.Frame(left)
        set_toolbar.pack(fill="x", pady=(0, 5))
        ttk.Button(set_toolbar, text="Add Set", command=self._add_set).pack(side="left")
        ttk.Button(set_toolbar, text="Edit", command=self._edit_set).pack(side="left", padx=4)
        ttk.Button(set_toolbar, text="Remove", command=self._remove_set).pack(side="left")
        self.set_tree = ttk.Treeview(
            left,
            columns=("title", "source", "count"),
            show="headings",
            selectmode="browse",
        )
        for column, title, width in (
            ("title", "Set", 190),
            ("source", "Source", 150),
            ("count", "Reqs", 55),
        ):
            self.set_tree.heading(column, text=title)
            self.set_tree.column(column, width=width, minwidth=50)
        self.set_tree.pack(fill="both", expand=True)
        self.set_tree.bind("<<TreeviewSelect>>", lambda _event: self._populate_requirements())

        req_toolbar = ttk.Frame(right)
        req_toolbar.pack(fill="x", pady=(0, 5))
        ttk.Button(req_toolbar, text="Add Requirement", command=self._add_requirement).pack(side="left")
        ttk.Button(req_toolbar, text="Edit", command=self._edit_requirement).pack(side="left", padx=4)
        ttk.Button(req_toolbar, text="Remove", command=self._remove_requirement).pack(side="left")
        self.requirement_tree = ttk.Treeview(
            right,
            columns=("title", "discipline", "category", "criterion", "status", "scope"),
            show="headings",
            selectmode="browse",
        )
        for column, title, width in (
            ("title", "Requirement", 210),
            ("discipline", "Discipline", 100),
            ("category", "Category", 125),
            ("criterion", "Criterion", 150),
            ("status", "State", 120),
            ("scope", "Scope", 150),
        ):
            self.requirement_tree.heading(column, text=title)
            self.requirement_tree.column(column, width=width, minwidth=60)
        self.requirement_tree.pack(fill="both", expand=True)
        self.refresh()

    @staticmethod
    def _criterion_text(item: dict[str, Any]) -> str:
        unit = f" {item['unit']}" if item.get("unit") else ""
        tolerance = item.get("tolerance")
        tol = f" ±{tolerance}" if tolerance not in (None, 0, 0.0) else ""
        if item.get("target") is not None:
            return f"= {item['target']!r}{unit}{tol}"
        minimum = item.get("minimum")
        maximum = item.get("maximum")
        if minimum is not None and maximum is not None:
            return f"{minimum} … {maximum}{unit}{tol}"
        if minimum is not None:
            return f"≥ {minimum}{unit}{tol}"
        if maximum is not None:
            return f"≤ {maximum}{unit}{tol}"
        return "descriptive"

    def _selected_set_id(self) -> str | None:
        selected = self.set_tree.selection()
        return selected[0] if selected else None

    def _selected_requirement_id(self) -> str | None:
        selected = self.requirement_tree.selection()
        return selected[0] if selected else None

    def refresh(self, *, select_set_id: str | None = None) -> None:
        previous = select_set_id or self._selected_set_id()
        snapshot = requirements_snapshot(self._project_getter())
        digest = snapshot.get("requirements_sha256")
        self.digest_var.set(
            f"Requirements SHA-256: {digest or 'not configured'}"
        )
        for iid in self.set_tree.get_children():
            self.set_tree.delete(iid)
        self._sets.clear()
        for item in snapshot["sets"]:
            set_id = item["id"]
            self._sets[set_id] = item
            self.set_tree.insert(
                "",
                "end",
                iid=set_id,
                values=(
                    item["title"],
                    f"{item['source']} · {item['source_revision']}",
                    len(item["requirements"]),
                ),
            )
        if previous and self.set_tree.exists(previous):
            target = previous
        elif self.set_tree.get_children():
            target = self.set_tree.get_children()[0]
        else:
            target = None
        if target:
            self.set_tree.selection_set(target)
            self.set_tree.focus(target)
        self._populate_requirements()

    def _populate_requirements(self) -> None:
        for iid in self.requirement_tree.get_children():
            self.requirement_tree.delete(iid)
        self._requirements.clear()
        set_id = self._selected_set_id()
        if not set_id:
            return
        for item in self._sets[set_id]["requirements"]:
            requirement_id = item["id"]
            self._requirements[requirement_id] = item
            self.requirement_tree.insert(
                "",
                "end",
                iid=requirement_id,
                values=(
                    item["title"],
                    item["discipline"],
                    item["category"],
                    self._criterion_text(item),
                    f"{item['status']} / {item['applicability']}",
                    ", ".join(item["scope"]) if item["scope"] else "project",
                ),
            )

    def _apply(self, description: str, mutation: Callable[[ProjectDocument], Any], *, select_set_id: str | None = None) -> bool:
        try:
            self._apply_project_edit(description, mutation)
        except ValueError as exc:
            messagebox.showerror(
                "Requirements update failed",
                (
                    f"{exc}\n\n"
                    "Existing requirement/evidence mappings are preserved. Update or "
                    "remove dependent mappings before deleting or renaming a mapped requirement."
                ),
                parent=self,
            )
            return False
        except Exception as exc:
            report = record_gui_exception(
                f"Requirements editor: {description}",
                exc,
            )
            messagebox.showerror(
                "Requirements update failed",
                (
                    f"{report.user_message()}\n\n"
                    "Existing requirement/evidence mappings are preserved."
                ),
                parent=self,
            )
            return False
        self.refresh(select_set_id=select_set_id)
        self._on_changed()
        return True

    def _add_set(self) -> None:
        dialog = _RequirementSetDialog(self)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        result = dialog.result
        self._apply(
            "Add requirement set",
            lambda project: add_requirement_set(project, **result),
            select_set_id=result["set_id"],
        )

    def _edit_set(self) -> None:
        set_id = self._selected_set_id()
        if not set_id:
            return
        dialog = _RequirementSetDialog(self, initial=self._sets[set_id])
        self.wait_window(dialog)
        if dialog.result is None:
            return
        result = dialog.result
        self._apply(
            "Edit requirement set",
            lambda project: update_requirement_set(
                project,
                set_id,
                **result,
            ),
            select_set_id=result["set_id"],
        )

    def _remove_set(self) -> None:
        set_id = self._selected_set_id()
        if not set_id:
            return
        count = len(self._sets[set_id]["requirements"])
        if not messagebox.askyesno(
            "Remove requirement set?",
            f"Remove this set and its {count} requirement(s)? This is undoable.",
            parent=self,
        ):
            return
        self._apply(
            "Remove requirement set",
            lambda project: remove_requirement_set(project, set_id),
        )

    def _add_requirement(self) -> None:
        set_id = self._selected_set_id()
        if not set_id:
            messagebox.showinfo("Requirement set required", "Create or select a requirement set first.", parent=self)
            return
        dialog = _RequirementDialog(self)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self._apply(
            "Add project requirement",
            lambda project: add_requirement(project, set_id, dialog.result),
            select_set_id=set_id,
        )

    def _edit_requirement(self) -> None:
        set_id = self._selected_set_id()
        requirement_id = self._selected_requirement_id()
        if not set_id or not requirement_id:
            return
        dialog = _RequirementDialog(
            self,
            initial=self._requirements[requirement_id],
            lock_id=True,
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self._apply(
            "Edit project requirement",
            lambda project: update_requirement(
                project,
                set_id,
                requirement_id,
                dialog.result,
            ),
            select_set_id=set_id,
        )

    def _remove_requirement(self) -> None:
        set_id = self._selected_set_id()
        requirement_id = self._selected_requirement_id()
        if not set_id or not requirement_id:
            return
        if not messagebox.askyesno(
            "Remove requirement?",
            f"Remove requirement {requirement_id!r}? This is undoable.",
            parent=self,
        ):
            return
        self._apply(
            "Remove project requirement",
            lambda project: remove_requirement(project, set_id, requirement_id),
            select_set_id=set_id,
        )
