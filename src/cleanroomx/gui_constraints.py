from __future__ import annotations

import copy
import json
from typing import Any, Callable

import tkinter as tk
from tkinter import messagebox, ttk

from .compliance_rulepack import (
    RULE_PACK_SCHEMA,
    RULE_PACK_SCHEMA_VERSION,
    compliance_check_from_dict,
)
from .project import ProjectDocument


_OPERATORS = ("exists", "equals", "min", "max", "range", "one_of")


def _analysis(project: ProjectDocument, analysis_id: str):
    analysis = project.analysis_by_id(analysis_id)
    if analysis.kind != "compliance_check":
        raise ValueError(f"analysis {analysis_id!r} is not a compliance constraint set")
    return analysis


def _validated_payload(payload: dict[str, Any]) -> dict[str, Any]:
    check = compliance_check_from_dict(payload)
    return {
        "name": check.name,
        "rule_pack": check.rule_pack.to_dict(),
        "evidence": copy.deepcopy(check.evidence),
    }


def constraint_sets_snapshot(project: ProjectDocument) -> list[dict[str, Any]]:
    """Project persisted compliance analyses as editable engineering constraint sets."""
    rows: list[dict[str, Any]] = []
    for analysis in project.analyses:
        if analysis.kind != "compliance_check":
            continue
        try:
            check = compliance_check_from_dict(analysis.input)
        except Exception as exc:
            rows.append(
                {
                    "analysis_id": analysis.id,
                    "analysis_name": analysis.name,
                    "valid": False,
                    "error": str(exc),
                    "pack": None,
                    "rules": [],
                }
            )
            continue
        rows.append(
            {
                "analysis_id": analysis.id,
                "analysis_name": analysis.name,
                "valid": True,
                "error": None,
                "pack": {
                    "id": check.rule_pack.id,
                    "version": check.rule_pack.version,
                    "title": check.rule_pack.title,
                    "source": check.rule_pack.source,
                },
                "rules": [
                    {
                        "id": rule.id,
                        "title": rule.title,
                        "evidence_path": rule.evidence_path,
                        "operator": rule.operator,
                        "expected": copy.deepcopy(rule.expected),
                        "unit": rule.unit,
                        "tolerance": rule.tolerance,
                        "source": rule.source,
                        "reference": rule.reference,
                    }
                    for rule in check.rule_pack.rules
                ],
            }
        )
    return rows


def create_constraint_set(
    project: ProjectDocument,
    *,
    analysis_name: str,
    pack_id: str,
    version: str,
    title: str,
    source: str,
    first_rule: dict[str, Any],
) -> str:
    payload = _validated_payload(
        {
            "name": analysis_name,
            "rule_pack": {
                "schema": RULE_PACK_SCHEMA,
                "schema_version": RULE_PACK_SCHEMA_VERSION,
                "id": pack_id,
                "version": version,
                "title": title,
                "source": source,
                "rules": [copy.deepcopy(first_rule)],
            },
            "evidence": {},
        }
    )
    analysis = project.create_analysis(
        kind="compliance_check",
        name=analysis_name,
        payload=payload,
    )
    return analysis.id


def update_constraint_set(
    project: ProjectDocument,
    analysis_id: str,
    *,
    analysis_name: str,
    pack_id: str,
    version: str,
    title: str,
    source: str,
) -> None:
    analysis = _analysis(project, analysis_id)
    payload = copy.deepcopy(analysis.input)
    payload["name"] = analysis_name
    pack = payload.get("rule_pack")
    if not isinstance(pack, dict):
        raise ValueError("constraint set rule_pack must be an object")
    pack.update(
        {
            "id": pack_id,
            "version": version,
            "title": title,
            "source": source,
        }
    )
    analysis.input = _validated_payload(payload)
    analysis.name = analysis_name


def add_constraint_rule(
    project: ProjectDocument,
    analysis_id: str,
    rule: dict[str, Any],
) -> None:
    analysis = _analysis(project, analysis_id)
    payload = copy.deepcopy(analysis.input)
    pack = payload.get("rule_pack")
    if not isinstance(pack, dict) or not isinstance(pack.get("rules"), list):
        raise ValueError("constraint set rule_pack.rules must be an array")
    pack["rules"].append(copy.deepcopy(rule))
    analysis.input = _validated_payload(payload)


def update_constraint_rule(
    project: ProjectDocument,
    analysis_id: str,
    rule_id: str,
    rule: dict[str, Any],
) -> None:
    analysis = _analysis(project, analysis_id)
    payload = copy.deepcopy(analysis.input)
    pack = payload.get("rule_pack")
    if not isinstance(pack, dict) or not isinstance(pack.get("rules"), list):
        raise ValueError("constraint set rule_pack.rules must be an array")
    indexes = [
        index
        for index, item in enumerate(pack["rules"])
        if isinstance(item, dict) and item.get("id") == rule_id
    ]
    if len(indexes) != 1:
        raise ValueError(f"constraint rule {rule_id!r} was not found uniquely")
    pack["rules"][indexes[0]] = copy.deepcopy(rule)
    analysis.input = _validated_payload(payload)


def remove_constraint_rule(
    project: ProjectDocument,
    analysis_id: str,
    rule_id: str,
) -> None:
    analysis = _analysis(project, analysis_id)
    payload = copy.deepcopy(analysis.input)
    pack = payload.get("rule_pack")
    if not isinstance(pack, dict) or not isinstance(pack.get("rules"), list):
        raise ValueError("constraint set rule_pack.rules must be an array")
    rules = pack["rules"]
    indexes = [
        index
        for index, item in enumerate(rules)
        if isinstance(item, dict) and item.get("id") == rule_id
    ]
    if len(indexes) != 1:
        raise ValueError(f"constraint rule {rule_id!r} was not found uniquely")
    if len(rules) == 1:
        raise ValueError(
            "a constraint set must retain at least one rule; remove the set instead"
        )
    del rules[indexes[0]]
    analysis.input = _validated_payload(payload)


class _RuleDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, *, initial: dict[str, Any] | None = None):
        super().__init__(parent)
        self.title("Constraint Rule")
        self.transient(parent)
        self.resizable(True, False)
        self.result: dict[str, Any] | None = None
        value = initial or {}
        fields = (
            ("ID", "id", value.get("id", "")),
            ("Title", "title", value.get("title", "")),
            ("Evidence JSON pointer", "evidence_path", value.get("evidence_path", "")),
            ("Expected JSON", "expected", "" if value.get("operator") == "exists" else json.dumps(value.get("expected"), ensure_ascii=False)),
            ("Unit", "unit", value.get("unit") or ""),
            ("Tolerance", "tolerance", str(value.get("tolerance", 0.0))),
            ("Source override", "source", value.get("source") or ""),
            ("Reference", "reference", value.get("reference") or ""),
        )
        self.vars: dict[str, tk.StringVar] = {}
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        for row, (label, key, default) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=str(default))
            self.vars[key] = var
            ttk.Entry(body, textvariable=var, width=58).grid(
                row=row, column=1, sticky="ew", padx=(10, 0), pady=3
            )
        ttk.Label(body, text="Operator").grid(row=3, column=0, sticky="w", pady=3)
        self.operator_var = tk.StringVar(value=str(value.get("operator") or "min"))
        ttk.Combobox(
            body,
            textvariable=self.operator_var,
            values=_OPERATORS,
            state="readonly",
            width=18,
        ).grid(row=3, column=1, sticky="w", padx=(10, 0), pady=3)
        # Move expected and following rows down one after inserting operator.
        for child in body.grid_slaves():
            info = child.grid_info()
            row = int(info["row"])
            if row >= 3 and child not in body.grid_slaves(row=3):
                child.grid_configure(row=row + 1)
        buttons = ttk.Frame(body)
        buttons.grid(row=10, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Apply", command=self._accept).pack(
            side="right", padx=(0, 6)
        )
        body.columnconfigure(1, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()

    def _accept(self) -> None:
        operator = self.operator_var.get()
        rule: dict[str, Any] = {
            "id": self.vars["id"].get().strip(),
            "title": self.vars["title"].get().strip(),
            "evidence_path": self.vars["evidence_path"].get().strip(),
            "operator": operator,
            "tolerance": float(self.vars["tolerance"].get().strip() or "0"),
        }
        if operator != "exists":
            expected_text = self.vars["expected"].get().strip()
            try:
                rule["expected"] = json.loads(expected_text)
            except json.JSONDecodeError as exc:
                messagebox.showerror(
                    "Invalid expected value",
                    f"Expected must be valid JSON.\n\n{exc}",
                    parent=self,
                )
                return
        for key in ("unit", "source", "reference"):
            text = self.vars[key].get().strip()
            if text:
                rule[key] = text
        self.result = rule
        self.destroy()


class _SetDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, *, initial: dict[str, Any] | None = None):
        super().__init__(parent)
        self.title("Constraint Set")
        self.transient(parent)
        self.resizable(True, False)
        self.result: dict[str, str] | None = None
        value = initial or {}
        fields = (
            ("Analysis name", "analysis_name", value.get("analysis_name", "")),
            ("Pack ID", "pack_id", value.get("id", "")),
            ("Version", "version", value.get("version", "1.0")),
            ("Title", "title", value.get("title", "")),
            ("Source", "source", value.get("source", "")),
        )
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        self.vars: dict[str, tk.StringVar] = {}
        for row, (label, key, default) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=str(default))
            self.vars[key] = var
            ttk.Entry(body, textvariable=var, width=58).grid(
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
        if not all(result.values()):
            messagebox.showerror(
                "Incomplete constraint set",
                "Analysis name, pack ID, version, title, and source are required.",
                parent=self,
            )
            return
        self.result = result
        self.destroy()


class ConstraintManagerDialog(tk.Toplevel):
    """Edit project-owned engineering constraints through canonical rule packs."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        project_getter: Callable[[], ProjectDocument],
        apply_project_edit: Callable[[str, Callable[[ProjectDocument], Any]], Any],
        on_changed: Callable[[str | None], None],
    ) -> None:
        super().__init__(parent)
        self.title("Project Constraint Manager")
        self.geometry("1180x680")
        self.minsize(900, 520)
        self.transient(parent)
        self._project_getter = project_getter
        self._apply_project_edit = apply_project_edit
        self._on_changed = on_changed
        self._sets: dict[str, dict[str, Any]] = {}
        self._rules: dict[str, dict[str, Any]] = {}

        header = ttk.Frame(self, padding=(10, 8))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="PROJECT CONSTRAINTS",
            style="CX.Section.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            text=(
                "Constraints use CleanroomX's versioned compliance rule-pack engine; "
                "no hidden acceptance criteria are added."
            ),
        ).pack(side="left", padx=(14, 0))

        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        left = ttk.Frame(panes)
        right = ttk.Frame(panes)
        panes.add(left, weight=2)
        panes.add(right, weight=3)

        set_toolbar = ttk.Frame(left)
        set_toolbar.pack(fill="x", pady=(0, 5))
        ttk.Button(set_toolbar, text="Add Set", command=self._add_set).pack(side="left")
        ttk.Button(set_toolbar, text="Edit", command=self._edit_set).pack(side="left", padx=4)
        ttk.Button(set_toolbar, text="Remove", command=self._remove_set).pack(side="left")

        self.set_tree = ttk.Treeview(
            left,
            columns=("name", "version", "rules", "state"),
            show="headings",
            selectmode="browse",
        )
        for column, title, width in (
            ("name", "Constraint set", 210),
            ("version", "Version", 80),
            ("rules", "Rules", 60),
            ("state", "State", 100),
        ):
            self.set_tree.heading(column, text=title)
            self.set_tree.column(column, width=width, minwidth=55)
        self.set_tree.pack(fill="both", expand=True)
        self.set_tree.bind("<<TreeviewSelect>>", lambda _event: self._populate_rules())

        rule_toolbar = ttk.Frame(right)
        rule_toolbar.pack(fill="x", pady=(0, 5))
        ttk.Button(rule_toolbar, text="Add Rule", command=self._add_rule).pack(side="left")
        ttk.Button(rule_toolbar, text="Edit", command=self._edit_rule).pack(side="left", padx=4)
        ttk.Button(rule_toolbar, text="Remove", command=self._remove_rule).pack(side="left")

        self.rule_tree = ttk.Treeview(
            right,
            columns=("title", "operator", "expected", "unit", "tolerance", "evidence"),
            show="headings",
            selectmode="browse",
        )
        for column, title, width in (
            ("title", "Rule", 170),
            ("operator", "Op", 70),
            ("expected", "Expected", 120),
            ("unit", "Unit", 70),
            ("tolerance", "Tol.", 65),
            ("evidence", "Evidence path", 220),
        ):
            self.rule_tree.heading(column, text=title)
            self.rule_tree.column(column, width=width, minwidth=55)
        self.rule_tree.pack(fill="both", expand=True)
        self.refresh()

    def _selected_set_id(self) -> str | None:
        selected = self.set_tree.selection()
        return selected[0] if selected else None

    def _selected_rule_id(self) -> str | None:
        selected = self.rule_tree.selection()
        return selected[0] if selected else None

    def refresh(self, *, select_analysis_id: str | None = None) -> None:
        previous = select_analysis_id or self._selected_set_id()
        for iid in self.set_tree.get_children():
            self.set_tree.delete(iid)
        self._sets.clear()
        for item in constraint_sets_snapshot(self._project_getter()):
            analysis_id = item["analysis_id"]
            self._sets[analysis_id] = item
            pack = item["pack"] or {}
            self.set_tree.insert(
                "",
                "end",
                iid=analysis_id,
                values=(
                    item["analysis_name"],
                    pack.get("version", "—"),
                    len(item["rules"]),
                    "VALID" if item["valid"] else "INVALID",
                ),
            )
        if previous and self.set_tree.exists(previous):
            self.set_tree.selection_set(previous)
            self.set_tree.focus(previous)
        elif self.set_tree.get_children():
            first = self.set_tree.get_children()[0]
            self.set_tree.selection_set(first)
            self.set_tree.focus(first)
        self._populate_rules()

    def _populate_rules(self) -> None:
        for iid in self.rule_tree.get_children():
            self.rule_tree.delete(iid)
        self._rules.clear()
        analysis_id = self._selected_set_id()
        if not analysis_id:
            return
        item = self._sets[analysis_id]
        if not item["valid"]:
            return
        for rule in item["rules"]:
            rule_id = str(rule["id"])
            self._rules[rule_id] = rule
            expected = "—" if rule["operator"] == "exists" else json.dumps(
                rule["expected"], ensure_ascii=False, sort_keys=True
            )
            self.rule_tree.insert(
                "",
                "end",
                iid=rule_id,
                values=(
                    rule["title"],
                    rule["operator"],
                    expected,
                    rule["unit"] or "—",
                    rule["tolerance"],
                    rule["evidence_path"],
                ),
            )

    def _apply(self, description: str, mutation: Callable[[ProjectDocument], Any], *, select: str | None = None) -> bool:
        try:
            result = self._apply_project_edit(description, mutation)
        except Exception as exc:
            messagebox.showerror("Constraint update failed", str(exc), parent=self)
            return False
        selected = result if isinstance(result, str) else select
        self.refresh(select_analysis_id=selected)
        self._on_changed(selected)
        return True

    def _add_set(self) -> None:
        dialog = _SetDialog(self)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        rule_dialog = _RuleDialog(self)
        self.wait_window(rule_dialog)
        if rule_dialog.result is None:
            return
        values = dialog.result
        self._apply(
            "Add constraint set",
            lambda project: create_constraint_set(
                project,
                **values,
                first_rule=rule_dialog.result,
            ),
        )

    def _edit_set(self) -> None:
        analysis_id = self._selected_set_id()
        if not analysis_id:
            return
        item = self._sets[analysis_id]
        if not item["valid"]:
            messagebox.showerror(
                "Invalid constraint set",
                item["error"] or "The constraint set cannot be edited structurally.",
                parent=self,
            )
            return
        pack = item["pack"] or {}
        dialog = _SetDialog(
            self,
            initial={
                "analysis_name": item["analysis_name"],
                **pack,
            },
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self._apply(
            "Edit constraint set",
            lambda project: update_constraint_set(
                project,
                analysis_id,
                **dialog.result,
            ),
            select=analysis_id,
        )

    def _remove_set(self) -> None:
        analysis_id = self._selected_set_id()
        if not analysis_id:
            return
        if not messagebox.askyesno(
            "Remove constraint set?",
            "Remove this constraint set from the project? This is undoable.",
            parent=self,
        ):
            return
        self._apply(
            "Remove constraint set",
            lambda project: project.remove_analysis(analysis_id),
        )

    def _add_rule(self) -> None:
        analysis_id = self._selected_set_id()
        if not analysis_id:
            messagebox.showinfo("Constraint set required", "Select a constraint set first.", parent=self)
            return
        dialog = _RuleDialog(self)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self._apply(
            "Add constraint rule",
            lambda project: add_constraint_rule(project, analysis_id, dialog.result),
            select=analysis_id,
        )

    def _edit_rule(self) -> None:
        analysis_id = self._selected_set_id()
        rule_id = self._selected_rule_id()
        if not analysis_id or not rule_id:
            return
        dialog = _RuleDialog(self, initial=self._rules[rule_id])
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self._apply(
            "Edit constraint rule",
            lambda project: update_constraint_rule(
                project, analysis_id, rule_id, dialog.result
            ),
            select=analysis_id,
        )

    def _remove_rule(self) -> None:
        analysis_id = self._selected_set_id()
        rule_id = self._selected_rule_id()
        if not analysis_id or not rule_id:
            return
        if not messagebox.askyesno(
            "Remove constraint rule?",
            f"Remove rule {rule_id!r}? This is undoable.",
            parent=self,
        ):
            return
        self._apply(
            "Remove constraint rule",
            lambda project: remove_constraint_rule(project, analysis_id, rule_id),
            select=analysis_id,
        )
