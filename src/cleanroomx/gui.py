from __future__ import annotations

import argparse
import copy
from datetime import datetime
import json
from pathlib import Path
import queue
import threading
import time
import uuid

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import __version__
from .autosave import (
    DEFAULT_AUTOSAVE_INTERVAL_SECONDS,
    AutosaveManager,
    discard_recovery_artifact,
    restore_recovery_artifact,
    scan_recovery_artifacts,
)
from .application import (
    ANALYSIS_SPECS,
    AnalysisRun,
    analysis_catalog,
    analysis_external_dependency_references,
    analysis_run_is_current,
    application_info,
    rebase_analysis_file_references,
    run_analysis,
    validate_analysis_input,
    validate_application_registry,
)
from .bim_ifc import (
    IFC_LINK_METADATA_KEY,
    IfcImportError,
    apply_ifc_semantics_to_project,
    extract_ifc_semantics,
    layout_from_ifc_semantics,
    plan_ifc_semantic_reimport,
    reimport_ifc_semantics_to_project,
)
from .engineering_report import engineering_report_html
from .persistence import atomic_write_text
from .project import (
    AnalysisDocument,
    ProjectDocument,
    ProjectFileBusyError,
    ProjectSaveDurabilityError,
    ProjectWriteConflictError,
    capture_project_file_revision,
    load_project_document,
    load_project_document_with_revision_info,
    new_project,
    project_file_revision_matches,
    project_from_dict,
    save_project_document,
    save_project_document_guarded,
)
from .project_history import ProjectEditHistory, ProjectHistoryState
from .project_bundle import (
    export_project_bundle,
    extract_project_bundle,
)
from .project_diagnostics import markdown_project_diagnostics_report
from .project_diagnostics_cli import (
    _assert_project_output_is_safe,
    _assert_project_publication_safe,
    _paths_alias,
)
from .gui_panels import ProjectDiagnosticsPanel
from .gui_simulation import SimulationWorkspace
from .gui_tasks import TaskCenter
from .gui_reporting import ReportingWorkspace
from .gui_command_palette import CommandPalette, PaletteCommand
from .gui_search import (
    GlobalEngineeringSearch,
    SearchEntry,
    build_engineering_search_entries,
)
from .gui_state import (
    GUI_WORKSPACE_PROFILES,
    clamp_window_size_to_display,
    default_gui_layout_state_path,
    load_gui_layout_state,
    normalize_gui_layout_state,
    save_gui_layout_state,
)
from .gui_theme import (
    configure_ttk_theme,
    normalize_density_name,
    normalize_theme_name,
)
from .gui_proofgraph import ProofGraphViewer
from .gui_ifc import ifc_import_review_snapshot, show_ifc_import_review
from .gui_start import StartCenter
from .project_dossier import (
    build_project_engineering_dossier,
    markdown_project_engineering_dossier,
)
from .project_requirement_evidence_mappings import (
    ProjectRequirementEvidenceMappingsFormatError,
)
from .project_requirements import ProjectRequirementsFormatError
from .project_requirements_traceability import (
    build_project_requirements_traceability,
)
from .project_requirements_workflow import run_project_requirements_workflow
from .project_verification_persistence import (
    persist_project_requirements_workflow_run,
)
from .project_revisions import restore_project_revision, scan_project_revisions
from .recovery_ui import RecoveryCenter
from .revision_ui import ProjectRevisionCenter
from .run_history import (
    RUN_HISTORY_METADATA_KEY,
    RunHistoryIntegrityError,
    append_run_history_evidence,
    build_run_history_evidence,
    run_history_records,
    validate_run_history,
)
from .verification_currency import (
    assess_project_verification_currency,
    verification_history_record_currency_context,
)
from .verification_run_history import (
    VerificationRunHistoryIntegrityError,
    validate_project_verification_run_history,
    verification_run_history_records,
)
from .strict_json import (
    STRICT_JSON_FILE_MAX_BYTES,
    load_strict_json,
    strict_json_loads as _strict_json_loads,
)
from .spatial import (
    SPATIAL_METADATA_KEY,
    SpatialDesignWorkspace,
    SpatialSyncError,
    sync_analysis_to_layout,
    sync_layout_to_analysis,
)


RECOVERY_CHECKPOINT_DEBOUNCE_MS = 1500
PROJECT_HISTORY_LIMIT = 100

WORKSPACE_LABELS = {
    "start": "Start",
    "design": "Design",
    "simulation": "Simulation",
    "verification": "Verification",
    "evidence": "Evidence",
    "reporting": "Reporting",
}


_UNIT_SUFFIXES = (
    ("_m3_h", "m³/h"),
    ("_m3_s", "m³/s"),
    ("_kg_m3", "kg/m³"),
    ("_m2_s", "m²/s"),
    ("_m2", "m²"),
    ("_m3", "m³"),
    ("_pa", "Pa"),
    ("_kw", "kW"),
    ("_w", "W"),
    ("_c", "°C"),
    ("_percent", "%"),
    ("_minutes", "min"),
    ("_um", "µm"),
    ("_m", "m"),
)


def unit_hint(path: str) -> str:
    key = path.rsplit(".", 1)[-1].split("[", 1)[0].lower()
    for suffix, unit in _UNIT_SUFFIXES:
        if key.endswith(suffix):
            return unit
    if key.endswith("_1_h") or key == "ach":
        return "1/h"
    return ""



def verification_history_requirement_rows(record: dict) -> list[dict]:
    """Project one validated retained record into read-only drill-down rows."""
    verification = record.get("verification")
    evidence = record.get("evidence")
    if not isinstance(verification, dict) or not isinstance(evidence, list):
        return []
    findings = verification.get("findings")
    if not isinstance(findings, list):
        return []

    evidence_by_id = {
        item["id"]: item
        for item in evidence
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and item["id"]
    }
    rows: list[dict] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        raw_evidence_ids = finding.get("evidence_ids", [])
        evidence_ids = (
            tuple(item for item in raw_evidence_ids if isinstance(item, str))
            if isinstance(raw_evidence_ids, list)
            else ()
        )
        rows.append(
            {
                "requirement_id": str(finding.get("requirement_id", "")),
                "subject_ref": copy.deepcopy(finding.get("subject_ref")),
                "status": str(finding.get("status", "")),
                "state": str(finding.get("state", "")),
                "criterion": copy.deepcopy(finding.get("criterion")),
                "actual": copy.deepcopy(finding.get("actual")),
                "unit": copy.deepcopy(finding.get("unit")),
                "included": bool(finding.get("included", False)),
                "explanation": str(finding.get("explanation", "")),
                "evidence_ids": evidence_ids,
                "evidence": tuple(
                    copy.deepcopy(evidence_by_id[evidence_id])
                    for evidence_id in evidence_ids
                    if evidence_id in evidence_by_id
                ),
            }
        )
    return rows


def _requirement_criterion_text(criterion: dict) -> str:
    parts: list[str] = []
    target = criterion.get("target")
    if target is not None:
        parts.append(
            "target="
            + json.dumps(
                target,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
        )
    minimum = criterion.get("minimum")
    if minimum is not None:
        parts.append(f"minimum={minimum:g}")
    maximum = criterion.get("maximum")
    if maximum is not None:
        parts.append(f"maximum={maximum:g}")
    tolerance = criterion.get("tolerance")
    if tolerance is not None:
        parts.append(f"tolerance={tolerance:g}")
    unit = criterion.get("unit")
    if unit is not None:
        parts.append(f"unit={unit}")
    return ", ".join(parts) if parts else "no explicit acceptance criterion"


def project_requirement_traceability_snapshot(
    project: ProjectDocument,
) -> dict:
    """Adapt the canonical project traceability projection for the desktop view."""
    traceability = build_project_requirements_traceability(project)
    summary = traceability["summary"]
    registries = traceability["registries"]

    requirement_by_id = {
        requirement["id"]: requirement
        for requirement in traceability["requirements"]
    }
    requirement_rows = []
    for requirement in traceability["requirements"]:
        requirement_set = requirement["set"]
        requirement_rows.append(
            {
                "id": requirement["id"],
                "title": requirement["title"],
                "set_id": requirement_set["id"],
                "set_title": requirement_set["title"],
                "status": requirement["status"],
                "applicability": requirement["applicability"],
                "scope": list(requirement["scope"]),
                "criterion": _requirement_criterion_text(
                    requirement["criterion"]
                ),
                "source": requirement["source"],
                "source_revision": requirement["source_revision"],
                "detail": {
                    "requirement_set": copy.deepcopy(requirement_set),
                    "requirement": copy.deepcopy(requirement),
                },
            }
        )

    mapping_rows = []
    for mapping in traceability["mappings"]:
        resolved_analysis = mapping["resolved_analysis"]
        mapping_rows.append(
            {
                "id": mapping["id"],
                "requirement_id": mapping["requirement_id"],
                "requirement_title": (
                    mapping["requirement_title"]
                    if mapping["requirement_title"] is not None
                    else mapping["requirement_id"]
                ),
                "analysis_id": mapping["analysis_id"],
                "analysis_name": (
                    resolved_analysis["name"]
                    if resolved_analysis is not None
                    else mapping["analysis_id"]
                ),
                "expected_analysis_kind": mapping["expected_analysis_kind"],
                "subject_ref": mapping["subject_ref"],
                "property_name": mapping["property_name"],
                "result_path": list(mapping["result_path"]),
                "status": mapping["status"],
                "reference_state": mapping["reference_state"],
                "detail": {
                    "mapping": copy.deepcopy(mapping),
                    "reference_state": mapping["reference_state"],
                    "analysis_reference_state": mapping[
                        "analysis_reference_state"
                    ],
                    "requirement_reference_state": mapping[
                        "requirement_reference_state"
                    ],
                    "resolved_requirement": copy.deepcopy(
                        requirement_by_id.get(mapping["requirement_id"])
                    ),
                    "resolved_analysis": copy.deepcopy(resolved_analysis),
                    "current_analysis_candidate": copy.deepcopy(
                        mapping["current_analysis_candidate"]
                    ),
                },
            }
        )

    return {
        "requirement_set_count": summary["requirement_set_count"],
        "requirement_count": summary["requirement_count"],
        "mapping_count": summary["mapping_count"],
        "active_mapping_count": summary["active_mapping_count"],
        "active_mapped_requirement_count": summary[
            "active_mapped_requirement_count"
        ],
        "requirements_sha256": registries["requirements_sha256"],
        "mappings_sha256": registries["mappings_sha256"],
        "requirements": requirement_rows,
        "mappings": mapping_rows,
    }

def flatten_json(value, path: str = "$") -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    if isinstance(value, dict):
        if not value:
            rows.append((path, "{}", ""))
        for key, item in value.items():
            child = f"{path}.{key}"
            rows.extend(flatten_json(item, child))
    elif isinstance(value, list):
        if not value:
            rows.append((path, "[]", ""))
        for index, item in enumerate(value):
            rows.extend(flatten_json(item, f"{path}[{index}]"))
    else:
        text = json.dumps(value, ensure_ascii=False)
        rows.append((path, text, unit_hint(path)))
    return rows


def structured_json_entries(
    value,
    path: str = "$",
    tokens: tuple[str | int, ...] = (),
) -> list[tuple[str, tuple[str | int, ...], object, str]]:
    """Return deterministic leaf/container rows with unambiguous edit tokens."""
    rows: list[tuple[str, tuple[str | int, ...], object, str]] = []
    if isinstance(value, dict):
        if not value:
            rows.append((path, tokens, {}, ""))
        for key, item in value.items():
            child = f"{path}.{key}"
            rows.extend(
                structured_json_entries(item, child, (*tokens, str(key)))
            )
    elif isinstance(value, list):
        if not value:
            rows.append((path, tokens, [], ""))
        for index, item in enumerate(value):
            rows.extend(
                structured_json_entries(
                    item,
                    f"{path}[{index}]",
                    (*tokens, index),
                )
            )
    else:
        rows.append((path, tokens, copy.deepcopy(value), unit_hint(path)))
    return rows


def replace_structured_json_value(
    payload: dict,
    tokens: tuple[str | int, ...],
    value,
) -> dict:
    """Return a detached payload with exactly one existing scalar leaf replaced."""
    if not isinstance(payload, dict):
        raise ValueError("analysis input must be a JSON object")
    if not tokens:
        raise ValueError("the analysis input root cannot be replaced")
    if isinstance(value, (dict, list)):
        raise ValueError("structured editing accepts scalar JSON values only")

    updated = copy.deepcopy(payload)
    target = updated
    for token in tokens[:-1]:
        if isinstance(token, int):
            if not isinstance(target, list) or not (0 <= token < len(target)):
                raise ValueError("structured input path no longer exists")
            target = target[token]
        else:
            if not isinstance(target, dict) or token not in target:
                raise ValueError("structured input path no longer exists")
            target = target[token]

    leaf = tokens[-1]
    if isinstance(leaf, int):
        if not isinstance(target, list) or not (0 <= leaf < len(target)):
            raise ValueError("structured input path no longer exists")
        if isinstance(target[leaf], (dict, list)):
            raise ValueError("structured editing accepts scalar leaves only")
        target[leaf] = copy.deepcopy(value)
    else:
        if not isinstance(target, dict) or leaf not in target:
            raise ValueError("structured input path no longer exists")
        if isinstance(target[leaf], (dict, list)):
            raise ValueError("structured editing accepts scalar leaves only")
        target[leaf] = copy.deepcopy(value)
    return updated


class AnalysisPicker(tk.Toplevel):
    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title("Add analysis")
        self.resizable(True, True)
        self.result: str | None = None
        self.transient(parent)
        self.grab_set()

        self._catalog = list(analysis_catalog())
        self.search_var = tk.StringVar()
        self.category_var = tk.StringVar(value="All")
        self.count_var = tk.StringVar()

        ttk.Label(
            self,
            text="Choose a CleanroomX backend workflow",
            style="CX.Section.TLabel",
        ).pack(anchor="w", padx=12, pady=(12, 6))

        filters = ttk.Frame(self)
        filters.pack(fill="x", padx=12, pady=(0, 6))
        ttk.Label(filters, text="Search").pack(side="left")
        self.search_entry = ttk.Entry(
            filters,
            textvariable=self.search_var,
            width=32,
        )
        self.search_entry.pack(side="left", padx=(4, 10))
        ttk.Label(filters, text="Category").pack(side="left")
        categories = sorted(
            {
                str(item.get("category", "")).strip()
                for item in self._catalog
                if str(item.get("category", "")).strip()
            },
            key=str.casefold,
        )
        self.category_combo = ttk.Combobox(
            filters,
            textvariable=self.category_var,
            values=("All", *categories),
            state="readonly",
            width=18,
        )
        self.category_combo.pack(side="left", padx=(4, 8))
        ttk.Button(
            filters,
            text="Clear",
            command=self._clear_filters,
        ).pack(side="left")
        ttk.Label(filters, textvariable=self.count_var).pack(side="right")

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=6)
        self.tree = ttk.Treeview(
            frame,
            columns=("category", "source", "description"),
            show="tree headings",
            height=14,
        )
        self.tree.heading("#0", text="Analysis")
        self.tree.heading("category", text="Category")
        self.tree.heading("source", text="Implementation")
        self.tree.heading("description", text="Description")
        self.tree.column("#0", width=230, stretch=False)
        self.tree.column("category", width=110, stretch=False)
        self.tree.column("source", width=180, stretch=False)
        self.tree.column("description", width=420, stretch=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=(6, 12))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        self.add_button = ttk.Button(
            buttons,
            text="Add",
            command=self._accept,
            style="CX.Primary.TButton",
        )
        self.add_button.pack(side="right", padx=(0, 6))

        self.search_var.trace_add("write", lambda *_: self._populate())
        self.category_var.trace_add("write", lambda *_: self._populate())
        self.tree.bind("<Double-1>", lambda event: self._accept())
        self.tree.bind("<Return>", lambda event: self._accept())
        self.bind("<Escape>", lambda event: self.destroy())
        self._populate()

        self.geometry("1020x500")
        self.minsize(760, 420)
        self.search_entry.focus_set()

    @staticmethod
    def _catalog_source(item: dict) -> str:
        source = "Built-in"
        plugin = item.get("plugin")
        if isinstance(plugin, dict):
            identity = (
                plugin.get("distribution_name")
                or plugin.get("entry_point_name")
                or item["key"]
            )
            version = plugin.get("distribution_version")
            source = f"Plugin: {identity}" + (
                f" {version}" if version else ""
            )
        return source

    def _filtered_catalog(self) -> list[dict]:
        query = self.search_var.get().strip().casefold()
        category = self.category_var.get().strip().casefold()
        visible = []
        for item in self._catalog:
            item_category = str(item.get("category", ""))
            if category and category != "all" and item_category.casefold() != category:
                continue
            if query:
                haystack = " ".join(
                    (
                        str(item.get("key", "")),
                        str(item.get("title", "")),
                        item_category,
                        str(item.get("description", "")),
                        self._catalog_source(item),
                    )
                ).casefold()
                if query not in haystack:
                    continue
            visible.append(item)
        return visible

    def _populate(self) -> None:
        previous = self.tree.selection()
        selected = previous[0] if previous else None
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        visible = self._filtered_catalog()
        for item in visible:
            self.tree.insert(
                "",
                "end",
                iid=item["key"],
                text=item["title"],
                values=(
                    item["category"],
                    self._catalog_source(item),
                    item["description"],
                ),
            )

        self.count_var.set(f"{len(visible)} of {len(self._catalog)} workflows")
        children = self.tree.get_children()
        if selected and self.tree.exists(selected):
            target = selected
        else:
            target = children[0] if children else None
        if target is not None:
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
        self.add_button.configure(state="normal" if children else "disabled")

    def _clear_filters(self) -> None:
        self.search_var.set("")
        self.category_var.set("All")
        self.search_entry.focus_set()

    def _accept(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        self.result = selection[0]
        self.destroy()


class RunHistoryDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, metadata: dict):
        super().__init__(parent)
        self.title("Analysis Run History")
        self.geometry("1180x700")
        self.minsize(900, 520)
        self.transient(parent)

        summary = validate_run_history(metadata)
        self.records = run_history_records(metadata)
        self.search_var = tk.StringVar()
        self.status_filter_var = tk.StringVar(value="All")
        self.count_var = tk.StringVar()

        ttk.Label(
            self,
            text=(
                f"Verified retained digest chain — {summary['record_count']} record(s). "
                "Digests detect accidental corruption; they are not authenticity signatures."
            ),
        ).pack(fill="x", padx=10, pady=(10, 6))

        filters = ttk.Frame(self)
        filters.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(filters, text="Search").pack(side="left")
        self.search_entry = ttk.Entry(
            filters,
            textvariable=self.search_var,
            width=34,
        )
        self.search_entry.pack(side="left", padx=(4, 10))
        ttk.Label(filters, text="Status").pack(side="left")
        statuses = sorted(
            {
                str(record.get("status", "")).strip()
                for record in self.records
                if str(record.get("status", "")).strip()
            },
            key=str.casefold,
        )
        self.status_combo = ttk.Combobox(
            filters,
            textvariable=self.status_filter_var,
            values=("All", *statuses),
            state="readonly",
            width=16,
        )
        self.status_combo.pack(side="left", padx=(4, 8))
        ttk.Button(
            filters,
            text="Clear",
            command=self._clear_filters,
        ).pack(side="left")
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
        ttk.Button(
            filters,
            text="Copy record",
            command=self._copy_selected,
        ).pack(side="left", padx=2)
        ttk.Label(filters, textvariable=self.count_var).pack(side="right")

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        list_frame = ttk.Frame(body)
        detail_frame = ttk.Frame(body)
        body.add(list_frame, weight=1)
        body.add(detail_frame, weight=2)

        self.tree = ttk.Treeview(
            list_frame,
            columns=("time", "analysis", "kind", "status", "input"),
            show="tree headings",
            height=10,
        )
        self.tree.heading("#0", text="#")
        self.tree.heading("time", text="Completed UTC")
        self.tree.heading("analysis", text="Analysis")
        self.tree.heading("kind", text="Kind")
        self.tree.heading("status", text="Status")
        self.tree.heading("input", text="Input SHA-256")
        self.tree.column("#0", width=55, stretch=False)
        self.tree.column("time", width=185, stretch=False)
        self.tree.column("analysis", width=230)
        self.tree.column("kind", width=190)
        self.tree.column("status", width=120, stretch=False)
        self.tree.column("input", width=165, stretch=False)
        list_scroll = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.tree.yview
        )
        list_scroll_x = ttk.Scrollbar(
            list_frame, orient="horizontal", command=self.tree.xview
        )
        self.tree.configure(
            yscrollcommand=list_scroll.set,
            xscrollcommand=list_scroll_x.set,
        )
        self.tree.grid(row=0, column=0, sticky="nsew")
        list_scroll.grid(row=0, column=1, sticky="ns")
        list_scroll_x.grid(row=1, column=0, sticky="ew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.detail = tk.Text(detail_frame, wrap="none")
        detail_scroll = ttk.Scrollbar(
            detail_frame, orient="vertical", command=self.detail.yview
        )
        detail_scroll_x = ttk.Scrollbar(
            detail_frame, orient="horizontal", command=self.detail.xview
        )
        self.detail.configure(
            yscrollcommand=detail_scroll.set,
            xscrollcommand=detail_scroll_x.set,
        )
        self.detail.grid(row=0, column=0, sticky="nsew")
        detail_scroll.grid(row=0, column=1, sticky="ns")
        detail_scroll_x.grid(row=1, column=0, sticky="ew")
        detail_frame.rowconfigure(0, weight=1)
        detail_frame.columnconfigure(0, weight=1)

        self.search_var.trace_add("write", lambda *_: self._populate())
        self.status_filter_var.trace_add("write", lambda *_: self._populate())
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)
        self.tree.bind("<F4>", lambda event: self._select_relative(1))
        self.tree.bind("<Shift-F4>", lambda event: self._select_relative(-1))
        self.tree.bind("<Control-c>", lambda event: self._copy_selected())
        self.bind("<Escape>", lambda event: self.destroy())

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

        self._populate()

    def _filtered_records(self) -> list[dict]:
        query = self.search_var.get().strip().casefold()
        status = self.status_filter_var.get().strip().casefold()
        visible = []
        for record in reversed(self.records):
            record_status = str(record.get("status", ""))
            if status and status != "all" and record_status.casefold() != status:
                continue
            if query:
                haystack = " ".join(
                    (
                        str(record.get("sequence", "")),
                        str(record.get("completed_at_utc", "")),
                        str(record.get("analysis_name", "")),
                        str(record.get("analysis_kind", "")),
                        record_status,
                        str(record.get("input_sha256", "")),
                    )
                ).casefold()
                if query not in haystack:
                    continue
            visible.append(record)
        return visible

    def _populate(self) -> None:
        selection = self.tree.selection()
        selected = selection[0] if selection else None
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        visible = self._filtered_records()
        for record in visible:
            self.tree.insert(
                "",
                "end",
                iid=str(record["sequence"]),
                text=str(record["sequence"]),
                values=(
                    record["completed_at_utc"],
                    record["analysis_name"],
                    record["analysis_kind"],
                    record["status"],
                    record["input_sha256"][:16] + "…",
                ),
            )
        self.count_var.set(f"{len(visible)} of {len(self.records)} records")

        children = self.tree.get_children()
        if selected and self.tree.exists(selected):
            target = selected
        else:
            target = children[0] if children else None
        if target is not None:
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
        self._show_selected()

    def _clear_filters(self) -> None:
        self.search_var.set("")
        self.status_filter_var.set("All")
        self.search_entry.focus_set()

    def _selected_record(self) -> dict | None:
        selection = self.tree.selection()
        if not selection:
            return None
        sequence = int(selection[0])
        return next(
            (item for item in self.records if item["sequence"] == sequence),
            None,
        )

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
        self._show_selected()
        return "break"

    def _copy_selected(self) -> None:
        record = self._selected_record()
        if record is None:
            return
        payload = json.dumps(
            record,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        self.clipboard_clear()
        self.clipboard_append(payload)

    def _show_selected(self, event=None) -> None:
        record = self._selected_record()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if record is not None:
            self.detail.insert(
                "1.0",
                json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False),
            )
        elif self.records and not self._filtered_records():
            self.detail.insert(
                "1.0",
                "No retained run records match the active filters.",
            )
        else:
            self.detail.insert("1.0", "No retained run records are available.")
        self.detail.configure(state="disabled")


class VerificationHistoryDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        project: ProjectDocument,
        *,
        base_dir: str | Path | None = None,
    ):
        super().__init__(parent)
        self.title("Project Verification History")
        self.geometry("1460x800")
        self.minsize(1080, 600)
        self.transient(parent)

        metadata = project.metadata
        summary = validate_project_verification_run_history(metadata)
        self.records = verification_run_history_records(metadata)
        currency = assess_project_verification_currency(
            project,
            base_dir=base_dir,
        )
        self.currency_by_analysis = {
            item["analysis_id"]: item
            for item in currency.get("analyses", [])
        }
        self._context_by_sequence = {
            record["sequence"]: verification_history_record_currency_context(
                record,
                self.currency_by_analysis.get(record["analysis_id"]),
            )
            for record in self.records
        }
        self.search_var = tk.StringVar()
        self.status_filter_var = tk.StringVar(value="All")
        self.currency_filter_var = tk.StringVar(value="All")
        self.count_var = tk.StringVar()

        ttk.Label(
            self,
            text=(
                f"Verified retained verification chain — {summary['record_count']} record(s). "
                "Hashes provide tamper evidence, not signer authentication."
            ),
        ).pack(fill="x", padx=10, pady=(10, 3))
        ttk.Label(
            self,
            text=(
                "Historical status is immutable evidence. Current currency is shown "
                "only for each analysis's latest retained record; older records are "
                "labeled historical."
            ),
        ).pack(fill="x", padx=10, pady=(0, 6))

        filters = ttk.Frame(self)
        filters.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(filters, text="Search").pack(side="left")
        self.search_entry = ttk.Entry(
            filters,
            textvariable=self.search_var,
            width=30,
        )
        self.search_entry.pack(side="left", padx=(4, 8))

        statuses = sorted(
            {
                str(record.get("verification", {}).get("status", "")).strip()
                for record in self.records
                if isinstance(record.get("verification"), dict)
                and str(record["verification"].get("status", "")).strip()
            },
            key=str.casefold,
        )
        ttk.Label(filters, text="Historical status").pack(side="left")
        self.status_combo = ttk.Combobox(
            filters,
            textvariable=self.status_filter_var,
            values=("All", *statuses),
            state="readonly",
            width=14,
        )
        self.status_combo.pack(side="left", padx=(4, 8))

        currencies = sorted(
            {
                str(context.get("state", "")).strip()
                for context in self._context_by_sequence.values()
                if str(context.get("state", "")).strip()
            },
            key=str.casefold,
        )
        ttk.Label(filters, text="Currency").pack(side="left")
        self.currency_combo = ttk.Combobox(
            filters,
            textvariable=self.currency_filter_var,
            values=("All", *currencies),
            state="readonly",
            width=22,
        )
        self.currency_combo.pack(side="left", padx=(4, 8))
        ttk.Button(
            filters,
            text="Clear",
            command=self._clear_filters,
        ).pack(side="left")
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
        ttk.Button(
            filters,
            text="Copy record",
            command=self._copy_selected,
        ).pack(side="left", padx=2)
        ttk.Label(filters, textvariable=self.count_var).pack(side="right")

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        list_frame = ttk.Frame(body)
        detail_frame = ttk.Frame(body)
        body.add(list_frame, weight=1)
        body.add(detail_frame, weight=2)

        self.tree = ttk.Treeview(
            list_frame,
            columns=(
                "time",
                "analysis",
                "kind",
                "status",
                "currency",
                "verified",
                "identity",
            ),
            show="tree headings",
            height=10,
        )
        self.tree.heading("#0", text="#")
        self.tree.heading("time", text="Completed UTC")
        self.tree.heading("analysis", text="Analysis")
        self.tree.heading("kind", text="Kind")
        self.tree.heading("status", text="Historical status")
        self.tree.heading("currency", text="Current currency")
        self.tree.heading("verified", text="Verified")
        self.tree.heading("identity", text="Verification identity")
        self.tree.column("#0", width=55, stretch=False)
        self.tree.column("time", width=185, stretch=False)
        self.tree.column("analysis", width=210)
        self.tree.column("kind", width=165)
        self.tree.column("status", width=115, stretch=False)
        self.tree.column("currency", width=245, stretch=False)
        self.tree.column("verified", width=80, stretch=False)
        self.tree.column("identity", width=175, stretch=False)

        list_scroll = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        list_scroll_x = ttk.Scrollbar(
            list_frame,
            orient="horizontal",
            command=self.tree.xview,
        )
        self.tree.configure(
            yscrollcommand=list_scroll.set,
            xscrollcommand=list_scroll_x.set,
        )
        self.tree.grid(row=0, column=0, sticky="nsew")
        list_scroll.grid(row=0, column=1, sticky="ns")
        list_scroll_x.grid(row=1, column=0, sticky="ew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        detail_tabs = ttk.Notebook(detail_frame)
        detail_tabs.pack(fill="both", expand=True)

        evidence_tab = ttk.Frame(detail_tabs)
        record_tab = ttk.Frame(detail_tabs)
        detail_tabs.add(evidence_tab, text="Requirement Evidence")
        detail_tabs.add(record_tab, text="Canonical Record")

        ttk.Label(
            evidence_tab,
            text=(
                "Read-only historical requirement → evidence → verdict projection. "
                "No verdict is recomputed from current project state."
            ),
        ).pack(fill="x", padx=8, pady=(8, 4))

        evidence_frame = ttk.Frame(evidence_tab)
        evidence_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.requirement_tree = ttk.Treeview(
            evidence_frame,
            columns=(
                "subject",
                "verdict",
                "state",
                "criterion",
                "actual",
                "unit",
                "freshness",
                "source",
            ),
            show="tree headings",
        )
        self.requirement_tree.heading("#0", text="Requirement / Evidence")
        self.requirement_tree.heading("subject", text="Subject")
        self.requirement_tree.heading("verdict", text="Verdict")
        self.requirement_tree.heading("state", text="State")
        self.requirement_tree.heading("criterion", text="Criterion")
        self.requirement_tree.heading("actual", text="Actual")
        self.requirement_tree.heading("unit", text="Unit")
        self.requirement_tree.heading("freshness", text="Freshness")
        self.requirement_tree.heading("source", text="Evidence source / locator")
        self.requirement_tree.column("#0", width=210)
        self.requirement_tree.column("subject", width=120, stretch=False)
        self.requirement_tree.column("verdict", width=85, stretch=False)
        self.requirement_tree.column("state", width=105, stretch=False)
        self.requirement_tree.column("criterion", width=230)
        self.requirement_tree.column("actual", width=150)
        self.requirement_tree.column("unit", width=80, stretch=False)
        self.requirement_tree.column("freshness", width=105, stretch=False)
        self.requirement_tree.column("source", width=330)

        evidence_scroll_y = ttk.Scrollbar(
            evidence_frame,
            orient="vertical",
            command=self.requirement_tree.yview,
        )
        evidence_scroll_x = ttk.Scrollbar(
            evidence_frame,
            orient="horizontal",
            command=self.requirement_tree.xview,
        )
        self.requirement_tree.configure(
            yscrollcommand=evidence_scroll_y.set,
            xscrollcommand=evidence_scroll_x.set,
        )
        self.requirement_tree.grid(row=0, column=0, sticky="nsew")
        evidence_scroll_y.grid(row=0, column=1, sticky="ns")
        evidence_scroll_x.grid(row=1, column=0, sticky="ew")
        evidence_frame.rowconfigure(0, weight=1)
        evidence_frame.columnconfigure(0, weight=1)

        self.detail = tk.Text(record_tab, wrap="none")
        detail_scroll_y = ttk.Scrollbar(
            record_tab,
            orient="vertical",
            command=self.detail.yview,
        )
        detail_scroll_x = ttk.Scrollbar(
            record_tab,
            orient="horizontal",
            command=self.detail.xview,
        )
        self.detail.configure(
            yscrollcommand=detail_scroll_y.set,
            xscrollcommand=detail_scroll_x.set,
        )
        self.detail.grid(row=0, column=0, sticky="nsew")
        detail_scroll_y.grid(row=0, column=1, sticky="ns")
        detail_scroll_x.grid(row=1, column=0, sticky="ew")
        record_tab.rowconfigure(0, weight=1)
        record_tab.columnconfigure(0, weight=1)

        for variable in (
            self.search_var,
            self.status_filter_var,
            self.currency_filter_var,
        ):
            variable.trace_add("write", lambda *_: self._populate_records())
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)
        self.tree.bind("<F4>", lambda event: self._select_relative(1))
        self.tree.bind("<Shift-F4>", lambda event: self._select_relative(-1))
        self.tree.bind("<Control-c>", lambda event: self._copy_selected())
        self.bind("<Escape>", lambda event: self.destroy())

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

        self._populate_records()

    @staticmethod
    def _display_value(value) -> str:
        if value is None:
            return ""
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _currency_text(context: dict) -> str:
        text = str(context.get("state", "unknown"))
        mismatch_reasons = context.get("mismatch_reasons", [])
        if mismatch_reasons:
            text += " (" + ", ".join(
                str(reason) for reason in mismatch_reasons
            ) + ")"
        return text

    def _filtered_records(self) -> list[dict]:
        query = self.search_var.get().strip().casefold()
        status = self.status_filter_var.get().strip().casefold()
        currency = self.currency_filter_var.get().strip().casefold()
        visible = []
        for record in reversed(self.records):
            verification = record.get("verification")
            if not isinstance(verification, dict):
                continue
            record_status = str(verification.get("status", ""))
            context = self._context_by_sequence.get(record["sequence"], {})
            context_state = str(context.get("state", ""))
            if status and status != "all" and record_status.casefold() != status:
                continue
            if currency and currency != "all" and context_state.casefold() != currency:
                continue
            if query:
                haystack = " ".join(
                    (
                        str(record.get("sequence", "")),
                        str(record.get("completed_at_utc", "")),
                        str(record.get("analysis_name", "")),
                        str(record.get("analysis_kind", "")),
                        record_status,
                        self._currency_text(context),
                        "verified" if verification.get("verified") else "not verified",
                        str(record.get("verification_identity_sha256", "")),
                    )
                ).casefold()
                if query not in haystack:
                    continue
            visible.append(record)
        return visible

    def _populate_records(self) -> None:
        selection = self.tree.selection()
        selected = selection[0] if selection else None
        for item in self.tree.get_children():
            self.tree.delete(item)

        visible = self._filtered_records()
        for record in visible:
            verification = record["verification"]
            context = self._context_by_sequence.get(record["sequence"], {})
            self.tree.insert(
                "",
                "end",
                iid=str(record["sequence"]),
                text=str(record["sequence"]),
                values=(
                    record["completed_at_utc"],
                    record["analysis_name"],
                    record["analysis_kind"],
                    verification["status"],
                    self._currency_text(context),
                    "yes" if verification["verified"] else "no",
                    record["verification_identity_sha256"][:16] + "…",
                ),
            )
        self.count_var.set(f"{len(visible)} of {len(self.records)} records")

        children = self.tree.get_children()
        if selected and self.tree.exists(selected):
            target = selected
        else:
            target = children[0] if children else None
        if target is not None:
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
        self._show_selected()

    def _clear_filters(self) -> None:
        self.search_var.set("")
        self.status_filter_var.set("All")
        self.currency_filter_var.set("All")
        self.search_entry.focus_set()

    def _selected_record(self) -> dict | None:
        selection = self.tree.selection()
        if not selection:
            return None
        sequence = int(selection[0])
        return next(
            (item for item in self.records if item["sequence"] == sequence),
            None,
        )

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
        self._show_selected()
        return "break"

    def _copy_selected(self) -> None:
        record = self._selected_record()
        if record is None:
            return
        self.clipboard_clear()
        self.clipboard_append(
            json.dumps(
                record,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )

    def _show_selected(self, event=None) -> None:
        record = self._selected_record()

        for item in self.requirement_tree.get_children():
            self.requirement_tree.delete(item)
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")

        if record is None:
            if self.records and not self._filtered_records():
                self.detail.insert(
                    "1.0",
                    "No retained verification records match the active filters.",
                )
            else:
                self.detail.insert(
                    "1.0",
                    "No retained verification records are available.",
                )
            self.detail.configure(state="disabled")
            return

        for index, row in enumerate(verification_history_requirement_rows(record)):
            parent_id = f"finding:{index}"
            subject = row["subject_ref"] if row["subject_ref"] is not None else "project"
            self.requirement_tree.insert(
                "",
                "end",
                iid=parent_id,
                text=row["requirement_id"],
                open=True,
                values=(
                    subject,
                    row["status"],
                    row["state"],
                    self._display_value(row["criterion"]),
                    self._display_value(row["actual"]),
                    row["unit"] or "",
                    "",
                    row["explanation"],
                ),
            )
            retained_by_id = {
                item.get("id"): item
                for item in row["evidence"]
                if isinstance(item, dict)
            }
            if not row["evidence_ids"]:
                self.requirement_tree.insert(
                    parent_id,
                    "end",
                    text="No bound evidence",
                    values=("", "", "", "", "", "", "", ""),
                )
                continue
            for evidence_index, evidence_id in enumerate(row["evidence_ids"]):
                evidence = retained_by_id.get(evidence_id)
                if evidence is None:
                    self.requirement_tree.insert(
                        parent_id,
                        "end",
                        iid=f"{parent_id}:missing:{evidence_index}",
                        text=evidence_id,
                        values=(
                            "",
                            "",
                            "missing",
                            "",
                            "",
                            "",
                            "",
                            "Referenced evidence is not retained in this record.",
                        ),
                    )
                    continue
                source = str(evidence.get("source", ""))
                locator = str(evidence.get("evidence_locator", ""))
                source_locator = source
                if locator:
                    source_locator += (" · " if source_locator else "") + locator
                evidence_subject = evidence.get("subject_ref")
                self.requirement_tree.insert(
                    parent_id,
                    "end",
                    iid=f"{parent_id}:evidence:{evidence_index}",
                    text=evidence_id,
                    values=(
                        evidence_subject if evidence_subject is not None else "project",
                        "",
                        "",
                        "",
                        self._display_value(evidence.get("value")),
                        evidence.get("unit") or "",
                        evidence.get("freshness") or "",
                        source_locator,
                    ),
                )

        self.detail.insert(
            "1.0",
            json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False),
        )
        self.detail.configure(state="disabled")


class RequirementsTraceabilityDialog(tk.Toplevel):
    """Read-only project requirements and evidence-routing inspection."""

    def __init__(self, parent: tk.Misc, snapshot: dict):
        super().__init__(parent)
        self.title("Project Requirements Traceability")
        self.geometry("1480x780")
        self.minsize(1080, 580)
        self.transient(parent)
        self._details: dict[str, dict] = {}
        self._traceability_rows: dict[str, dict[str, str]] = {}
        self.search_var = tk.StringVar()
        self.type_filter_var = tk.StringVar(value="All")
        self.count_var = tk.StringVar()

        ttk.Label(
            self,
            text=(
                f"Requirement sets: {snapshot['requirement_set_count']} · "
                f"Requirements: {snapshot['requirement_count']} · "
                f"Mappings: {snapshot['mapping_count']} "
                f"({snapshot['active_mapping_count']} active) · "
                f"Actively mapped requirements: "
                f"{snapshot['active_mapped_requirement_count']}"
            ),
            style="CX.Section.TLabel",
        ).pack(anchor="w", padx=10, pady=(10, 3))

        ttk.Label(
            self,
            text=(
                "Requirements SHA-256: "
                f"{snapshot.get('requirements_sha256') or 'not configured'}\n"
                "Mappings SHA-256: "
                f"{snapshot.get('mappings_sha256') or 'not configured'}"
            ),
            wraplength=1420,
        ).pack(anchor="w", padx=10, pady=(0, 6))

        ttk.Label(
            self,
            text=(
                "Read-only canonical project data. This view does not infer "
                "requirements, change acceptance criteria, or rewrite mappings."
            ),
        ).pack(anchor="w", padx=10, pady=(0, 6))

        filters = ttk.Frame(self)
        filters.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(filters, text="Search").pack(side="left")
        self.search_entry = ttk.Entry(
            filters,
            textvariable=self.search_var,
            width=34,
        )
        self.search_entry.pack(side="left", padx=(4, 8))
        ttk.Label(filters, text="Type").pack(side="left")
        self.type_combo = ttk.Combobox(
            filters,
            textvariable=self.type_filter_var,
            values=("All", "Requirement", "Mapping"),
            state="readonly",
            width=14,
        )
        self.type_combo.pack(side="left", padx=(4, 8))
        ttk.Button(
            filters,
            text="Clear",
            command=self._clear_filters,
        ).pack(side="left")
        ttk.Button(
            filters,
            text="Expand all",
            command=lambda: self._set_roots_open(True),
        ).pack(side="left", padx=(10, 2))
        ttk.Button(
            filters,
            text="Collapse all",
            command=lambda: self._set_roots_open(False),
        ).pack(side="left", padx=2)
        ttk.Label(filters, textvariable=self.count_var).pack(side="right")

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        tree_frame = ttk.Frame(body)
        detail_frame = ttk.Frame(body)
        body.add(tree_frame, weight=2)
        body.add(detail_frame, weight=2)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("type", "title", "status", "scope", "analysis", "criterion"),
            show="tree headings",
        )
        self.tree.heading("#0", text="ID")
        self.tree.heading("type", text="Type")
        self.tree.heading("title", text="Requirement / property")
        self.tree.heading("status", text="Status")
        self.tree.heading("scope", text="Scope / subject")
        self.tree.heading("analysis", text="Analysis")
        self.tree.heading("criterion", text="Criterion / result path")
        self.tree.column("#0", width=190)
        self.tree.column("type", width=110, stretch=False)
        self.tree.column("title", width=260)
        self.tree.column("status", width=150, stretch=False)
        self.tree.column("scope", width=175)
        self.tree.column("analysis", width=240)
        self.tree.column("criterion", width=360)

        tree_scroll_y = ttk.Scrollbar(
            tree_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        tree_scroll_x = ttk.Scrollbar(
            tree_frame,
            orient="horizontal",
            command=self.tree.xview,
        )
        self.tree.configure(
            yscrollcommand=tree_scroll_y.set,
            xscrollcommand=tree_scroll_x.set,
        )
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        tree_scroll_x.grid(row=1, column=0, sticky="ew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.requirements_root = "traceability:requirements"
        self.mappings_root = "traceability:mappings"
        self.tree.insert(
            "",
            "end",
            iid=self.requirements_root,
            text="Requirements",
            values=(
                "Registry",
                f"{snapshot['requirement_count']} requirement(s)",
                "",
                "",
                "",
                "",
            ),
            open=True,
        )
        self._details[self.requirements_root] = {
            "requirements_sha256": snapshot.get("requirements_sha256"),
            "requirement_set_count": snapshot["requirement_set_count"],
            "requirement_count": snapshot["requirement_count"],
        }
        for item in snapshot["requirements"]:
            iid = f"requirement:{item['id']}"
            scope_text = ", ".join(item["scope"]) if item["scope"] else "project"
            self.tree.insert(
                self.requirements_root,
                "end",
                iid=iid,
                text=item["id"],
                values=(
                    "Requirement",
                    item["title"],
                    f"{item['status']} / {item['applicability']}",
                    scope_text,
                    "",
                    item["criterion"],
                ),
            )
            self._details[iid] = item["detail"]
            self._index_traceability_row(
                iid,
                self.requirements_root,
                "Requirement",
            )

        self.tree.insert(
            "",
            "end",
            iid=self.mappings_root,
            text="Evidence mappings",
            values=(
                "Registry",
                f"{snapshot['mapping_count']} mapping(s)",
                f"{snapshot['active_mapping_count']} active",
                "",
                "",
                "",
            ),
            open=True,
        )
        self._details[self.mappings_root] = {
            "mappings_sha256": snapshot.get("mappings_sha256"),
            "mapping_count": snapshot["mapping_count"],
            "active_mapping_count": snapshot["active_mapping_count"],
            "active_mapped_requirement_count": snapshot[
                "active_mapped_requirement_count"
            ],
        }
        for item in snapshot["mappings"]:
            iid = f"mapping:{item['id']}"
            subject = item["subject_ref"] or "project"
            analysis_text = (
                f"{item['analysis_name']} [{item['analysis_id']}]"
                if item["analysis_name"] != item["analysis_id"]
                else item["analysis_id"]
            )
            result_path = json.dumps(
                item["result_path"],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            self.tree.insert(
                self.mappings_root,
                "end",
                iid=iid,
                text=item["id"],
                values=(
                    "Mapping",
                    f"{item['requirement_title']} → {item['property_name']}",
                    f"{item['status']} / {item['reference_state']}",
                    subject,
                    analysis_text,
                    result_path,
                ),
            )
            self._details[iid] = item["detail"]
            self._index_traceability_row(
                iid,
                self.mappings_root,
                "Mapping",
            )

        self.detail = tk.Text(detail_frame, wrap="none")
        detail_scroll_y = ttk.Scrollbar(
            detail_frame,
            orient="vertical",
            command=self.detail.yview,
        )
        detail_scroll_x = ttk.Scrollbar(
            detail_frame,
            orient="horizontal",
            command=self.detail.xview,
        )
        self.detail.configure(
            yscrollcommand=detail_scroll_y.set,
            xscrollcommand=detail_scroll_x.set,
        )
        self.detail.grid(row=0, column=0, sticky="nsew")
        detail_scroll_y.grid(row=0, column=1, sticky="ns")
        detail_scroll_x.grid(row=1, column=0, sticky="ew")
        detail_frame.rowconfigure(0, weight=1)
        detail_frame.columnconfigure(0, weight=1)
        self.detail.configure(state="disabled")

        self.search_var.trace_add("write", lambda *_: self._apply_filter())
        self.type_filter_var.trace_add("write", lambda *_: self._apply_filter())
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)
        self.bind("<Control-f>", lambda event: self.search_entry.focus_set())
        self.bind("<Escape>", lambda event: self.destroy())

        self._apply_filter()

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

    def _index_traceability_row(
        self,
        iid: str,
        parent: str,
        kind: str,
    ) -> None:
        item = self.tree.item(iid)
        detail = self._details.get(iid, {})
        search_text = " ".join(
            (
                iid,
                str(item.get("text", "")),
                " ".join(str(value) for value in item.get("values", ())),
                json.dumps(
                    detail,
                    ensure_ascii=False,
                    sort_keys=True,
                    allow_nan=False,
                ),
            )
        ).casefold()
        self._traceability_rows[iid] = {
            "parent": parent,
            "kind": kind,
            "search_text": search_text,
        }

    def _visible_traceability_rows(self) -> list[str]:
        query = self.search_var.get().strip().casefold()
        kind = self.type_filter_var.get().strip().casefold()
        visible = []
        for iid, row in self._traceability_rows.items():
            if kind and kind != "all" and row["kind"].casefold() != kind:
                continue
            if query and query not in row["search_text"]:
                continue
            visible.append(iid)
        return visible

    def _apply_filter(self) -> None:
        selection = self.tree.selection()
        selected = selection[0] if selection else None
        for iid in self._traceability_rows:
            self.tree.detach(iid)

        visible = self._visible_traceability_rows()
        for iid in visible:
            row = self._traceability_rows[iid]
            self.tree.move(iid, row["parent"], "end")

        self.count_var.set(
            f"{len(visible)} of {len(self._traceability_rows)} traceability rows"
        )
        self._set_roots_open(True)

        if selected in visible or selected in (
            self.requirements_root,
            self.mappings_root,
        ):
            target = selected
        elif visible:
            target = visible[0]
        else:
            target = self.requirements_root
        self.tree.selection_set(target)
        self.tree.focus(target)
        self.tree.see(target)
        self._show_selected()

    def _clear_filters(self) -> None:
        self.search_var.set("")
        self.type_filter_var.set("All")
        self.search_entry.focus_set()

    def _set_roots_open(self, opened: bool) -> None:
        self.tree.item(self.requirements_root, open=opened)
        self.tree.item(self.mappings_root, open=opened)

    def focus_requirement(self, requirement_id: str) -> bool:
        """Reveal and focus one canonical requirement without mutating the registry."""
        iid = f"requirement:{str(requirement_id).strip()}"
        if iid not in self._traceability_rows:
            return False
        self.search_var.set("")
        self.type_filter_var.set("All")
        # Trace callbacks rebuild the tree synchronously; explicitly reattach for
        # compatibility with lightweight/fake Tk variables used by unit tests.
        row = self._traceability_rows[iid]
        self.tree.move(iid, row["parent"], "end")
        self.tree.item(self.requirements_root, open=True)
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self._show_selected()
        return True

    def focus_mapping(self, mapping_id: str) -> bool:
        """Reveal and focus one canonical requirement-to-evidence mapping."""
        iid = f"mapping:{str(mapping_id).strip()}"
        if iid not in self._traceability_rows:
            return False
        self.search_var.set("")
        self.type_filter_var.set("All")
        row = self._traceability_rows[iid]
        self.tree.move(iid, row["parent"], "end")
        self.tree.item(self.mappings_root, open=True)
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self._show_selected()
        return True

    def _show_selected(self, event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        detail = self._details.get(selection[0], {})
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if detail:
            self.detail.insert(
                "1.0",
                json.dumps(
                    detail,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                ),
            )
        else:
            self.detail.insert("1.0", "No canonical detail is available for this row.")
        self.detail.configure(state="disabled")


class IfcReimportPlanDialog(tk.Toplevel):
    """Read-only review of the deterministic IFC re-import plan."""

    def __init__(self, parent: tk.Misc, report: dict):
        super().__init__(parent)
        self.title("IFC Re-import Plan")
        self.geometry("1120x700")
        self.minsize(820, 500)
        self.transient(parent)
        self.grab_set()

        self.changes = [
            item
            for item in report.get("changes", ())
            if isinstance(item, dict)
        ]
        self._change_by_iid: dict[str, dict] = {}
        self.search_var = tk.StringVar()
        self.action_filter_var = tk.StringVar(value="All")
        self.kind_filter_var = tk.StringVar(value="All")
        self.count_var = tk.StringVar()

        can_apply = bool(report.get("can_apply"))
        conflict_count = int(report.get("conflict_count", 0))
        status = (
            "Ready to apply"
            if can_apply
            else f"Blocked — {conflict_count} conflict(s) or invalid merged layout"
        )
        ttk.Label(
            self,
            text=status,
            style="CX.Section.TLabel",
        ).pack(anchor="w", padx=12, pady=(12, 4))

        summary = report.get("summary", {})
        if isinstance(summary, dict) and summary:
            summary_text = " · ".join(
                f"{key}: {summary[key]}" for key in sorted(summary)
            )
        else:
            summary_text = "No IFC entity changes detected."
        ttk.Label(
            self,
            text=summary_text,
            wraplength=1060,
        ).pack(anchor="w", padx=12, pady=(0, 8))

        filters = ttk.Frame(self)
        filters.pack(fill="x", padx=12, pady=(0, 6))
        ttk.Label(filters, text="Search").pack(side="left")
        self.search_entry = ttk.Entry(
            filters,
            textvariable=self.search_var,
            width=30,
        )
        self.search_entry.pack(side="left", padx=(4, 8))

        actions = sorted(
            {
                str(item.get("action", "")).strip()
                for item in self.changes
                if str(item.get("action", "")).strip()
            },
            key=str.casefold,
        )
        ttk.Label(filters, text="Action").pack(side="left")
        self.action_combo = ttk.Combobox(
            filters,
            textvariable=self.action_filter_var,
            values=("All", *actions),
            state="readonly",
            width=14,
        )
        self.action_combo.pack(side="left", padx=(4, 8))

        kinds = sorted(
            {
                str(item.get("kind", "")).strip()
                for item in self.changes
                if str(item.get("kind", "")).strip()
            },
            key=str.casefold,
        )
        ttk.Label(filters, text="Kind").pack(side="left")
        self.kind_combo = ttk.Combobox(
            filters,
            textvariable=self.kind_filter_var,
            values=("All", *kinds),
            state="readonly",
            width=14,
        )
        self.kind_combo.pack(side="left", padx=(4, 8))
        ttk.Button(
            filters,
            text="Clear",
            command=self._clear_filters,
        ).pack(side="left")
        ttk.Button(
            filters,
            text="Copy change",
            command=self._copy_selected,
        ).pack(side="left", padx=(10, 0))
        ttk.Label(filters, textvariable=self.count_var).pack(side="right")

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True, padx=12, pady=4)
        table_frame = ttk.Frame(body)
        detail_frame = ttk.Frame(body)
        body.add(table_frame, weight=3)
        body.add(detail_frame, weight=2)

        self.tree = ttk.Treeview(
            table_frame,
            columns=("action", "kind", "spatial", "local", "source"),
            show="tree headings",
        )
        self.tree.heading("#0", text="IFC GlobalId")
        self.tree.heading("action", text="Action")
        self.tree.heading("kind", text="Kind")
        self.tree.heading("spatial", text="CleanroomX ID")
        self.tree.heading("local", text="Local changed")
        self.tree.heading("source", text="IFC changed")
        self.tree.column("#0", width=230)
        self.tree.column("action", width=120, stretch=False)
        self.tree.column("kind", width=90, stretch=False)
        self.tree.column("spatial", width=210)
        self.tree.column("local", width=105, stretch=False)
        self.tree.column("source", width=105, stretch=False)
        scroll_y = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        scroll_x = ttk.Scrollbar(
            table_frame,
            orient="horizontal",
            command=self.tree.xview,
        )
        self.tree.configure(
            yscrollcommand=scroll_y.set,
            xscrollcommand=scroll_x.set,
        )
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.tree.tag_configure("conflict", font=("TkDefaultFont", 9, "bold"))

        self.detail = tk.Text(
            detail_frame,
            wrap="none",
            state="disabled",
            borderwidth=0,
        )
        detail_scroll_y = ttk.Scrollbar(
            detail_frame,
            orient="vertical",
            command=self.detail.yview,
        )
        detail_scroll_x = ttk.Scrollbar(
            detail_frame,
            orient="horizontal",
            command=self.detail.xview,
        )
        self.detail.configure(
            yscrollcommand=detail_scroll_y.set,
            xscrollcommand=detail_scroll_x.set,
        )
        self.detail.grid(row=0, column=0, sticky="nsew")
        detail_scroll_y.grid(row=0, column=1, sticky="ns")
        detail_scroll_x.grid(row=1, column=0, sticky="ew")
        detail_frame.rowconfigure(0, weight=1)
        detail_frame.columnconfigure(0, weight=1)

        for variable in (
            self.search_var,
            self.action_filter_var,
            self.kind_filter_var,
        ):
            variable.trace_add("write", lambda *_: self._populate())
        self.tree.bind("<<TreeviewSelect>>", self._show_selected)
        self.tree.bind("<Control-c>", lambda event: self._copy_selected())
        self.bind("<Control-f>", lambda event: self.search_entry.focus_set())
        self.bind("<Escape>", lambda event: self.destroy())

        self._populate()

        validation_error = report.get("candidate_validation_error")
        if validation_error:
            ttk.Label(
                self,
                text=f"Merged-layout validation: {validation_error}",
                wraplength=1060,
            ).pack(anchor="w", padx=12, pady=(6, 0))

        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=12, pady=12)
        ttk.Button(footer, text="Close", command=self.destroy).pack(side="right")

    def _filtered_changes(self) -> list[dict]:
        query = self.search_var.get().strip().casefold()
        action = self.action_filter_var.get().strip().casefold()
        kind = self.kind_filter_var.get().strip().casefold()
        visible = []
        for item in self.changes:
            item_action = str(item.get("action", ""))
            item_kind = str(item.get("kind", ""))
            if action and action != "all" and item_action.casefold() != action:
                continue
            if kind and kind != "all" and item_kind.casefold() != kind:
                continue
            if query:
                haystack = " ".join(
                    (
                        str(item.get("global_id", "")),
                        item_action,
                        item_kind,
                        str(item.get("spatial_id", "")),
                        json.dumps(
                            item,
                            sort_keys=True,
                            ensure_ascii=False,
                            allow_nan=False,
                        ),
                    )
                ).casefold()
                if query not in haystack:
                    continue
            visible.append(item)
        return visible

    def _populate(self) -> None:
        selection = self.tree.selection()
        selected_item = (
            self._change_by_iid.get(selection[0])
            if selection
            else None
        )
        selected_global_id = (
            str(selected_item.get("global_id", ""))
            if isinstance(selected_item, dict)
            else None
        )
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._change_by_iid.clear()

        visible = self._filtered_changes()
        for index, item in enumerate(visible, start=1):
            global_id = str(item.get("global_id", ""))
            iid = f"change:{index}"
            action = str(item.get("action", ""))
            tags = ("conflict",) if action.casefold() == "conflict" else ()
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=global_id,
                values=(
                    action,
                    item.get("kind", ""),
                    item.get("spatial_id", ""),
                    "yes" if item.get("local_changed") else "no",
                    "yes" if item.get("source_changed") else "no",
                ),
                tags=tags,
            )
            self._change_by_iid[iid] = item

        self.count_var.set(f"{len(visible)} of {len(self.changes)} changes")
        children = self.tree.get_children()
        target = None
        if selected_global_id is not None:
            for iid, item in self._change_by_iid.items():
                if str(item.get("global_id", "")) == selected_global_id:
                    target = iid
                    break
        if target is None and children:
            target = children[0]
        if target is not None:
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
        self._show_selected()

    def _clear_filters(self) -> None:
        self.search_var.set("")
        self.action_filter_var.set("All")
        self.kind_filter_var.set("All")
        self.search_entry.focus_set()

    def _selected_change(self) -> dict | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._change_by_iid.get(selection[0])

    def _copy_selected(self) -> None:
        item = self._selected_change()
        if item is None:
            return
        self.clipboard_clear()
        self.clipboard_append(
            json.dumps(
                item,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )

    def _show_selected(self, event=None) -> None:
        item = self._selected_change()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if item is not None:
            self.detail.insert(
                "1.0",
                json.dumps(
                    item,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                ),
            )
        elif self.changes and not self._filtered_changes():
            self.detail.insert(
                "1.0",
                "No IFC re-import changes match the active filters.",
            )
        else:
            self.detail.insert(
                "1.0",
                "No IFC entity changes are present in this re-import plan.",
            )
        self.detail.configure(state="disabled")


class CleanroomXApp:
    def __init__(
        self,
        root: tk.Tk,
        *,
        autosave_interval_seconds: float = DEFAULT_AUTOSAVE_INTERVAL_SECONDS,
        autosave_manager: AutosaveManager | None = None,
        ui_state_path: str | Path | None = None,
    ):
        self.root = root
        self.root.title(f"CleanroomX {__version__}")
        self._display_width = max(1, int(self.root.winfo_screenwidth()))
        self._display_height = max(1, int(self.root.winfo_screenheight()))
        self.root.minsize(
            min(1050, self._display_width),
            min(680, self._display_height),
        )
        default_width, default_height = clamp_window_size_to_display(
            1440,
            900,
            self._display_width,
            self._display_height,
        )
        self.root.geometry(f"{default_width}x{default_height}")

        self.project: ProjectDocument = new_project()
        self.project_path: Path | None = None
        self._project_file_revision = None
        self._recovery_source_path: Path | None = None
        self._restored_recovery_artifact: Path | None = None
        self._migration_source_path: Path | None = None
        self.last_run: AnalysisRun | None = None
        self.last_run_analysis_id: str | None = None
        self._runs_by_analysis: dict[str, AnalysisRun] = {}
        self._editor_analysis_id: str | None = None
        self._selection_guard = False
        self._baseline_state: str | None = None
        self._project_history = ProjectEditHistory(limit=PROJECT_HISTORY_LIMIT)
        self._autosave_interval_seconds = max(0.0, float(autosave_interval_seconds))
        self._autosave_interval_ms = (
            max(1000, int(self._autosave_interval_seconds * 1000))
            if self._autosave_interval_seconds > 0
            else 0
        )
        self._autosave_manager = autosave_manager or AutosaveManager()
        self._autosave_manager.begin_project(None)
        self._autosave_status_sequence = -1
        self._recovery_checkpoint_after_id = None
        self._project_diagnostics_after_id = None
        self._recent_project_paths: list[Path] = []
        self._command_palette_window: CommandPalette | None = None
        self._global_search_window: GlobalEngineeringSearch | None = None
        self._ui_state_path = (
            Path(ui_state_path)
            if ui_state_path is not None
            else default_gui_layout_state_path()
        )
        self._ui_layout_state = load_gui_layout_state(self._ui_state_path)
        window_width, window_height = clamp_window_size_to_display(
            self._ui_layout_state["window_width"],
            self._ui_layout_state["window_height"],
            self._display_width,
            self._display_height,
        )
        self.root.geometry(f"{window_width}x{window_height}")
        self._recent_project_paths = [
            Path(value)
            for value in self._ui_layout_state["recent_projects"]
        ]
        self._navigator_favorites_by_project: dict[str, list[str]] = {
            str(path): list(item_ids)
            for path, item_ids in self._ui_layout_state["navigator_favorites"].items()
        }

        self._queue: queue.Queue = queue.Queue()
        self._run_generation = 0
        self._running = False
        self._abandon_requested = False
        self._run_started_monotonic: float | None = None
        self._active_run_task_id: str | None = None

        self.name_var = tk.StringVar(value=self.project.name)
        self.description_var = tk.StringVar(value=self.project.description)
        self.status_var = tk.StringVar(value="Ready")
        self.autosave_status_var = tk.StringVar(
            value=(
                "Autosave: ready"
                if self._autosave_interval_ms
                else "Autosave: disabled"
            )
        )
        self.wrap_outputs_var = tk.BooleanVar(value=False)
        self.model_status_var = tk.StringVar(value="Model: ready")
        self.selection_status_var = tk.StringVar(value="Selected: —")
        self.workspace_status_var = tk.StringVar(value="Workspace: Split")
        self.workspace_profile_var = tk.StringVar(
            value=self._ui_layout_state["active_workspace"]
        )
        self.diagnostics_status_var = tk.StringVar(value="Problems: —")
        self.task_status_var = tk.StringVar(value="Tasks: idle")
        self.view_status_var = tk.StringVar(
            value="Split · 2D 100% · 3D 100% · Ortho"
        )
        self.navigator_filter_var = tk.StringVar(value="")
        self.navigator_recent_var = tk.StringVar(value="")
        self.navigator_favorites_var = tk.StringVar(value="")
        self._navigator_recent_ids: list[str] = []
        self._navigator_recent_display_to_id: dict[str, str] = {}
        self._navigator_recent_project_token = id(self.project)
        self._navigator_favorite_ids: list[str] = []
        self._navigator_favorite_display_to_id: dict[str, str] = {}
        self._navigator_favorites_project_token = id(self.project)
        self._navigator_favorites_loaded_key: str | None = None
        self.theme_var = tk.StringVar(value=self._ui_layout_state["theme"])
        self.density_var = tk.StringVar(value=self._ui_layout_state["density"])
        self.engineering_context_var = tk.StringVar(
            value="x 0.00 m   y 0.00 m · Grid 0.5 m · Snap ON"
        )
        self.focus_workspace_var = tk.BooleanVar(value=False)
        self.fullscreen_var = tk.BooleanVar(value=False)
        self.navigator_panel_visible_var = tk.BooleanVar(
            value=bool(self._ui_layout_state["navigator_visible"])
        )
        self.output_panel_visible_var = tk.BooleanVar(
            value=bool(self._ui_layout_state["output_visible"])
        )
        self._navigator_tree_snapshot: list[tuple[str, str, int]] = []
        self._focus_workspace_snapshot: dict[str, bool] | None = None

        self._configure_styles()
        self._build_menu()
        self._build_layout()
        self._apply_theme_to_native_widgets(redraw=False)
        self._refresh_analysis_list()
        self._refresh_engineering_panels()
        self._refresh_start_center()
        self._activate_start_workspace(apply_layout=False)
        self._capture_saved_state()
        self.root.after_idle(self._restore_ui_layout_state)
        self.name_var.trace_add("write", lambda *_: self._update_title())
        self.description_var.trace_add("write", lambda *_: self._update_title())
        self._update_title()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_worker)
        if self._autosave_interval_ms:
            self.root.after(self._autosave_interval_ms, self._autosave_tick)
            self.root.after(500, self._poll_autosave_status)

    def _configure_styles(self) -> None:
        self._theme_palette = configure_ttk_theme(
            self.root,
            self.theme_var.get(),
            density=self.density_var.get(),
        )

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="New Project", accelerator="Ctrl+N", command=self.new_project)
        file_menu.add_command(label="Open Project...", accelerator="Ctrl+O", command=self.open_project)
        file_menu.add_command(label="Save Project", accelerator="Ctrl+S", command=self.save_project)
        file_menu.add_command(label="Save Project As...", command=self.save_project_as)
        file_menu.add_separator()
        file_menu.add_command(
            label="Open Portable Project Bundle...",
            command=self.open_portable_project_bundle,
        )
        file_menu.add_command(
            label="Export Portable Project Bundle...",
            command=self.export_portable_project_bundle,
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        self.edit_menu = tk.Menu(menubar, tearoff=False)
        self.edit_menu.add_command(
            label="Undo Project Edit", command=self.undo_project_edit, state="disabled"
        )
        self.edit_menu.add_command(
            label="Redo Project Edit", command=self.redo_project_edit, state="disabled"
        )
        menubar.add_cascade(label="Edit", menu=self.edit_menu)

        project_menu = tk.Menu(menubar, tearoff=False)
        project_menu.add_command(label="Add Analysis...", command=self.add_analysis)
        project_menu.add_command(label="Rename Analysis...", command=self.rename_analysis)
        project_menu.add_command(label="Remove Analysis", command=self.remove_analysis)
        project_menu.add_separator()
        project_menu.add_command(label="Saved Revisions...", command=self.show_saved_revisions)
        project_menu.add_command(label="Recovery Center...", command=self.show_recovery_center)
        menubar.add_cascade(label="Project", menu=project_menu)

        design_menu = tk.Menu(menubar, tearoff=False)
        design_menu.add_command(
            label="2D Workspace", accelerator="Ctrl+1",
            command=lambda: self._activate_spatial_workspace("2d"),
        )
        design_menu.add_command(
            label="3D Workspace", accelerator="Ctrl+2",
            command=lambda: self._activate_spatial_workspace("3d"),
        )
        design_menu.add_command(
            label="Split 2D + 3D", accelerator="Ctrl+3",
            command=lambda: self._activate_spatial_workspace("split"),
        )
        design_menu.add_separator()
        design_menu.add_command(
            label="Add Room",
            command=lambda: self.spatial_workspace.add_room(),
        )
        design_menu.add_command(
            label="Fit Spatial Views",
            command=lambda: self.spatial_workspace.fit_views(),
        )
        menubar.add_cascade(label="Design", menu=design_menu)

        analyze_menu = tk.Menu(menubar, tearoff=False)
        analyze_menu.add_command(label="Validate Input", command=self.validate_current)
        analyze_menu.add_command(
            label="Run Analysis", accelerator="F5", command=self.run_current
        )
        analyze_menu.add_command(label="Abandon Current Run", command=self.cancel_run)
        analyze_menu.add_separator()
        analyze_menu.add_command(label="Run History...", command=self.show_run_history)
        menubar.add_cascade(label="Simulation", menu=analyze_menu)

        verify_menu = tk.Menu(menubar, tearoff=False)
        verify_menu.add_command(
            label="Verify Project Requirements",
            command=self.run_project_requirements_verification,
        )
        verify_menu.add_command(
            label="Verify & Persist Project Requirements",
            command=self.persist_project_requirements_verification,
        )
        verify_menu.add_command(
            label="Refresh Project Diagnostics",
            accelerator="F8",
            command=self._refresh_engineering_panels,
        )
        verify_menu.add_separator()
        verify_menu.add_command(
            label="Requirements Traceability...",
            command=self.show_requirements_traceability,
        )
        verify_menu.add_command(
            label="Verification History...",
            command=self.show_verification_history,
        )
        menubar.add_cascade(label="Verification", menu=verify_menu)

        evidence_menu = tk.Menu(menubar, tearoff=False)
        evidence_menu.add_command(
            label="Evidence Workspace",
            command=lambda: self.activate_workspace_profile("evidence"),
        )
        evidence_menu.add_command(
            label="ProofGraph Explorer",
            command=self._activate_proofgraph_workspace,
        )
        evidence_menu.add_separator()
        evidence_menu.add_command(
            label="Requirements Traceability...",
            command=self.show_requirements_traceability,
        )
        menubar.add_cascade(label="Evidence", menu=evidence_menu)

        bim_menu = tk.Menu(menubar, tearoff=False)
        bim_menu.add_command(
            label="Import IFC Spatial Layout...",
            command=self.import_ifc_spatial_layout,
        )
        bim_menu.add_command(
            label="Review IFC Re-import...",
            command=self.review_ifc_reimport,
        )
        bim_menu.add_command(
            label="Apply IFC Re-import...",
            command=self.apply_ifc_reimport,
        )
        menubar.add_cascade(label="BIM", menu=bim_menu)

        report_menu = tk.Menu(menubar, tearoff=False)
        report_menu.add_command(
            label="Reporting Workspace",
            command=self._activate_reporting_workspace,
        )
        report_menu.add_command(
            label="Export Selected Summary...",
            command=self.export_selected_reporting_summary,
        )
        report_menu.add_separator()
        report_menu.add_command(
            label="Export Project Engineering Dossier...",
            command=self.export_project_engineering_dossier,
        )
        report_menu.add_separator()
        report_menu.add_command(label="Export Result JSON...", command=self.export_result_json)
        report_menu.add_command(
            label="Export Run Bundle JSON...", command=self.export_run_bundle_json
        )
        report_menu.add_command(
            label="Export Report Markdown...", command=self.export_report_markdown
        )
        report_menu.add_command(
            label="Export Portable HTML Report...", command=self.export_report_html
        )
        menubar.add_cascade(label="Reports", menu=report_menu)

        tools_menu = tk.Menu(menubar, tearoff=False)
        tools_menu.add_command(
            label="Global Engineering Search...",
            accelerator="Ctrl+K",
            command=self.show_global_search,
        )
        tools_menu.add_command(
            label="Command Palette...",
            accelerator="Ctrl+Shift+P",
            command=self.show_command_palette,
        )
        menubar.add_cascade(label="Tools", menu=tools_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="Start Center", command=self._activate_start_workspace)
        workspace_menu = tk.Menu(view_menu, tearoff=False)
        for profile in ("design", "simulation", "verification", "evidence", "reporting"):
            workspace_menu.add_command(
                label=WORKSPACE_LABELS[profile],
                command=lambda selected=profile: self.activate_workspace_profile(selected),
            )
        view_menu.add_cascade(label="Engineering Workspace", menu=workspace_menu)
        view_menu.add_separator()
        view_menu.add_checkbutton(
            label="Project Navigator",
            accelerator="Ctrl+B",
            variable=self.navigator_panel_visible_var,
            command=self._on_navigator_visibility_requested,
        )
        view_menu.add_checkbutton(
            label="Output / Verification",
            accelerator="Ctrl+J",
            variable=self.output_panel_visible_var,
            command=self._on_output_visibility_requested,
        )
        view_menu.add_command(
            label="Design Inspector",
            accelerator="Ctrl+I",
            command=self.toggle_design_inspector,
        )
        view_menu.add_command(
            label="Job / Task Center",
            command=self.show_task_center,
        )
        view_menu.add_checkbutton(
            label="Focus Workspace",
            accelerator="Ctrl+Shift+F",
            variable=self.focus_workspace_var,
            command=self._sync_focus_workspace,
        )
        view_menu.add_checkbutton(
            label="Full-screen Workspace",
            accelerator="F11",
            variable=self.fullscreen_var,
            command=self._sync_fullscreen_workspace,
        )
        view_menu.add_command(
            label="Reset Panel Layout",
            command=self.reset_panel_layout,
        )
        theme_menu = tk.Menu(view_menu, tearoff=False)
        for value, label in (("light", "Light"), ("dark", "Dark")):
            theme_menu.add_radiobutton(
                label=label,
                variable=self.theme_var,
                value=value,
                command=lambda mode=value: self.set_theme(mode),
            )
        view_menu.add_cascade(label="Theme", menu=theme_menu)
        density_menu = tk.Menu(view_menu, tearoff=False)
        for value, label in (("compact", "Compact / Engineering"), ("comfortable", "Comfortable")):
            density_menu.add_radiobutton(
                label=label,
                variable=self.density_var,
                value=value,
                command=lambda mode=value: self.set_density(mode),
            )
        view_menu.add_cascade(label="Density", menu=density_menu)
        view_menu.add_separator()
        view_menu.add_command(label="Refresh Structured Input", command=self.refresh_structure)
        view_menu.add_command(
            label="Refresh Spatial Workspace",
            command=lambda: self.spatial_workspace.refresh(),
        )
        view_menu.add_checkbutton(
            label="Wrap output text",
            variable=self.wrap_outputs_var,
            command=self._apply_wrap_setting,
        )
        menubar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About CleanroomX", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.menubar = menubar
        self.root.config(menu=menubar)
        self.root.bind("<Control-n>", lambda event: self.new_project())
        self.root.bind("<Control-o>", lambda event: self.open_project())
        self.root.bind("<Control-s>", lambda event: self.save_project())
        self.root.bind("<Control-Key-1>", lambda event: self._activate_spatial_workspace("2d"))
        self.root.bind("<Control-Key-2>", lambda event: self._activate_spatial_workspace("3d"))
        self.root.bind("<Control-Key-3>", lambda event: self._activate_spatial_workspace("split"))
        self.root.bind("<Control-b>", lambda event: self.toggle_navigator_panel())
        self.root.bind("<Control-j>", lambda event: self.toggle_output_panel())
        self.root.bind("<Control-i>", lambda event: self.toggle_design_inspector())
        self.root.bind("<Control-Shift-F>", lambda event: self.toggle_focus_workspace())
        self.root.bind("<F11>", lambda event: self.toggle_fullscreen_workspace())
        self.root.bind("<Escape>", lambda event: self.exit_fullscreen_workspace())
        self.root.bind("<Control-Alt-t>", lambda event: self.toggle_theme())
        self.root.bind("<Control-k>", lambda event: self.show_global_search())
        self.root.bind("<Control-K>", lambda event: self.show_global_search())
        self.root.bind("<Control-Shift-P>", lambda event: self.show_command_palette())
        for sequence, profile in (
            ("<Control-Alt-Key-1>", "design"),
            ("<Control-Alt-Key-2>", "simulation"),
            ("<Control-Alt-Key-3>", "verification"),
            ("<Control-Alt-Key-4>", "evidence"),
            ("<Control-Alt-Key-5>", "reporting"),
        ):
            self.root.bind(
                sequence,
                lambda event, selected=profile: self.activate_workspace_profile(selected),
            )
        self.root.bind("<F5>", lambda event: self.run_current())
        self.root.bind("<F8>", lambda event: self._refresh_engineering_panels())

    def _build_layout(self) -> None:
        # Keep the application chrome compact enough that the engineering
        # workspace remains fully usable at the supported 1050×680 minimum.
        topbar = ttk.Frame(self.root, padding=(10, 5, 10, 4))
        topbar.pack(fill="x")
        ttk.Label(topbar, text="CLEANROOMX", style="CX.Brand.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 12)
        )
        ttk.Label(topbar, text="Project").grid(
            row=0, column=1, sticky="w", padx=(0, 5)
        )
        ttk.Entry(topbar, textvariable=self.name_var, width=22).grid(
            row=0, column=2, sticky="ew", padx=(0, 10)
        )
        ttk.Label(topbar, text="Description").grid(
            row=0, column=3, sticky="w", padx=(0, 5)
        )
        ttk.Entry(topbar, textvariable=self.description_var, width=28).grid(
            row=0, column=4, sticky="ew", padx=(0, 10)
        )
        ttk.Button(
            topbar,
            text="Validate",
            command=self.validate_current,
        ).grid(row=0, column=5, padx=2)
        self.run_button = ttk.Button(
            topbar,
            text="▶ Run",
            command=self.run_current,
            style="CX.Primary.TButton",
        )
        self.run_button.grid(row=0, column=6, padx=2)
        self.cancel_button = ttk.Button(
            topbar, text="Abandon", command=self.cancel_run, state="disabled"
        )
        self.cancel_button.grid(row=0, column=7, padx=(2, 0))
        topbar.columnconfigure(2, weight=1)
        topbar.columnconfigure(4, weight=2)

        commandbar = ttk.Frame(
            self.root,
            style="CX.Toolbar.TFrame",
            padding=(10, 3),
        )
        self.commandbar = commandbar
        commandbar.pack(fill="x", padx=10, pady=(0, 4))

        # Reserve the right-side global actions first so critical controls
        # cannot be clipped when the window is at the supported minimum width.
        self.toolbar_commands_button = ttk.Button(
            commandbar,
            text="Commands…",
            width=10,
            style="CX.Compact.TButton",
            command=self.show_command_palette,
        )
        self.toolbar_commands_button.pack(side="right", padx=1)
        self.toolbar_workspace_button = ttk.Menubutton(
            commandbar,
            text="Workspace",
            width=9,
            style="CX.Compact.TButton",
        )
        self.toolbar_workspace_menu = tk.Menu(
            self.toolbar_workspace_button,
            tearoff=False,
        )
        for profile in ("design", "simulation", "verification", "evidence", "reporting"):
            self.toolbar_workspace_menu.add_command(
                label=WORKSPACE_LABELS[profile],
                command=lambda selected=profile: self.activate_workspace_profile(selected),
            )
        self.toolbar_workspace_button.configure(menu=self.toolbar_workspace_menu)
        self.toolbar_workspace_button.pack(side="right", padx=1)
        self.toolbar_problems_button = ttk.Button(
            commandbar,
            text="Problems",
            width=8,
            style="CX.Compact.TButton",
            command=self.show_problems_panel,
        )
        self.toolbar_problems_button.pack(side="right", padx=1)

        self.toolbar_new_button = ttk.Button(
            commandbar,
            text="New",
            width=5,
            style="CX.Compact.TButton",
            command=self.new_project,
        )
        self.toolbar_new_button.pack(side="left", padx=1)
        self.toolbar_open_button = ttk.Button(
            commandbar,
            text="Open",
            width=5,
            style="CX.Compact.TButton",
            command=self.open_project,
        )
        self.toolbar_open_button.pack(side="left", padx=1)
        self.toolbar_save_button = ttk.Button(
            commandbar,
            text="Save",
            width=5,
            style="CX.Compact.TButton",
            command=self.save_project,
        )
        self.toolbar_save_button.pack(side="left", padx=1)
        ttk.Separator(commandbar, orient="vertical").pack(
            side="left", fill="y", padx=4
        )

        self.toolbar_undo_button = ttk.Button(
            commandbar,
            text="Undo",
            width=5,
            style="CX.Compact.TButton",
            command=self.undo_project_edit,
            state="disabled",
        )
        self.toolbar_undo_button.pack(side="left", padx=1)
        self.toolbar_redo_button = ttk.Button(
            commandbar,
            text="Redo",
            width=5,
            style="CX.Compact.TButton",
            command=self.redo_project_edit,
            state="disabled",
        )
        self.toolbar_redo_button.pack(side="left", padx=1)
        ttk.Separator(commandbar, orient="vertical").pack(
            side="left", fill="y", padx=4
        )

        for label, mode, width in (
            ("2D", "2d", 4),
            ("3D", "3d", 4),
            ("Split", "split", 5),
        ):
            ttk.Button(
                commandbar,
                text=label,
                width=width,
                style="CX.Compact.TButton",
                command=lambda selected=mode: self._activate_spatial_workspace(selected),
            ).pack(side="left", padx=1)
        self.toolbar_fit_button = ttk.Button(
            commandbar,
            text="Fit",
            width=4,
            style="CX.Compact.TButton",
            command=lambda: self.spatial_workspace.fit_views(),
        )
        self.toolbar_fit_button.pack(side="left", padx=1)

        workflowbar = ttk.Frame(
            self.root,
            style="CX.Toolbar.TFrame",
            padding=(10, 3),
        )
        self.workflowbar = workflowbar
        workflowbar.pack(fill="x", padx=10, pady=(0, 4))
        ttk.Label(
            workflowbar,
            text="GUIDED WORKFLOW",
        ).pack(side="left", padx=(0, 8))
        ttk.Separator(workflowbar, orient="vertical").pack(
            side="left", fill="y", padx=(0, 6)
        )

        self.workflow_design_button = ttk.Button(
            workflowbar,
            text="1  Design",
            width=9,
            style="CX.Compact.TButton",
            command=lambda: self._activate_spatial_workspace("split"),
        )
        self.workflow_design_button.pack(side="left", padx=1)
        self.workflow_input_button = ttk.Button(
            workflowbar,
            text="2  Inputs",
            width=9,
            style="CX.Compact.TButton",
            command=self._activate_analysis_input_workspace,
        )
        self.workflow_input_button.pack(side="left", padx=1)
        self.workflow_validate_button = ttk.Button(
            workflowbar,
            text="3  Validate",
            width=10,
            style="CX.Compact.TButton",
            command=self.validate_current,
        )
        self.workflow_validate_button.pack(side="left", padx=1)
        self.workflow_run_button = ttk.Button(
            workflowbar,
            text="4  Run",
            width=9,
            style="CX.Primary.TButton",
            command=self.run_current,
        )
        self.workflow_run_button.pack(side="left", padx=1)
        self.workflow_verify_button = ttk.Button(
            workflowbar,
            text="5  Save & Verify",
            width=14,
            style="CX.Compact.TButton",
            command=self._guided_save_and_verify,
        )
        self.workflow_verify_button.pack(side="left", padx=1)
        self.workflow_report_button = ttk.Button(
            workflowbar,
            text="6  Report",
            width=9,
            style="CX.Compact.TButton",
            command=self._activate_reporting_workspace,
        )
        self.workflow_report_button.pack(side="left", padx=1)

        panes = ttk.Panedwindow(self.root, orient="horizontal")
        self.main_panes = panes
        panes.pack(fill="both", expand=True, padx=10, pady=(2, 6))

        navigator = ttk.Frame(panes, padding=(8, 7))
        self.navigator_panel = navigator
        panes.add(navigator, weight=1)
        navigator_header = ttk.Frame(
            navigator,
            style="CX.PanelHeader.TFrame",
        )
        navigator_header.pack(fill="x", pady=(0, 6))
        ttk.Label(
            navigator_header,
            text="PROJECT NAVIGATOR",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.navigator_close_button = ttk.Button(
            navigator_header,
            text="×",
            width=3,
            style="CX.Compact.TButton",
            command=self.hide_navigator_panel,
        )
        self.navigator_close_button.pack(side="right")
        filter_row = ttk.Frame(navigator)
        filter_row.pack(fill="x", pady=(0, 6))
        ttk.Label(filter_row, text="Filter").pack(side="left", padx=(0, 6))
        navigator_filter = ttk.Entry(
            filter_row,
            textvariable=self.navigator_filter_var,
        )
        navigator_filter.pack(side="left", fill="x", expand=True)
        ttk.Button(
            filter_row,
            text="×",
            width=3,
            command=lambda: self.navigator_filter_var.set(""),
        ).pack(side="left", padx=(4, 0))

        recent_row = ttk.Frame(navigator)
        recent_row.pack(fill="x", pady=(0, 6))
        ttk.Label(recent_row, text="Recent").pack(side="left", padx=(0, 6))
        self.navigator_recent_picker = ttk.Combobox(
            recent_row,
            textvariable=self.navigator_recent_var,
            values=(),
            state="readonly",
        )
        self.navigator_recent_picker.pack(side="left", fill="x", expand=True)
        self.navigator_recent_picker.bind(
            "<<ComboboxSelected>>",
            self._on_recent_navigator_selected,
        )
        ttk.Button(
            recent_row,
            text="Clear",
            style="CX.Compact.TButton",
            command=self.clear_navigator_recent,
        ).pack(side="left", padx=(4, 0))

        favorites_row = ttk.Frame(navigator)
        favorites_row.pack(fill="x", pady=(0, 6))
        ttk.Label(favorites_row, text="Favorites").pack(side="left", padx=(0, 6))
        self.navigator_favorites_picker = ttk.Combobox(
            favorites_row,
            textvariable=self.navigator_favorites_var,
            values=(),
            state="readonly",
        )
        self.navigator_favorites_picker.pack(side="left", fill="x", expand=True)
        self.navigator_favorites_picker.bind(
            "<<ComboboxSelected>>",
            self._on_favorite_navigator_selected,
        )
        self.navigator_favorite_toggle_button = ttk.Button(
            favorites_row,
            text="☆",
            width=3,
            style="CX.Compact.TButton",
            command=self.toggle_selected_navigator_favorite,
        )
        self.navigator_favorite_toggle_button.pack(side="left", padx=(4, 0))
        ttk.Button(
            favorites_row,
            text="Clear",
            style="CX.Compact.TButton",
            command=self.clear_navigator_favorites,
        ).pack(side="left", padx=(4, 0))

        navigator_actions = ttk.Frame(navigator)
        navigator_actions.pack(fill="x", pady=(0, 6))
        self.navigator_add_analysis_button = ttk.Button(
            navigator_actions,
            text="+ Analysis",
            style="CX.Compact.TButton",
            command=lambda: self.add_analysis(),
        )
        self.navigator_add_analysis_button.pack(
            side="left", fill="x", expand=True, padx=(0, 2)
        )
        self.navigator_add_room_button = ttk.Button(
            navigator_actions,
            text="+ Room",
            style="CX.Compact.TButton",
            command=lambda: self.spatial_workspace.add_room(),
        )
        self.navigator_add_room_button.pack(
            side="left", fill="x", expand=True, padx=(2, 0)
        )
        self.navigator_import_ifc_button = ttk.Button(
            navigator,
            text="Import IFC spatial layout…",
            style="CX.Compact.TButton",
            command=lambda: self.import_ifc_spatial_layout(),
        )
        self.navigator_import_ifc_button.pack(fill="x", pady=(0, 6))

        self.analysis_tree = ttk.Treeview(
            navigator,
            columns=("kind",),
            show="tree",
            selectmode="browse",
            style="CX.Navigator.Treeview",
        )
        self.analysis_tree.column("#0", width=245, minwidth=180)
        nav_scroll = ttk.Scrollbar(
            navigator, orient="vertical", command=self.analysis_tree.yview
        )
        self.analysis_tree.configure(yscrollcommand=nav_scroll.set)
        self.analysis_tree.pack(side="left", fill="both", expand=True)
        nav_scroll.pack(side="right", fill="y")
        self.analysis_tree.bind("<<TreeviewSelect>>", self._on_navigator_selected)
        self.analysis_tree.bind("<Button-3>", self._show_navigator_context_menu)
        self.analysis_tree.tag_configure("section", font=("TkDefaultFont", 9, "bold"))
        self.navigator_filter_var.trace_add(
            "write",
            lambda *_: self._apply_navigator_filter(),
        )

        content = ttk.Frame(panes)
        self.content_panel = content
        panes.add(content, weight=5)

        self.workspace_panes = ttk.Panedwindow(content, orient="vertical")
        self.workspace_panes.pack(fill="both", expand=True)

        workspace_host = ttk.Frame(self.workspace_panes)
        self.workspace_panes.add(workspace_host, weight=5)
        self.notebook = ttk.Notebook(workspace_host)
        self.notebook.pack(fill="both", expand=True)

        self.start_center = StartCenter(
            self.notebook,
            on_new=self.new_project,
            on_open=self.open_project,
            on_import_ifc=self._import_ifc_from_start,
            on_open_demo=self._open_bundled_demo_from_start,
            on_open_recent=self._open_recent_project_from_start,
            on_forget_recent=self._forget_recent_project,
        )
        self.notebook.add(self.start_center, text="Start")

        self.spatial_workspace = SpatialDesignWorkspace(
            self.notebook,
            project_getter=lambda: self.project,
            analysis_getter=self._editor_analysis,
            on_change=self._on_spatial_changed,
            on_sync_requested=self._sync_spatial_to_current_analysis,
            on_pull_requested=self._sync_current_analysis_to_spatial,
            result_getter=self._spatial_result_payload,
            status_setter=self.status_var.set,
            on_history_record=self._record_spatial_project_edit,
            on_undo_requested=self.undo_project_edit,
            on_redo_requested=self.redo_project_edit,
            on_selection_change=self._on_workspace_selection_change,
            on_view_status_change=self.view_status_var.set,
            on_engineering_context_change=self.engineering_context_var.set,
        )
        self.notebook.add(self.spatial_workspace, text="Design")

        self.simulation_workspace = SimulationWorkspace(
            self.notebook,
            on_run=self.run_current,
            on_cancel=self.cancel_run,
            on_validate=self.validate_current,
            on_open_inputs=self._activate_analysis_input_workspace,
            on_open_results=self._activate_analysis_results_workspace,
            on_open_history=self.show_run_history,
            on_select_analysis=self._select_analysis_from_simulation,
        )
        self.notebook.add(self.simulation_workspace, text="Simulation")

        self.input_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.input_tab, text="Input")
        input_notebook = ttk.Notebook(self.input_tab)
        input_notebook.pack(fill="both", expand=True)

        structured_tab = ttk.Frame(input_notebook)
        input_notebook.add(structured_tab, text="Structured")
        structured_help = ttk.Frame(structured_tab, padding=(8, 6))
        structured_help.pack(fill="x")
        ttk.Label(
            structured_help,
            text=(
                "Validated scalar editing · double-click or Enter to edit the selected "
                "value; objects/arrays remain in the JSON editor."
            ),
        ).pack(side="left")
        ttk.Button(
            structured_help,
            text="Edit value",
            command=self._edit_structured_input_value,
        ).pack(side="right")
        self._structure_rows: dict[
            str, tuple[tuple[str | int, ...], object, str]
        ] = {}
        self.structure_tree = ttk.Treeview(
            structured_tab,
            columns=("value", "unit"),
            show="tree headings",
        )
        self.structure_tree.heading("#0", text="Field path")
        self.structure_tree.heading("value", text="Value")
        self.structure_tree.heading("unit", text="Unit")
        self.structure_tree.column("#0", width=430)
        self.structure_tree.column("value", width=310)
        self.structure_tree.column("unit", width=90, stretch=False)
        struct_scroll = ttk.Scrollbar(
            structured_tab, orient="vertical", command=self.structure_tree.yview
        )
        self.structure_tree.configure(yscrollcommand=struct_scroll.set)
        self.structure_tree.pack(side="left", fill="both", expand=True)
        struct_scroll.pack(side="right", fill="y")
        self.structure_tree.bind(
            "<Double-1>",
            lambda _event: self._edit_structured_input_value(),
        )
        self.structure_tree.bind(
            "<Return>",
            lambda _event: self._edit_structured_input_value(),
        )

        json_tab = ttk.Frame(input_notebook)
        input_notebook.add(json_tab, text="JSON editor")
        self.input_text = tk.Text(json_tab, wrap="none", undo=True)
        input_scroll_y = ttk.Scrollbar(
            json_tab, orient="vertical", command=self.input_text.yview
        )
        input_scroll_x = ttk.Scrollbar(
            json_tab, orient="horizontal", command=self.input_text.xview
        )
        self.input_text.configure(
            yscrollcommand=input_scroll_y.set, xscrollcommand=input_scroll_x.set
        )
        self.input_text.grid(row=0, column=0, sticky="nsew")
        input_scroll_y.grid(row=0, column=1, sticky="ns")
        input_scroll_x.grid(row=1, column=0, sticky="ew")
        json_tab.rowconfigure(0, weight=1)
        json_tab.columnconfigure(0, weight=1)
        self.input_text.bind(
            "<FocusOut>", lambda event: self.refresh_structure(silent=True)
        )
        self.input_text.bind("<<Modified>>", self._on_input_modified)
        self.input_text.edit_modified(False)

        plot_tab = ttk.Frame(self.notebook)
        self.plot_tab = plot_tab
        self.notebook.add(plot_tab, text="Plot")
        self.plot_canvas = tk.Canvas(plot_tab, highlightthickness=0)
        self.plot_canvas.pack(fill="both", expand=True)
        self.plot_canvas.bind("<Configure>", lambda event: self._draw_plot())

        self.proofgraph_viewer = ProofGraphViewer(
            self.notebook,
            on_navigate=self._navigate_proofgraph_node,
            status_setter=self.status_var.set,
        )
        self.notebook.add(self.proofgraph_viewer, text="ProofGraph")

        self.reporting_workspace = ReportingWorkspace(
            self.notebook,
            on_export_dossier=self.export_project_engineering_dossier,
            on_export_diagnostics=self.export_project_diagnostics,
            on_export_result_json=self.export_result_json,
            on_export_run_bundle=self.export_run_bundle_json,
            on_export_markdown=self.export_report_markdown,
            on_export_html=self.export_report_html,
            on_export_selected_summary=self.export_selected_reporting_summary,
        )
        self.notebook.add(self.reporting_workspace, text="Reports")

        output_host = ttk.Frame(self.workspace_panes, padding=(0, 5, 0, 0))
        self.output_panel = output_host
        self.workspace_panes.add(output_host, weight=1)
        output_header = ttk.Frame(
            output_host,
            style="CX.PanelHeader.TFrame",
        )
        output_header.pack(fill="x")
        ttk.Label(
            output_header,
            text="OUTPUT / VERIFICATION",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.output_close_button = ttk.Button(
            output_header,
            text="×",
            width=3,
            style="CX.Compact.TButton",
            command=self.hide_output_panel,
        )
        self.output_close_button.pack(side="right")
        ttk.Label(
            output_host,
            text="Diagnostics · verification currency · evidence · analysis output",
        ).pack(fill="x", padx=8, pady=(4, 2))

        self.output_notebook = ttk.Notebook(output_host)
        self.output_notebook.pack(fill="both", expand=True)

        self.problems_panel = ProjectDiagnosticsPanel(
            self.output_notebook,
            project_getter=lambda: self.project,
            base_dir_getter=self._base_dir,
            navigate_callback=self._navigate_project_diagnostic,
            export_callback=self.export_project_diagnostics,
            status_setter=self.status_var.set,
        )
        self.output_notebook.add(self.problems_panel, text="Problems")
        self.diagnostics_text = self._add_text_tab(
            "Diagnostics", notebook=self.output_notebook
        )
        self.verification_text = self._add_text_tab(
            "Verification", notebook=self.output_notebook
        )
        self.console_text = self._add_text_tab(
            "Console", notebook=self.output_notebook
        )
        self.evidence_text = self._add_text_tab(
            "Evidence", notebook=self.output_notebook
        )
        self.task_center = TaskCenter(
            self.output_notebook,
            on_change=self._on_task_center_change,
            on_abandon=self._abandon_task_from_center,
        )
        self.task_center.apply_theme(self.theme_var.get())
        self.output_notebook.add(self.task_center, text="Tasks")
        self.result_text = self._add_text_tab(
            "Results", notebook=self.output_notebook
        )
        self.report_text = self._add_text_tab(
            "Report", notebook=self.output_notebook
        )

        status_bar = ttk.Frame(self.root, padding=(8, 4))
        status_bar.pack(fill="x", side="bottom")
        ttk.Label(
            status_bar,
            textvariable=self.status_var,
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        ttk.Separator(status_bar, orient="vertical").pack(
            side="left", fill="y", padx=8
        )
        ttk.Label(status_bar, textvariable=self.model_status_var).pack(side="left")
        ttk.Separator(status_bar, orient="vertical").pack(
            side="left", fill="y", padx=8
        )
        ttk.Label(status_bar, textvariable=self.selection_status_var).pack(side="left")
        ttk.Separator(status_bar, orient="vertical").pack(
            side="left", fill="y", padx=8
        )
        ttk.Label(status_bar, textvariable=self.workspace_status_var).pack(side="left")
        ttk.Separator(status_bar, orient="vertical").pack(
            side="left", fill="y", padx=8
        )
        ttk.Label(
            status_bar,
            textvariable=self.view_status_var,
            anchor="e",
            width=31,
        ).pack(side="left")
        ttk.Separator(status_bar, orient="vertical").pack(
            side="left", fill="y", padx=8
        )
        ttk.Label(
            status_bar,
            textvariable=self.engineering_context_var,
            anchor="e",
        ).pack(side="left")
        ttk.Separator(status_bar, orient="vertical").pack(
            side="left", fill="y", padx=8
        )
        self.task_status_label = ttk.Label(
            status_bar,
            textvariable=self.task_status_var,
            anchor="e",
            cursor="hand2",
        )
        self.task_status_label.pack(side="right", padx=(8, 0))
        self.task_status_label.bind(
            "<Button-1>",
            lambda event: self.show_task_center(),
        )
        ttk.Separator(status_bar, orient="vertical").pack(
            side="right", fill="y", padx=8
        )
        self.diagnostics_status_label = ttk.Label(
            status_bar,
            textvariable=self.diagnostics_status_var,
            anchor="e",
            cursor="hand2",
        )
        self.diagnostics_status_label.pack(side="right", padx=(8, 0))
        self.diagnostics_status_label.bind(
            "<Button-1>",
            lambda event: self.show_problems_panel(),
        )
        ttk.Separator(status_bar, orient="vertical").pack(
            side="right", fill="y", padx=8
        )
        ttk.Label(
            status_bar,
            textvariable=self.autosave_status_var,
            anchor="e",
        ).pack(side="right")

    @staticmethod
    def _paned_contains(paned: ttk.Panedwindow, child: tk.Misc) -> bool:
        return str(child) in {str(item) for item in paned.panes()}

    @staticmethod
    def _pane_fraction(paned: ttk.Panedwindow, extent: int) -> float | None:
        if len(paned.panes()) < 2 or extent <= 1:
            return None
        try:
            position = paned.sashpos(0)
        except tk.TclError:
            return None
        return min(0.95, max(0.05, float(position) / float(extent)))

    @staticmethod
    def _set_pane_fraction(
        paned: ttk.Panedwindow,
        fraction: float,
        extent: int,
    ) -> None:
        if len(paned.panes()) < 2 or extent <= 1:
            return
        position = int(round(extent * min(0.95, max(0.05, float(fraction)))))
        try:
            paned.sashpos(0, position)
        except tk.TclError:
            return

    def _remember_current_panel_fractions(self) -> None:
        state = dict(getattr(self, "_ui_layout_state", {}))
        if (
            hasattr(self, "main_panes")
            and self.navigator_panel_visible_var.get()
            and self._paned_contains(self.main_panes, self.navigator_panel)
        ):
            fraction = self._pane_fraction(
                self.main_panes,
                self.main_panes.winfo_width(),
            )
            if fraction is not None:
                state["navigator_fraction"] = fraction
        if (
            hasattr(self, "workspace_panes")
            and self.output_panel_visible_var.get()
            and self._paned_contains(self.workspace_panes, self.output_panel)
        ):
            fraction = self._pane_fraction(
                self.workspace_panes,
                self.workspace_panes.winfo_height(),
            )
            if fraction is not None:
                state["output_fraction"] = fraction
        workspace = getattr(self, "spatial_workspace", None)
        if workspace is not None and workspace.inspector_visible():
            fraction = self._pane_fraction(
                workspace._body,
                workspace._body.winfo_width(),
            )
            if fraction is not None:
                state["inspector_fraction"] = fraction
        self._ui_layout_state = normalize_gui_layout_state(state)

    def _apply_saved_panel_sashes(self) -> None:
        state = self._ui_layout_state
        if (
            self.navigator_panel_visible_var.get()
            and self._paned_contains(self.main_panes, self.navigator_panel)
        ):
            self._set_pane_fraction(
                self.main_panes,
                state["navigator_fraction"],
                self.main_panes.winfo_width(),
            )
        if (
            self.output_panel_visible_var.get()
            and self._paned_contains(self.workspace_panes, self.output_panel)
        ):
            self._set_pane_fraction(
                self.workspace_panes,
                state["output_fraction"],
                self.workspace_panes.winfo_height(),
            )
        workspace = getattr(self, "spatial_workspace", None)
        if workspace is not None and workspace.inspector_visible():
            self._set_pane_fraction(
                workspace._body,
                state["inspector_fraction"],
                workspace._body.winfo_width(),
            )

    def _current_workspace_profile(self) -> str:
        profile = str(self.workspace_profile_var.get() or "").strip().casefold()
        return profile if profile in GUI_WORKSPACE_PROFILES else "start"

    def _capture_current_workspace_layout(self) -> None:
        """Store the active workspace panel arrangement without touching project data."""
        self._remember_current_panel_fractions()
        state = dict(getattr(self, "_ui_layout_state", {}))
        profile = self._current_workspace_profile()
        workspace = getattr(self, "spatial_workspace", None)
        focus_snapshot = getattr(self, "_focus_workspace_snapshot", None)
        if focus_snapshot is None:
            visibility = {
                "navigator_visible": bool(self.navigator_panel_visible_var.get()),
                "output_visible": bool(self.output_panel_visible_var.get()),
                "inspector_visible": bool(
                    workspace is not None and workspace.inspector_visible()
                ),
            }
        else:
            visibility = dict(focus_snapshot)
        layout = {
            **visibility,
            "navigator_fraction": state.get("navigator_fraction", 0.20),
            "output_fraction": state.get("output_fraction", 0.72),
            "inspector_fraction": state.get("inspector_fraction", 0.78),
        }
        layouts = copy.deepcopy(state.get("workspace_layouts", {}))
        layouts[profile] = layout
        state.update(layout)
        state["active_workspace"] = profile
        state["workspace_layouts"] = layouts
        self._ui_layout_state = normalize_gui_layout_state(state)

    def activate_workspace_profile(
        self,
        profile: str,
        *,
        persist: bool = True,
        capture_current: bool = True,
    ) -> None:
        """Apply a saved engineering workspace layout and select its primary surfaces."""
        selected = str(profile or "").strip().casefold()
        if selected not in GUI_WORKSPACE_PROFILES:
            raise ValueError(f"unsupported GUI workspace profile: {profile!r}")

        if capture_current and hasattr(self, "main_panes"):
            self._capture_current_workspace_layout()
        self._restore_focus_workspace_snapshot(status=False)

        state = dict(self._ui_layout_state)
        layout = dict(state["workspace_layouts"][selected])
        state.update(layout)
        state["active_workspace"] = selected
        self._ui_layout_state = normalize_gui_layout_state(state)
        self.workspace_profile_var.set(selected)

        self.navigator_panel_visible_var.set(bool(layout["navigator_visible"]))
        self.output_panel_visible_var.set(bool(layout["output_visible"]))
        self._sync_navigator_panel_visibility()
        self._sync_output_panel_visibility()
        workspace = getattr(self, "spatial_workspace", None)
        if workspace is not None:
            workspace.set_inspector_visible(bool(layout["inspector_visible"]))

        if selected == "start":
            self._refresh_start_center()
            self.notebook.select(self.start_center)
        elif selected == "design":
            self.notebook.select(self.spatial_workspace)
        elif selected == "simulation":
            self._refresh_simulation_workspace()
            self.notebook.select(self.simulation_workspace)
            self.output_notebook.select(self.result_text.master)
        elif selected == "verification":
            self.notebook.select(self.spatial_workspace)
            self.output_notebook.select(self.problems_panel)
        elif selected == "evidence":
            self.notebook.select(self.proofgraph_viewer)
            self.output_notebook.select(self.evidence_text.master)
        elif selected == "reporting":
            self._refresh_engineering_panels()
            self.notebook.select(self.reporting_workspace)
            self.output_notebook.select(self.report_text.master)

        label = WORKSPACE_LABELS[selected]
        self.workspace_status_var.set(f"Workspace: {label}")
        self.status_var.set(f"{label} workspace active")
        self.root.update_idletasks()
        self.root.after_idle(self._apply_saved_panel_sashes)
        if persist:
            self.root.after_idle(self._save_ui_layout_state)

    def _capture_ui_layout_state(self) -> dict:
        self._capture_current_workspace_layout()
        state = dict(self._ui_layout_state)
        screen_width = max(1, int(self.root.winfo_screenwidth()))
        screen_height = max(1, int(self.root.winfo_screenheight()))
        minimum_width = min(1050, screen_width)
        minimum_height = min(680, screen_height)
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        if width < minimum_width:
            width = int(state.get("window_width", 1440))
        if height < minimum_height:
            height = int(state.get("window_height", 900))
        width, height = clamp_window_size_to_display(
            width,
            height,
            screen_width,
            screen_height,
        )
        state.update(
            {
                "theme": normalize_theme_name(self.theme_var.get()),
                "density": normalize_density_name(self.density_var.get()),
                "recent_projects": [
                    str(path)
                    for path in self._recent_project_paths[:8]
                ],
                "navigator_favorites": self._capture_navigator_favorites_state(),
                "window_width": width,
                "window_height": height,
                "active_workspace": self._current_workspace_profile(),
            }
        )
        self._ui_layout_state = normalize_gui_layout_state(state)
        return dict(self._ui_layout_state)

    def _save_ui_layout_state(self) -> None:
        try:
            save_gui_layout_state(
                self._ui_state_path,
                self._capture_ui_layout_state(),
            )
        except Exception:
            return

    def _restore_ui_layout_state(self) -> None:
        self._focus_workspace_snapshot = None
        self.focus_workspace_var.set(False)
        state = self._ui_layout_state
        self.theme_var.set(normalize_theme_name(state["theme"]))
        self.density_var.set(normalize_density_name(state["density"]))
        self.set_density(self.density_var.get(), persist=False)
        self.activate_workspace_profile(
            state["active_workspace"],
            persist=False,
            capture_current=False,
        )
        self.root.update_idletasks()
        self._apply_saved_panel_sashes()
        self.status_var.set("Ready")

    def _apply_menu_theme(self, menu: tk.Menu) -> None:
        palette = self._theme_palette
        try:
            menu.configure(
                background=palette["surface"],
                foreground=palette["text"],
                activebackground=palette["selection"],
                activeforeground=palette["selection_text"],
                disabledforeground=palette["disabled"],
                selectcolor=palette["accent"],
            )
        except tk.TclError:
            return
        end = menu.index("end")
        if end is None:
            return
        for index in range(end + 1):
            try:
                submenu_name = menu.entrycget(index, "menu")
            except tk.TclError:
                continue
            if not submenu_name:
                continue
            try:
                submenu = menu.nametowidget(submenu_name)
            except (KeyError, tk.TclError):
                continue
            if isinstance(submenu, tk.Menu):
                self._apply_menu_theme(submenu)

    def _apply_theme_to_native_widgets(self, *, redraw: bool = True) -> None:
        palette = self._theme_palette
        text_widgets = [
            getattr(self, name, None)
            for name in (
                "input_text",
                "result_text",
                "report_text",
                "diagnostics_text",
                "verification_text",
                "console_text",
                "evidence_text",
            )
        ]
        problems_panel = getattr(self, "problems_panel", None)
        if problems_panel is not None:
            text_widgets.append(getattr(problems_panel, "detail", None))
        for widget in text_widgets:
            if isinstance(widget, tk.Text):
                widget.configure(
                    background=palette["field"],
                    foreground=palette["field_text"],
                    insertbackground=palette["text"],
                    selectbackground=palette["selection"],
                    selectforeground=palette["selection_text"],
                )

        plot_canvas = getattr(self, "plot_canvas", None)
        if isinstance(plot_canvas, tk.Canvas):
            plot_canvas.configure(
                background=palette["plot"],
                highlightbackground=palette["border"],
            )

        workspace = getattr(self, "spatial_workspace", None)
        if workspace is not None:
            workspace.apply_theme(self.theme_var.get(), redraw=redraw)

        reporting = getattr(self, "reporting_workspace", None)
        if reporting is not None:
            reporting.apply_theme(self.theme_var.get())

        task_center = getattr(self, "task_center", None)
        if task_center is not None:
            task_center.apply_theme(self.theme_var.get())

        proofgraph = getattr(self, "proofgraph_viewer", None)
        if proofgraph is not None:
            proofgraph.apply_theme(self.theme_var.get())

        menubar = getattr(self, "menubar", None)
        if isinstance(menubar, tk.Menu):
            self._apply_menu_theme(menubar)

        if redraw and isinstance(plot_canvas, tk.Canvas):
            self._draw_plot()

    def set_theme(self, value: str, *, persist: bool = True) -> None:
        theme = normalize_theme_name(value)
        self.theme_var.set(theme)
        self._theme_palette = configure_ttk_theme(
            self.root,
            theme,
            density=self.density_var.get(),
        )
        self._apply_theme_to_native_widgets()
        state = dict(getattr(self, "_ui_layout_state", {}))
        state["theme"] = theme
        self._ui_layout_state = normalize_gui_layout_state(state)
        if persist:
            self._save_ui_layout_state()
        self.status_var.set(f"Theme: {theme.title()}")

    def toggle_theme(self) -> None:
        self.set_theme("dark" if self.theme_var.get() == "light" else "light")

    def set_density(self, value: str, *, persist: bool = True) -> None:
        density = normalize_density_name(value)
        self.density_var.set(density)
        self._theme_palette = configure_ttk_theme(
            self.root,
            self.theme_var.get(),
            density=density,
        )
        self._apply_theme_to_native_widgets()
        state = dict(getattr(self, "_ui_layout_state", {}))
        state["density"] = density
        self._ui_layout_state = normalize_gui_layout_state(state)
        if persist:
            self._save_ui_layout_state()
        label = "Compact / Engineering" if density == "compact" else "Comfortable"
        self.status_var.set(f"Density: {label}")

    def _restore_focus_workspace_snapshot(self, *, status: bool = True) -> bool:
        snapshot = getattr(self, "_focus_workspace_snapshot", None)
        if snapshot is None:
            self.focus_workspace_var.set(False)
            return False
        self._focus_workspace_snapshot = None
        self.focus_workspace_var.set(False)
        self.navigator_panel_visible_var.set(
            bool(snapshot["navigator_visible"])
        )
        self.output_panel_visible_var.set(bool(snapshot["output_visible"]))
        self._sync_navigator_panel_visibility()
        self._sync_output_panel_visibility()
        workspace = getattr(self, "spatial_workspace", None)
        if workspace is not None:
            workspace.set_inspector_visible(
                bool(snapshot["inspector_visible"])
            )
        self.root.after_idle(self._apply_saved_panel_sashes)
        if status:
            self.status_var.set("Focus Workspace disabled")
        return True

    def set_focus_workspace(self, enabled: bool) -> None:
        enabled = bool(enabled)
        workspace = getattr(self, "spatial_workspace", None)
        if enabled:
            if self._focus_workspace_snapshot is None:
                self._remember_current_panel_fractions()
                self._focus_workspace_snapshot = {
                    "navigator_visible": bool(
                        self.navigator_panel_visible_var.get()
                    ),
                    "output_visible": bool(
                        self.output_panel_visible_var.get()
                    ),
                    "inspector_visible": bool(
                        workspace is not None and workspace.inspector_visible()
                    ),
                }
            self.focus_workspace_var.set(True)
            self.navigator_panel_visible_var.set(False)
            self.output_panel_visible_var.set(False)
            self._sync_navigator_panel_visibility()
            self._sync_output_panel_visibility()
            if workspace is not None:
                workspace.set_inspector_visible(False)
            self.status_var.set("Focus Workspace enabled")
            return
        self._restore_focus_workspace_snapshot()

    def _sync_focus_workspace(self) -> None:
        self.set_focus_workspace(bool(self.focus_workspace_var.get()))

    def toggle_focus_workspace(self) -> None:
        self.set_focus_workspace(
            self._focus_workspace_snapshot is None
        )

    def set_fullscreen_workspace(self, enabled: bool) -> None:
        """Toggle native full-screen without changing project or panel state."""
        target = bool(enabled)
        try:
            self.root.attributes("-fullscreen", target)
        except tk.TclError:
            self.fullscreen_var.set(False)
            self.status_var.set("Full-screen workspace unavailable on this display")
            return
        self.fullscreen_var.set(target)
        self.status_var.set(
            "Full-screen workspace enabled — F11 or Esc to exit"
            if target
            else "Full-screen workspace disabled"
        )

    def _sync_fullscreen_workspace(self) -> None:
        self.set_fullscreen_workspace(bool(self.fullscreen_var.get()))

    def toggle_fullscreen_workspace(self) -> None:
        self.set_fullscreen_workspace(not bool(self.fullscreen_var.get()))

    def exit_fullscreen_workspace(self) -> None:
        if bool(self.fullscreen_var.get()):
            self.set_fullscreen_workspace(False)

    def _on_navigator_visibility_requested(self) -> None:
        target = bool(self.navigator_panel_visible_var.get())
        self._restore_focus_workspace_snapshot(status=False)
        self.navigator_panel_visible_var.set(target)
        self._sync_navigator_panel_visibility()

    def _on_output_visibility_requested(self) -> None:
        target = bool(self.output_panel_visible_var.get())
        self._restore_focus_workspace_snapshot(status=False)
        self.output_panel_visible_var.set(target)
        self._sync_output_panel_visibility()

    def _sync_navigator_panel_visibility(self) -> None:
        panes = getattr(self, "main_panes", None)
        panel = getattr(self, "navigator_panel", None)
        if panes is None or panel is None:
            return
        visible = bool(self.navigator_panel_visible_var.get())
        present = self._paned_contains(panes, panel)
        if visible and not present:
            panes.insert(0, panel, weight=1)
            self.root.after_idle(self._apply_saved_panel_sashes)
        elif not visible and present:
            self._remember_current_panel_fractions()
            panes.forget(panel)
        state = "shown" if visible else "hidden"
        self.status_var.set(f"Project Navigator {state}")

    def _sync_output_panel_visibility(self) -> None:
        panes = getattr(self, "workspace_panes", None)
        panel = getattr(self, "output_panel", None)
        if panes is None or panel is None:
            return
        visible = bool(self.output_panel_visible_var.get())
        present = self._paned_contains(panes, panel)
        if visible and not present:
            panes.add(panel, weight=1)
            self.root.after_idle(self._apply_saved_panel_sashes)
        elif not visible and present:
            self._remember_current_panel_fractions()
            panes.forget(panel)
        state = "shown" if visible else "hidden"
        self.status_var.set(f"Output / Verification {state}")

    def hide_navigator_panel(self) -> None:
        self._restore_focus_workspace_snapshot(status=False)
        self.navigator_panel_visible_var.set(False)
        self._sync_navigator_panel_visibility()

    def toggle_navigator_panel(self) -> None:
        target = not bool(self.navigator_panel_visible_var.get())
        self._restore_focus_workspace_snapshot(status=False)
        self.navigator_panel_visible_var.set(target)
        self._sync_navigator_panel_visibility()

    def hide_output_panel(self) -> None:
        self._restore_focus_workspace_snapshot(status=False)
        self.output_panel_visible_var.set(False)
        self._sync_output_panel_visibility()

    def toggle_output_panel(self) -> None:
        target = not bool(self.output_panel_visible_var.get())
        self._restore_focus_workspace_snapshot(status=False)
        self.output_panel_visible_var.set(target)
        self._sync_output_panel_visibility()

    def show_problems_panel(self) -> None:
        self._restore_focus_workspace_snapshot(status=False)
        self.output_panel_visible_var.set(True)
        self._sync_output_panel_visibility()
        panel = getattr(self, "problems_panel", None)
        notebook = getattr(self, "output_notebook", None)
        if panel is not None and notebook is not None:
            notebook.select(panel)
        self.status_var.set("Output: Problems")

    def toggle_design_inspector(self) -> None:
        workspace = getattr(self, "spatial_workspace", None)
        if workspace is None:
            return
        target = not workspace.inspector_visible()
        self._restore_focus_workspace_snapshot(status=False)
        self._activate_spatial_workspace()
        if workspace.inspector_visible():
            self._remember_current_panel_fractions()
        workspace.set_inspector_visible(target)
        if workspace.inspector_visible():
            self.root.after_idle(self._apply_saved_panel_sashes)

    def _apply_default_panel_sashes(self) -> None:
        if (
            self.navigator_panel_visible_var.get()
            and self._paned_contains(self.main_panes, self.navigator_panel)
        ):
            width = self.main_panes.winfo_width()
            if width > 1:
                self.main_panes.sashpos(
                    0,
                    min(360, max(240, int(width * 0.20))),
                )
        if (
            self.output_panel_visible_var.get()
            and self._paned_contains(self.workspace_panes, self.output_panel)
        ):
            height = self.workspace_panes.winfo_height()
            if height > 1:
                self.workspace_panes.sashpos(
                    0,
                    max(320, int(height * 0.72)),
                )
        workspace = getattr(self, "spatial_workspace", None)
        if workspace is not None and workspace.inspector_visible():
            width = workspace._body.winfo_width()
            if width > 1:
                workspace._body.sashpos(0, max(520, int(width * 0.78)))

    def reset_panel_layout(self) -> None:
        self._restore_focus_workspace_snapshot(status=False)
        profile = self._current_workspace_profile()
        defaults = normalize_gui_layout_state({})["workspace_layouts"][profile]
        state = dict(self._ui_layout_state)
        layouts = copy.deepcopy(state["workspace_layouts"])
        layouts[profile] = defaults
        state["workspace_layouts"] = layouts
        state.update(defaults)
        state["active_workspace"] = profile
        self._ui_layout_state = normalize_gui_layout_state(state)
        self.activate_workspace_profile(
            profile,
            persist=False,
            capture_current=False,
        )
        self.root.after_idle(self._save_ui_layout_state)
        self.status_var.set(
            f"{WORKSPACE_LABELS[profile]} workspace layout reset"
        )

    def _activate_proofgraph_workspace(self) -> None:
        viewer = getattr(self, "proofgraph_viewer", None)
        if viewer is None:
            return
        self.activate_workspace_profile("evidence")
        self.notebook.select(viewer)
        self.workspace_status_var.set("Workspace: ProofGraph")

    def _navigate_proofgraph_node(self, node: dict) -> bool:
        raw = node.get("raw", {}) if isinstance(node, dict) else {}
        if not isinstance(raw, dict):
            raw = {}

        candidates: list[str] = []
        if node.get("type") == "model_object":
            candidates.append(str(node.get("id") or ""))
        for key in ("subject_ref", "cleanroomx_entity_id"):
            value = str(raw.get(key) or "").strip()
            if value:
                candidates.append(value)

        provenance = raw.get("provenance")
        if isinstance(provenance, list):
            for record in provenance:
                if not isinstance(record, dict):
                    continue
                value = str(record.get("cleanroomx_entity_id") or "").strip()
                if value:
                    candidates.append(value)

        workspace = getattr(self, "spatial_workspace", None)
        if workspace is not None:
            for candidate in dict.fromkeys(value for value in candidates if value):
                for kind in ("room", "device"):
                    if workspace.select_item(kind, candidate, notify=True):
                        self._activate_spatial_workspace()
                        workspace.fit_selected()
                        self.status_var.set(
                            f"ProofGraph: opened {kind} {candidate}"
                        )
                        return True

        if node.get("type") == "requirement":
            self.status_var.set(
                f"ProofGraph requirement selected: {node.get('label') or node.get('id')}"
            )
        else:
            self.status_var.set(
                "ProofGraph node has no directly navigable CleanroomX spatial object"
            )
        return False

    @staticmethod
    def _proofgraph_documents_from_records(records: list[dict]) -> list[dict]:
        documents: list[dict] = []
        seen: set[str] = set()
        for record in reversed(records):
            raw_graphs = record.get("proofgraphs", [])
            if not isinstance(raw_graphs, list):
                continue
            for document in raw_graphs:
                if not isinstance(document, dict):
                    continue
                digest = str(document.get("graph_sha256") or "")
                identity = digest or str(document.get("id") or "")
                if not identity or identity in seen:
                    continue
                seen.add(identity)
                documents.append(document)
        return documents

    def _refresh_engineering_panels(self) -> dict | None:
        panel = getattr(self, "problems_panel", None)
        if panel is None:
            return None
        diagnostics = panel.refresh()
        verification_summary: dict = {}
        records: list[dict] = []
        proofgraphs: list[dict] = []

        try:
            currency = assess_project_verification_currency(
                self.project,
                base_dir=self._base_dir(),
            )
            summary = currency.get("summary", {})
            verification_summary = (
                dict(summary) if isinstance(summary, dict) else {}
            )
            lines = [
                "CURRENT VERIFICATION CURRENCY",
                "",
                f"Configured analyses: {summary.get('configured_analysis_count', 0)}",
                f"Current: {summary.get('current_count', 0)}",
                f"Stale: {summary.get('stale_count', 0)}",
                f"Not verified: {summary.get('not_verified_count', 0)}",
                f"Not configured: {summary.get('not_configured_count', 0)}",
                (
                    "Dependency freshness unverifiable: "
                    f"{summary.get('dependency_freshness_unverifiable_count', 0)}"
                ),
                "",
            ]
            for item in currency.get("analyses", []):
                lines.append(
                    "{name} [{kind}] — {state}".format(
                        name=item.get("analysis_name")
                        or item.get("analysis_id")
                        or "analysis",
                        kind=item.get("analysis_kind", "unknown"),
                        state=item.get("state", "unknown"),
                    )
                )
            self._set_text(
                self.verification_text,
                "\n".join(lines).rstrip() + "\n",
            )
        except Exception as exc:
            self._set_text(
                self.verification_text,
                f"Verification currency unavailable: {exc}\n",
            )

        try:
            records = verification_run_history_records(self.project.metadata)
            proofgraphs = self._proofgraph_documents_from_records(records)
            viewer = getattr(self, "proofgraph_viewer", None)
            if viewer is not None:
                viewer.set_documents(proofgraphs)
            lines = [
                "PERSISTED VERIFICATION EVIDENCE",
                "",
                f"Retained records: {len(records)}",
            ]
            if not records:
                lines.append("No persisted project-verification evidence.")
            else:
                for record in reversed(records[-20:]):
                    verification = record.get("verification", {})
                    lines.append(
                        "#{sequence} · {analysis} · {status} · {completed}".format(
                            sequence=record.get("sequence", "?"),
                            analysis=record.get("analysis_name")
                            or record.get("analysis_id")
                            or "analysis",
                            status=verification.get("status", "unknown"),
                            completed=record.get("completed_at_utc", ""),
                        )
                    )
            self._set_text(
                self.evidence_text,
                "\n".join(lines).rstrip() + "\n",
            )
        except Exception as exc:
            viewer = getattr(self, "proofgraph_viewer", None)
            if viewer is not None:
                viewer.set_documents([])
            self._set_text(
                self.evidence_text,
                f"Verification evidence unavailable: {exc}\n",
            )

        diagnostic_summary = (
            diagnostics.get("summary", {})
            if isinstance(diagnostics, dict)
            else {}
        )
        if isinstance(diagnostics, dict):
            error_count = int(diagnostic_summary.get("error_count", 0) or 0)
            warning_count = int(diagnostic_summary.get("warning_count", 0) or 0)
            if error_count or warning_count:
                self.diagnostics_status_var.set(
                    f"Problems: {error_count}E {warning_count}W"
                )
            else:
                self.diagnostics_status_var.set("Problems: Clear")
        else:
            self.diagnostics_status_var.set("Problems: unavailable")
        location = str(self.project_path) if self.project_path else "Unsaved project"
        console_lines = [
            f"CleanroomX {__version__}",
            f"Project: {self.project.name}",
            f"Location: {location}",
            f"Analyses: {len(self.project.analyses)}",
            "Project diagnostics: "
            + str(diagnostic_summary.get("status", "unavailable")).upper(),
        ]
        if self.last_run is not None:
            console_lines.append(
                f"Last run: {self.last_run.title} — {self.last_run.status}"
            )
        self._set_text(self.console_text, "\n".join(console_lines) + "\n")

        reporting = getattr(self, "reporting_workspace", None)
        if reporting is not None:
            reporting.refresh(
                {
                    "project_name": self.project.name,
                    "source": location,
                    "saved": (
                        self.project_path is not None
                        and not self._has_unsaved_changes()
                    ),
                    "diagnostics": diagnostic_summary,
                    "verification": verification_summary,
                    "last_run": (
                        {
                            "title": self.last_run.title,
                            "status": self.last_run.status,
                        }
                        if self.last_run is not None
                        else None
                    ),
                    "evidence_record_count": len(records),
                    "proofgraph_count": len(proofgraphs),
                }
            )
        return diagnostics

    def _schedule_project_diagnostics_refresh(self, delay_ms: int = 300) -> None:
        if getattr(self, "problems_panel", None) is None:
            return
        pending = getattr(self, "_project_diagnostics_after_id", None)
        if pending is not None:
            try:
                self.root.after_cancel(pending)
            except tk.TclError:
                pass
        self._project_diagnostics_after_id = self.root.after(
            delay_ms,
            self._run_scheduled_engineering_refresh,
        )

    def _run_scheduled_engineering_refresh(self) -> None:
        self._project_diagnostics_after_id = None
        self._refresh_engineering_panels()

    def _navigate_project_diagnostic(self, issue: dict) -> None:
        element = issue.get("element", {})
        if not isinstance(element, dict):
            element = {}
        element_type = str(element.get("type") or "")
        element_id = str(element.get("id") or "")

        if element_type == "analysis" and element_id:
            if self.analysis_tree.exists(element_id):
                self.analysis_tree.selection_set(element_id)
                self.analysis_tree.focus(element_id)
                self.analysis_tree.see(element_id)
                self._on_analysis_selected()
                self.notebook.select(self.input_tab)
                analysis = self._current_analysis()
                self.selection_status_var.set(
                    f"Analysis: {analysis.name}"
                    if analysis is not None
                    else f"Analysis: {element_id}"
                )
                return

        if element_type == "spatial_element" and element_id:
            workspace = self.spatial_workspace
            for kind in ("room", "device"):
                if workspace.select_item(kind, element_id, notify=True):
                    self._activate_spatial_workspace()
                    workspace.fit_selected()
                    self._sync_spatial_selection_status()
                    return

        self.status_var.set(
            f"Diagnostic {issue.get('rule', '')}: no spatial navigation target"
        )

    def export_project_diagnostics(self, _result: dict | None = None) -> None:
        try:
            if self._editor_analysis() is not None:
                self._commit_editor()
            else:
                self._sync_metadata()
        except Exception as exc:
            messagebox.showerror(
                "Cannot export project diagnostics",
                str(exc),
                parent=self.root,
            )
            return

        result = self._refresh_engineering_panels()
        if result is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export CleanroomX project diagnostics",
            defaultextension=".json",
            filetypes=[
                ("CleanroomX diagnostics JSON", "*.json"),
                ("Markdown report", "*.md"),
            ],
        )
        if not path:
            return

        destination = Path(path)
        if destination.suffix.lower() in {".md", ".markdown"}:
            content = markdown_project_diagnostics_report(result)
        else:
            content = (
                json.dumps(
                    result,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                )
                + "\n"
            )
        self._write_export_file(
            path,
            content,
            label="Project diagnostics",
        )

    def _engineering_search_entries(self) -> list[SearchEntry]:
        """Index canonical project data already available in the workstation."""
        layout = self.project.metadata.get(SPATIAL_METADATA_KEY, {})
        if not isinstance(layout, dict):
            layout = {}

        diagnostics = getattr(
            getattr(self, "problems_panel", None),
            "last_result",
            None,
        )
        if not isinstance(diagnostics, dict):
            diagnostics = {}

        requirement_snapshot: dict = {}
        try:
            requirement_snapshot = project_requirement_traceability_snapshot(
                self.project
            )
        except Exception:
            requirement_snapshot = {}

        proofgraph_documents: list[dict] = []
        try:
            records = verification_run_history_records(self.project.metadata)
            proofgraph_documents = self._proofgraph_documents_from_records(records)
        except Exception:
            proofgraph_documents = []

        return build_engineering_search_entries(
            project=self.project,
            spatial_layout=layout,
            diagnostics=diagnostics,
            requirement_snapshot=requirement_snapshot,
            proofgraph_documents=proofgraph_documents,
        )

    def _navigate_engineering_search_result(self, entry: SearchEntry) -> None:
        target_type = entry.target_type
        target_id = entry.target_id

        if target_type == "project":
            self._activate_start_workspace()
            self.selection_status_var.set(f"Selected: {entry.label}")
            return

        if target_type == "analysis" and target_id:
            if self.analysis_tree.exists(target_id):
                self.analysis_tree.selection_set(target_id)
                self.analysis_tree.focus(target_id)
                self.analysis_tree.see(target_id)
                self._on_analysis_selected()
                if self._editor_analysis_id == target_id:
                    self._activate_analysis_input_workspace()
                    self.selection_status_var.set(f"Selected: {entry.label}")
            return

        if target_type in {"room", "device"} and target_id:
            workspace = getattr(self, "spatial_workspace", None)
            if workspace is not None and workspace.select_item(
                target_type,
                target_id,
                notify=True,
            ):
                self._activate_spatial_workspace()
                workspace.fit_selected()
                self._sync_spatial_selection_status()
                return

        if target_type == "diagnostic" and isinstance(entry.payload, dict):
            self.show_problems_panel()
            self._navigate_project_diagnostic(entry.payload)
            self.selection_status_var.set(f"Selected: {entry.label}")
            return

        if target_type == "requirement":
            self.show_requirements_traceability(target_id or None)
            self.selection_status_var.set(
                f"Selected requirement: {target_id or entry.label}"
            )
            return

        if target_type == "mapping":
            self.show_requirements_traceability(mapping_id=target_id or None)
            self.selection_status_var.set(
                f"Selected evidence mapping: {target_id or entry.label}"
            )
            return

        if target_type == "evidence":
            self._activate_proofgraph_workspace()
            viewer = getattr(self, "proofgraph_viewer", None)
            payload = entry.payload if isinstance(entry.payload, dict) else {}
            focused = False
            if viewer is not None and target_id:
                focused = viewer.focus_node(
                    target_id,
                    node_type=str(payload.get("type") or ""),
                    graph_id=str(payload.get("_proofgraph_id") or ""),
                    node_key=str(payload.get("_proofgraph_key") or ""),
                )
            self.selection_status_var.set(f"Selected evidence: {entry.label}")
            self.status_var.set(
                (
                    f"ProofGraph focused on search result: {entry.label}"
                    if focused
                    else (
                        "ProofGraph opened; search target is not present in the "
                        f"active persisted graph: {entry.label}"
                    )
                )
            )
            return

        self.status_var.set(
            f"Search result has no direct navigation target: {entry.label}"
        )

    def show_global_search(self) -> None:
        existing = getattr(self, "_global_search_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.search.focus_set()
                    return
            except tk.TclError:
                pass

        def clear_reference() -> None:
            self._global_search_window = None

        entries = self._engineering_search_entries()
        self._global_search_window = GlobalEngineeringSearch(
            self.root,
            entries=entries,
            on_activate=self._navigate_engineering_search_result,
            on_close=clear_reference,
        )
        self.status_var.set(
            f"Global engineering search indexed {len(entries)} project entities"
        )

    def _command_palette_commands(self) -> list[PaletteCommand]:
        return [
            PaletteCommand(
                "file.new",
                "New Project",
                "File",
                self.new_project,
                shortcut="Ctrl+N",
                keywords=("create", "project"),
            ),
            PaletteCommand(
                "file.open",
                "Open Project",
                "File",
                self.open_project,
                shortcut="Ctrl+O",
                keywords=("load", "project"),
            ),
            PaletteCommand(
                "file.save",
                "Save Project",
                "File",
                self.save_project,
                shortcut="Ctrl+S",
            ),
            PaletteCommand(
                "search.global",
                "Global Engineering Search",
                "Navigation",
                self.show_global_search,
                shortcut="Ctrl+K",
                keywords=(
                    "find",
                    "room",
                    "device",
                    "analysis",
                    "diagnostic",
                    "requirement",
                    "evidence",
                ),
            ),
            PaletteCommand(
                "workspace.start",
                "Open Start Center",
                "Window",
                self._activate_start_workspace,
                keywords=("home", "recent", "example"),
            ),
            PaletteCommand(
                "workspace.design",
                "Switch to Design Workspace",
                "Workspace",
                lambda: self.activate_workspace_profile("design"),
                shortcut="Ctrl+Alt+1",
                keywords=("layout", "panels", "canvas", "inspector"),
            ),
            PaletteCommand(
                "workspace.simulation",
                "Switch to Simulation Workspace",
                "Workspace",
                lambda: self.activate_workspace_profile("simulation"),
                shortcut="Ctrl+Alt+2",
                keywords=("analysis", "results", "run", "solver"),
            ),
            PaletteCommand(
                "workspace.verification",
                "Switch to Verification Workspace",
                "Workspace",
                lambda: self.activate_workspace_profile("verification"),
                shortcut="Ctrl+Alt+3",
                keywords=("diagnostics", "problems", "requirements"),
            ),
            PaletteCommand(
                "workspace.evidence",
                "Switch to Evidence Workspace",
                "Workspace",
                lambda: self.activate_workspace_profile("evidence"),
                shortcut="Ctrl+Alt+4",
                keywords=("proofgraph", "provenance", "traceability"),
            ),
            PaletteCommand(
                "workspace.reporting",
                "Switch to Reporting Workspace",
                "Workspace",
                lambda: self.activate_workspace_profile("reporting"),
                shortcut="Ctrl+Alt+5",
                keywords=("report", "plot", "export"),
            ),
            PaletteCommand(
                "workspace.2d",
                "Open 2D Workspace",
                "Design",
                lambda: self._activate_spatial_workspace("2d"),
                shortcut="Ctrl+1",
                keywords=("plan", "viewport"),
            ),
            PaletteCommand(
                "workspace.3d",
                "Open 3D Workspace",
                "Design",
                lambda: self._activate_spatial_workspace("3d"),
                shortcut="Ctrl+2",
                keywords=("model", "viewport"),
            ),
            PaletteCommand(
                "workspace.split",
                "Open Split 2D + 3D Workspace",
                "Design",
                lambda: self._activate_spatial_workspace("split"),
                shortcut="Ctrl+3",
                keywords=("viewport",),
            ),
            PaletteCommand(
                "design.fit",
                "Fit Spatial Views",
                "Design",
                lambda: self.spatial_workspace.fit_views(),
                keywords=("zoom", "model"),
            ),
            PaletteCommand(
                "workspace.focus",
                "Toggle Focus Workspace",
                "Window",
                self.toggle_focus_workspace,
                shortcut="Ctrl+Shift+F",
                keywords=("panels", "viewport", "zen"),
            ),
            PaletteCommand(
                "workspace.fullscreen",
                "Toggle Full-screen Workspace",
                "Window",
                self.toggle_fullscreen_workspace,
                shortcut="F11",
                keywords=("fullscreen", "presentation", "viewport", "window"),
            ),
            PaletteCommand(
                "bim.import",
                "Import IFC Spatial Layout",
                "BIM",
                self.import_ifc_spatial_layout,
                keywords=("ifc", "bim", "model"),
            ),
            PaletteCommand(
                "analysis.validate",
                "Validate Current Analysis Input",
                "Analysis",
                self.validate_current,
                keywords=("check", "input"),
            ),
            PaletteCommand(
                "analysis.run",
                "Run Current Analysis",
                "Analysis",
                self.run_current,
                shortcut="F5",
                keywords=("solver", "calculate"),
            ),
            PaletteCommand(
                "verification.refresh",
                "Refresh Project Diagnostics",
                "Verification",
                self._refresh_engineering_panels,
                shortcut="F8",
                keywords=("problems", "errors", "warnings"),
            ),
            PaletteCommand(
                "verification.run",
                "Verify Project Requirements",
                "Verification",
                self.run_project_requirements_verification,
                keywords=("requirements", "compliance"),
            ),
            PaletteCommand(
                "verification.persist",
                "Verify and Persist Project Requirements",
                "Verification",
                self.persist_project_requirements_verification,
                keywords=("requirements", "evidence"),
            ),
            PaletteCommand(
                "proofgraph.open",
                "Open ProofGraph Explorer",
                "Evidence",
                self._activate_proofgraph_workspace,
                keywords=("proof", "provenance", "traceability"),
            ),
            PaletteCommand(
                "traceability.open",
                "Open Requirements Traceability",
                "Verification",
                self.show_requirements_traceability,
                keywords=("requirements", "evidence", "trace"),
            ),
            PaletteCommand(
                "workspace.reports",
                "Open Reporting Workspace",
                "Report",
                self._activate_reporting_workspace,
                keywords=("report", "release", "dossier", "summary"),
            ),
            PaletteCommand(
                "report.summary",
                "Export Selected Report Summary",
                "Report",
                self.export_selected_reporting_summary,
                keywords=("report", "summary", "sections"),
            ),
            PaletteCommand(
                "report.dossier",
                "Export Project Engineering Dossier",
                "Report",
                self.export_project_engineering_dossier,
                keywords=("report", "evidence"),
            ),
            PaletteCommand(
                "diagnostics.open",
                "Open Problems",
                "Verification",
                self.show_problems_panel,
                keywords=("diagnostics", "issues", "errors", "warnings"),
            ),
            PaletteCommand(
                "analysis.history",
                "Open Run History",
                "Simulation",
                self.show_run_history,
                keywords=("runs", "results", "evidence", "history"),
            ),
            PaletteCommand(
                "verification.history",
                "Open Verification History",
                "Verification",
                self.show_verification_history,
                keywords=("requirements", "evidence", "history"),
            ),
            PaletteCommand(
                "panel.navigator",
                "Toggle Project Navigator",
                "Workspace",
                self.toggle_navigator_panel,
                shortcut="Ctrl+B",
                keywords=("panel", "tree", "project"),
            ),
            PaletteCommand(
                "panel.output",
                "Toggle Output / Verification Panel",
                "Workspace",
                self.toggle_output_panel,
                shortcut="Ctrl+J",
                keywords=("panel", "results", "diagnostics"),
            ),
            PaletteCommand(
                "panel.inspector",
                "Toggle Design Inspector",
                "Workspace",
                self.toggle_design_inspector,
                shortcut="Ctrl+I",
                keywords=("panel", "properties", "inspector"),
            ),
            PaletteCommand(
                "workspace.reset_layout",
                "Reset Active Workspace Layout",
                "Workspace",
                self.reset_panel_layout,
                keywords=("panels", "splitters", "restore", "default"),
            ),
            PaletteCommand(
                "recovery.open",
                "Open Recovery Center",
                "Project",
                self.show_recovery_center,
                keywords=("autosave", "restore"),
            ),
        ]

    def show_command_palette(self) -> None:
        existing = getattr(self, "_command_palette_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.search.focus_set()
                    return
            except tk.TclError:
                pass

        def clear_reference() -> None:
            self._command_palette_window = None

        self._command_palette_window = CommandPalette(
            self.root,
            commands=self._command_palette_commands(),
            on_close=clear_reference,
        )

    def _activate_start_workspace(self, *, apply_layout: bool = True) -> None:
        if apply_layout and hasattr(self, "notebook"):
            self.activate_workspace_profile("start")
            return
        if hasattr(self, "notebook") and hasattr(self, "start_center"):
            self._refresh_start_center()
            self.notebook.select(self.start_center)
            self.workspace_profile_var.set("start")
            self.workspace_status_var.set("Workspace: Start")

    def _activate_reporting_workspace(self) -> None:
        if not hasattr(self, "notebook") or not hasattr(
            self, "reporting_workspace"
        ):
            return
        self.activate_workspace_profile("reporting")

    def _recent_project_records(self) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        active_path = (
            self.project_path.resolve(strict=False)
            if self.project_path is not None
            else None
        )
        for path in getattr(self, "_recent_project_paths", []):
            resolved = path.resolve(strict=False)
            name = path.name
            if name.endswith(".cleanroomx.json"):
                name = name[: -len(".cleanroomx.json")]
            else:
                name = path.stem
            if active_path is not None and resolved == active_path:
                name = self.project.name or name
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime).strftime(
                    "%Y-%m-%d %H:%M"
                )
            except OSError:
                modified = "Unavailable"
            records.append(
                {
                    "name": name,
                    "path": str(path),
                    "modified": modified,
                }
            )
        return records

    def _refresh_start_center(self) -> None:
        start_center = getattr(self, "start_center", None)
        if start_center is not None:
            start_center.set_recent_projects(self._recent_project_records())

    def _remember_recent_project(self, path: str | Path) -> None:
        candidate = Path(path).resolve(strict=False)
        recent_paths = list(getattr(self, "_recent_project_paths", []))
        self._recent_project_paths = [
            existing
            for existing in recent_paths
            if existing.resolve(strict=False) != candidate
        ]
        self._recent_project_paths.insert(0, candidate)
        del self._recent_project_paths[8:]
        self._refresh_start_center()
        self._save_ui_layout_state()

    def _forget_recent_project(self, path: str | Path) -> None:
        candidate = Path(path).resolve(strict=False)
        self._recent_project_paths = [
            existing
            for existing in self._recent_project_paths
            if existing.resolve(strict=False) != candidate
        ]
        self._refresh_start_center()
        self._save_ui_layout_state()

    def _open_recent_project_from_start(self, path: str) -> None:
        if self._running:
            messagebox.showwarning(
                "Analysis running",
                "Abandon the current run first.",
                parent=self.root,
            )
            return
        if not self._confirm_project_replacement():
            return
        candidate = Path(path)
        if not candidate.is_file():
            self._forget_recent_project(candidate)
            messagebox.showerror(
                "Open failed",
                f"Recent project is no longer available:\n{candidate}",
                parent=self.root,
            )
            return
        try:
            self.load_project_path(candidate)
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc), parent=self.root)

    def _open_bundled_demo_from_start(self) -> None:
        if self._running:
            messagebox.showwarning(
                "Analysis running",
                "Abandon the current run first.",
                parent=self.root,
            )
            return
        if not self._confirm_project_replacement():
            return
        try:
            self.load_project_path(bundled_demo_project_path())
        except Exception as exc:
            messagebox.showerror("Open example failed", str(exc), parent=self.root)

    def _import_ifc_from_start(self) -> None:
        if self.import_ifc_spatial_layout():
            self._activate_spatial_workspace("split")

    def _activate_spatial_workspace(self, mode: str | None = None) -> None:
        if mode is not None and hasattr(self, "notebook"):
            self.activate_workspace_profile("design")
        if hasattr(self, "notebook") and hasattr(self, "spatial_workspace"):
            self.notebook.select(self.spatial_workspace)
        if mode is not None and hasattr(self, "spatial_workspace"):
            self.spatial_workspace.set_workspace_mode(mode)
            label = {"2d": "2D", "3d": "3D", "split": "Split"}[mode]
            self.workspace_status_var.set(f"Workspace: {label}")

    def _activate_analysis_input_workspace(self) -> None:
        """Open the current analysis input editor without changing engineering data."""
        if hasattr(self, "notebook") and hasattr(self, "input_tab"):
            self.notebook.select(self.input_tab)
            self.workspace_status_var.set("Workspace: Analysis Inputs")

    def _refresh_simulation_workspace(self) -> None:
        """Project the active analysis/run into the simulation surface without mutation."""
        workspace = getattr(self, "simulation_workspace", None)
        if workspace is None:
            return
        active_id = getattr(self, "_editor_analysis_id", None) or self.project.active_analysis_id
        workspace.set_analysis_options(
            tuple((item.id, item.name, item.kind) for item in self.project.analyses),
            active_id=active_id,
        )
        analysis = self._editor_analysis()
        if analysis is None:
            workspace.set_context(
                analysis_name=None,
                analysis_kind=None,
                running=False,
            )
            return
        history_available = True
        retained_run_count: int | None = None
        latest_retained_utc: str | None = None
        try:
            retained = [
                record
                for record in run_history_records(self.project.metadata)
                if record.get("analysis_id") == analysis.id
            ]
        except RunHistoryIntegrityError:
            history_available = False
        else:
            retained_run_count = len(retained)
            if retained:
                latest_retained_utc = (
                    str(retained[-1].get("completed_at_utc") or "") or None
                )
        workspace.set_context(
            analysis_name=analysis.name,
            analysis_kind=analysis.kind,
            analysis_input=analysis.input,
            last_run=self._runs_by_analysis.get(analysis.id),
            running=bool(self._running),
            retained_run_count=retained_run_count,
            latest_retained_utc=latest_retained_utc,
            history_available=history_available,
        )

    def _select_analysis_from_simulation(self, analysis_id: str) -> None:
        """Route Simulation scenario selection through the canonical navigator guard."""
        target = str(analysis_id or "").strip()
        if not target or not self.analysis_tree.exists(target):
            self._refresh_simulation_workspace()
            return
        self.analysis_tree.selection_set(target)
        self.analysis_tree.focus(target)
        self.analysis_tree.see(target)
        self._on_analysis_selected()
        self._refresh_simulation_workspace()
        if getattr(self, "_editor_analysis_id", None) == target:
            self.notebook.select(self.simulation_workspace)
            self.workspace_profile_var.set("simulation")
            self.workspace_status_var.set("Workspace: Simulation")

    def _activate_analysis_results_workspace(self) -> None:
        if hasattr(self, "output_notebook") and hasattr(self, "result_text"):
            self.output_panel_visible_var.set(True)
            self._sync_output_panel_visibility()
            self.output_notebook.select(self.result_text.master)
            self.workspace_status_var.set("Workspace: Simulation Results")

    def _guided_save_and_verify(self) -> None:
        """Save the exact project state required by canonical verification, then verify."""
        if self._running:
            messagebox.showwarning(
                "Analysis running",
                "Abandon the current run before verification.",
                parent=self.root,
            )
            return
        if self.project_path is None:
            self.save_project_as()
        elif self._has_unsaved_changes():
            self.save_project()
        if self.project_path is None or self._has_unsaved_changes():
            self.status_var.set("Save required before verification")
            return
        self.activate_workspace_profile("verification")
        self.run_project_requirements_verification()

    def _add_text_tab(
        self,
        title: str,
        *,
        notebook: ttk.Notebook | None = None,
    ) -> tk.Text:
        target = self.notebook if notebook is None else notebook
        frame = ttk.Frame(target)
        target.add(frame, text=title)
        text = tk.Text(frame, wrap="none", state="disabled")
        yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return text

    def _apply_wrap_setting(self) -> None:
        wrap = "word" if self.wrap_outputs_var.get() else "none"
        for widget in (
            self.result_text,
            self.report_text,
            self.diagnostics_text,
            self.verification_text,
            self.console_text,
            self.evidence_text,
        ):
            widget.configure(wrap=wrap)

    def _set_text(self, widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _clear_rendered_run(self) -> None:
        self.last_run = None
        self.last_run_analysis_id = None
        self._set_text(self.result_text, "")
        self._set_text(self.report_text, "")
        self._set_text(self.diagnostics_text, "")
        self._draw_plot()

    def _clear_run_cache(self) -> None:
        self._runs_by_analysis.clear()
        self._clear_rendered_run()

    def _project_history_manager(self) -> ProjectEditHistory:
        history = getattr(self, "_project_history", None)
        if history is None:
            history = ProjectEditHistory(limit=PROJECT_HISTORY_LIMIT)
            self._project_history = history
        return history

    def _spatial_history_selection(self) -> tuple[str, str] | None:
        workspace = getattr(self, "spatial_workspace", None)
        getter = getattr(workspace, "history_selection", None)
        return getter() if callable(getter) else None

    def _project_history_document(self) -> dict:
        """Capture the complete undoable design state.

        Persistent audit evidence is not an edit and must never be erased by Undo.
        Spatial camera/view state is also excluded so design undo preserves the
        operator's current viewport.
        """

        data = copy.deepcopy(self.project.to_dict())
        metadata = data.get("project", {}).get("metadata")
        if isinstance(metadata, dict):
            metadata.pop(RUN_HISTORY_METADATA_KEY, None)
            layout = metadata.get(SPATIAL_METADATA_KEY)
            if isinstance(layout, dict):
                layout.pop("view", None)
        return data

    def _capture_project_history_state(self) -> ProjectHistoryState:
        return self._project_history_manager().capture(
            self._project_history_document(),
            getattr(self, "_editor_analysis_id", None),
            self._spatial_history_selection(),
        )

    def _update_project_history_controls(self) -> None:
        history = self._project_history_manager()
        menu = getattr(self, "edit_menu", None)
        if menu is not None:
            undo_description = history.undo_description
            redo_description = history.redo_description
            menu.entryconfigure(
                0,
                label=(
                    f"Undo {undo_description}"
                    if undo_description is not None
                    else "Undo Project Edit"
                ),
                state="normal" if history.can_undo else "disabled",
            )
            menu.entryconfigure(
                1,
                label=(
                    f"Redo {redo_description}"
                    if redo_description is not None
                    else "Redo Project Edit"
                ),
                state="normal" if history.can_redo else "disabled",
            )
        toolbar_undo = getattr(self, "toolbar_undo_button", None)
        if toolbar_undo is not None:
            toolbar_undo.configure(
                state="normal" if history.can_undo else "disabled"
            )
        toolbar_redo = getattr(self, "toolbar_redo_button", None)
        if toolbar_redo is not None:
            toolbar_redo.configure(
                state="normal" if history.can_redo else "disabled"
            )

        workspace = getattr(self, "spatial_workspace", None)
        setter = getattr(workspace, "set_history_availability", None)
        if callable(setter):
            setter(history.can_undo, history.can_redo)

    def _clear_project_history(self) -> None:
        self._project_history_manager().clear()
        self._update_project_history_controls()

    def _record_project_edit(
        self,
        before: ProjectHistoryState,
        description: str,
    ) -> bool:
        recorded = self._project_history_manager().record(
            before=before,
            after_document=self._project_history_document(),
            after_editor_analysis_id=getattr(self, "_editor_analysis_id", None),
            after_spatial_selection=self._spatial_history_selection(),
            description=description,
        )
        self._update_project_history_controls()
        return recorded

    def _record_spatial_project_edit(
        self,
        before_layout: dict,
        before_selection: tuple[str, str] | None,
        after_layout: dict,
        after_selection: tuple[str, str] | None,
        description: str,
    ) -> bool:
        """Record a spatial mutation in the same transaction stream as all edits."""

        after_document = self._project_history_document()
        before_document = copy.deepcopy(after_document)
        project_block = before_document.get("project")
        if not isinstance(project_block, dict):
            raise ValueError("project history snapshot is missing project metadata")
        metadata = project_block.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("project history snapshot metadata must be an object")
        before_design = copy.deepcopy(before_layout)
        if isinstance(before_design, dict):
            before_design.pop("view", None)
        metadata[SPATIAL_METADATA_KEY] = before_design

        before = self._project_history_manager().capture(
            before_document,
            getattr(self, "_editor_analysis_id", None),
            before_selection,
        )
        recorded = self._project_history_manager().record(
            before=before,
            after_document=after_document,
            after_editor_analysis_id=getattr(self, "_editor_analysis_id", None),
            after_spatial_selection=after_selection,
            description=description,
        )
        self._update_project_history_controls()
        return recorded

    def _project_from_history_state(
        self, state: ProjectHistoryState
    ) -> ProjectDocument:
        """Rebuild validated design state while preserving audit evidence and viewport."""

        current_metadata = self.project.metadata
        audit_history = (
            copy.deepcopy(current_metadata[RUN_HISTORY_METADATA_KEY])
            if RUN_HISTORY_METADATA_KEY in current_metadata
            else None
        )
        current_layout = current_metadata.get(SPATIAL_METADATA_KEY)
        current_view = (
            copy.deepcopy(current_layout.get("view", {}))
            if isinstance(current_layout, dict)
            else {}
        )

        restored = project_from_dict(copy.deepcopy(state.document))
        if audit_history is not None:
            restored.metadata[RUN_HISTORY_METADATA_KEY] = audit_history

        restored_layout = restored.metadata.get(SPATIAL_METADATA_KEY)
        if isinstance(restored_layout, dict) and current_view:
            restored_layout["view"] = current_view
        return restored

    def _perform_project_edit(self, description: str, mutation):
        """Apply one validated application-wide mutation transaction."""

        before = self._capture_project_history_state()
        try:
            result = mutation()
            project_from_dict(copy.deepcopy(self.project.to_dict()))
        except Exception:
            self.project = self._project_from_history_state(before)
            self._editor_analysis_id = before.editor_analysis_id
            raise
        self._record_project_edit(before, description)
        return result

    def _restore_project_history_state(self, state: ProjectHistoryState) -> None:
        restored = self._project_from_history_state(state)
        self.project = restored
        self.name_var.set(restored.name)
        self.description_var.set(restored.description)
        self._clear_run_cache()
        self._refresh_analysis_list(select_id=state.editor_analysis_id)

        workspace = getattr(self, "spatial_workspace", None)
        if workspace is not None:
            workspace.refresh()
            restore_selection = getattr(workspace, "restore_history_selection", None)
            if callable(restore_selection):
                restore_selection(state.spatial_selection)

        self._update_project_history_controls()
        self._update_title()
        self._schedule_project_diagnostics_refresh()

    def _prepare_project_history_action(self, action: str) -> bool:
        try:
            if self._editor_analysis() is not None:
                self._commit_editor()
            else:
                self._sync_metadata()
        except Exception as exc:
            messagebox.showerror(
                f"Cannot {action}",
                (
                    "The current project fields must be valid before project history "
                    f"can be changed.\n\n{exc}"
                ),
                parent=self.root,
            )
            return False
        return True

    def undo_project_edit(self) -> bool:
        if self._running:
            messagebox.showwarning(
                "Analysis running",
                "Abandon the current run before undoing a project edit.",
                parent=self.root,
            )
            return False
        if not self._prepare_project_history_action("undo"):
            return False
        item = self._project_history_manager().undo()
        if item is None:
            self._update_project_history_controls()
            return False
        state, description = item
        self._restore_project_history_state(state)
        self.status_var.set(f"Undo: {description}")
        return True

    def redo_project_edit(self) -> bool:
        if self._running:
            messagebox.showwarning(
                "Analysis running",
                "Abandon the current run before redoing a project edit.",
                parent=self.root,
            )
            return False
        if not self._prepare_project_history_action("redo"):
            return False
        item = self._project_history_manager().redo()
        if item is None:
            self._update_project_history_controls()
            return False
        state, description = item
        self._restore_project_history_state(state)
        self.status_var.set(f"Redo: {description}")
        return True

    def _invalidate_last_run_for(self, analysis_id: str | None) -> None:
        if analysis_id is None:
            return
        self._runs_by_analysis.pop(analysis_id, None)
        if self.last_run_analysis_id == analysis_id:
            self._clear_rendered_run()
        if hasattr(self, "spatial_workspace"):
            self.spatial_workspace.redraw()

    def _restore_run_for(self, analysis_id: str) -> bool:
        run = self._runs_by_analysis.get(analysis_id)
        if run is None:
            self._clear_rendered_run()
            return False
        try:
            analysis = self.project.analysis_by_id(analysis_id)
        except KeyError:
            self._invalidate_last_run_for(analysis_id)
            return False
        if not analysis_run_is_current(
            run, analysis.kind, analysis.input, base_dir=self._base_dir()
        ):
            self._invalidate_last_run_for(analysis_id)
            self.status_var.set(
                f"{analysis.name} — cached result is out of date; run the analysis again."
            )
            return False
        self.last_run = run
        self.last_run_analysis_id = analysis_id
        self._render_run(run, select_results=False)
        return True

    def _current_fresh_run(self) -> AnalysisRun | None:
        run = self.last_run
        analysis_id = self.last_run_analysis_id
        if run is None or analysis_id is None:
            return None
        try:
            analysis = self.project.analysis_by_id(analysis_id)
        except KeyError:
            self._invalidate_last_run_for(analysis_id)
            return None
        if not analysis_run_is_current(
            run, analysis.kind, analysis.input, base_dir=self._base_dir()
        ):
            self._invalidate_last_run_for(analysis_id)
            self.status_var.set(
                f"{analysis.name} — result is out of date; run the analysis again."
            )
            return None
        return run

    def _record_completed_run(
        self,
        analysis: AnalysisDocument,
        run: AnalysisRun,
        evidence: dict | None = None,
    ) -> dict:
        prepared = (
            evidence
            if evidence is not None
            else build_run_history_evidence(analysis.input, run)
        )
        record = append_run_history_evidence(
            self.project.metadata,
            analysis_id=analysis.id,
            analysis_name=analysis.name,
            analysis_kind=analysis.kind,
            evidence=prepared,
        )
        self._update_title()
        return record

    def show_run_history(self) -> bool:
        try:
            summary = validate_run_history(self.project.metadata)
        except RunHistoryIntegrityError as exc:
            self.status_var.set("Run history integrity check failed")
            messagebox.showerror(
                "Run history integrity failure",
                (
                    "CleanroomX found invalid or modified run-history evidence and "
                    "did not rewrite it.\n\n"
                    f"{exc}"
                ),
                parent=self.root,
            )
            return False
        if summary["record_count"] == 0:
            messagebox.showinfo(
                "Analysis Run History",
                "No completed analysis runs have been recorded in this project yet.",
                parent=self.root,
            )
            return False
        RunHistoryDialog(self.root, self.project.metadata)
        return True

    def show_verification_history(self) -> bool:
        try:
            summary = validate_project_verification_run_history(
                self.project.metadata
            )
        except VerificationRunHistoryIntegrityError as exc:
            self.status_var.set("Verification history integrity check failed")
            messagebox.showerror(
                "Verification history integrity failure",
                (
                    "CleanroomX found invalid or modified project-verification "
                    "evidence and did not rewrite it.\n\n"
                    f"{exc}"
                ),
                parent=self.root,
            )
            return False
        if summary["record_count"] == 0:
            messagebox.showinfo(
                "Project Verification History",
                "No persisted project requirements verification records exist yet.",
                parent=self.root,
            )
            return False
        VerificationHistoryDialog(
            self.root,
            self.project,
            base_dir=self._base_dir(),
        )
        return True

    def show_requirements_traceability(
        self,
        requirement_id: str | None = None,
        mapping_id: str | None = None,
    ) -> bool:
        try:
            snapshot = project_requirement_traceability_snapshot(self.project)
        except (
            ProjectRequirementsFormatError,
            ProjectRequirementEvidenceMappingsFormatError,
        ) as exc:
            self.status_var.set("Project requirements traceability is invalid")
            messagebox.showerror(
                "Requirements traceability invalid",
                str(exc),
                parent=self.root,
            )
            return False

        if (
            snapshot["requirement_count"] == 0
            and snapshot["mapping_count"] == 0
        ):
            messagebox.showinfo(
                "Project Requirements Traceability",
                "No persisted project requirements or evidence mappings exist yet.",
                parent=self.root,
            )
            return False

        dialog = RequirementsTraceabilityDialog(self.root, snapshot)
        if requirement_id:
            focused = dialog.focus_requirement(requirement_id)
            if focused:
                self.status_var.set(
                    f"Requirements traceability focused on {requirement_id}"
                )
            else:
                self.status_var.set(
                    f"Requirements traceability opened; {requirement_id} is not present"
                )
        elif mapping_id:
            focused = dialog.focus_mapping(mapping_id)
            if focused:
                self.status_var.set(
                    f"Requirements traceability focused on mapping {mapping_id}"
                )
            else:
                self.status_var.set(
                    f"Requirements traceability opened; mapping {mapping_id} is not present"
                )
        return True

    def _project_verification_target(
        self,
    ) -> tuple[Path, AnalysisDocument] | None:
        if self._running:
            messagebox.showwarning(
                "Analysis running",
                "Abandon the current run first.",
                parent=self.root,
            )
            return None
        if self.project_path is None:
            self.status_var.set(
                "Save the project before running project requirements verification."
            )
            messagebox.showinfo(
                "Save project first",
                (
                    "Project requirements verification is bound to exact saved "
                    "project bytes. Save the project first."
                ),
                parent=self.root,
            )
            return None
        if self._has_unsaved_changes():
            self.status_var.set(
                "Save project changes before running requirements verification."
            )
            messagebox.showinfo(
                "Save project changes first",
                (
                    "The project has unsaved changes. Save them before verification "
                    "so the run can be bound to the exact source-project SHA-256."
                ),
                parent=self.root,
            )
            return None

        analysis = self._current_analysis() or self._editor_analysis()
        if analysis is None:
            messagebox.showinfo(
                "Select analysis",
                "Select the analysis whose mapped project requirements should be verified.",
                parent=self.root,
            )
            return None

        expected_revision = getattr(self, "_project_file_revision", None)
        if expected_revision is None:
            self.status_var.set("Saved project revision identity is unavailable.")
            messagebox.showerror(
                "Verification blocked",
                (
                    "CleanroomX cannot prove which saved project revision is open. "
                    "Save or reopen the project, then retry verification."
                ),
                parent=self.root,
            )
            return None
        try:
            current_revision = capture_project_file_revision(self.project_path)
        except OSError as exc:
            self.status_var.set("Verification blocked")
            messagebox.showerror(
                "Verification blocked",
                str(exc),
                parent=self.root,
            )
            return None
        if not project_file_revision_matches(
            expected_revision,
            current_revision,
        ):
            self.status_var.set("Verification blocked: project changed on disk")
            messagebox.showerror(
                "Verification blocked",
                (
                    "The saved project changed on disk after it was opened or saved. "
                    "Reload or save the intended revision before verification."
                ),
                parent=self.root,
            )
            return None
        return self.project_path, analysis

    @staticmethod
    def _project_verification_summary_text(workflow) -> str:
        verification = workflow.verification
        summary = verification.get("summary", {})
        return (
            f"Analysis: {workflow.analysis_name}\n"
            f"Status: {verification.get('status')}\n"
            f"Complete: {verification.get('complete')}\n"
            f"Verified: {verification.get('verified')}\n"
            f"Pass findings: {summary.get('pass_count', 0)}\n"
            f"Fail findings: {summary.get('fail_count', 0)}\n"
            f"Not checked: {summary.get('not_checked_count', 0)}\n\n"
            f"Source project SHA-256: {workflow.source_revision}\n"
            f"Verification SHA-256: {verification.get('verification_sha256')}\n"
            f"Workflow SHA-256: {workflow.workflow_sha256}"
        )

    def run_project_requirements_verification(self) -> bool:
        target = self._project_verification_target()
        if target is None:
            return False
        project_path, analysis = target
        try:
            workflow = run_project_requirements_workflow(
                project_path,
                analysis.id,
            )
        except Exception as exc:
            self.status_var.set("Project requirements verification failed")
            messagebox.showerror(
                "Project requirements verification failed",
                str(exc),
                parent=self.root,
            )
            return False

        message = self._project_verification_summary_text(workflow)
        if workflow.verification.get("verified") is True:
            self.status_var.set(
                f"Project requirements verified — {analysis.name}"
            )
            messagebox.showinfo(
                "Project requirements verified",
                message,
                parent=self.root,
            )
        else:
            self.status_var.set(
                f"Project requirements require attention — {analysis.name}"
            )
            messagebox.showwarning(
                "Project requirements require attention",
                message,
                parent=self.root,
            )
        return True

    def persist_project_requirements_verification(self) -> bool:
        target = self._project_verification_target()
        if target is None:
            return False
        project_path, analysis = target
        try:
            workflow = run_project_requirements_workflow(
                project_path,
                analysis.id,
            )
            persisted = persist_project_requirements_workflow_run(
                project_path,
                workflow,
            )
        except ProjectSaveDurabilityError as exc:
            try:
                self.load_project_path(project_path)
            except Exception:
                pass
            self.status_var.set(
                "Verification bytes committed; save durability not confirmed"
            )
            messagebox.showwarning(
                "Verification save durability not confirmed",
                (
                    "CleanroomX wrote and verified the project bytes containing the "
                    "verification record, but filesystem directory durability could "
                    "not be confirmed.\n\n"
                    f"Committed project SHA-256: {exc.committed_revision.sha256}"
                ),
                parent=self.root,
            )
            return False
        except Exception as exc:
            self.status_var.set("Project verification persistence failed")
            messagebox.showerror(
                "Project verification persistence failed",
                str(exc),
                parent=self.root,
            )
            return False

        try:
            self.load_project_path(project_path)
        except Exception as exc:
            self.status_var.set("Verification persisted; project reload failed")
            messagebox.showerror(
                "Verification persisted; reload failed",
                (
                    f"The verification record was committed, but the project could "
                    f"not be reloaded into the desktop session.\n\n{exc}\n\n"
                    f"Record SHA-256: {persisted.record['record_sha256']}"
                ),
                parent=self.root,
            )
            return False

        record = persisted.record
        message = (
            self._project_verification_summary_text(workflow)
            + "\n\n"
            + f"Persisted sequence: {record['sequence']}\n"
            + f"Record SHA-256: {record['record_sha256']}\n"
            + "The record remains historical evidence for the source revision above."
        )
        if workflow.verification.get("verified") is True:
            self.status_var.set(
                f"Project verification persisted — {analysis.name}"
            )
            messagebox.showinfo(
                "Project verification persisted",
                message,
                parent=self.root,
            )
        else:
            self.status_var.set(
                f"Adverse/incomplete verification persisted — {analysis.name}"
            )
            messagebox.showwarning(
                "Verification evidence persisted",
                message,
                parent=self.root,
            )
        return True

    def _on_input_modified(self, event=None) -> None:
        if not self.input_text.edit_modified():
            return
        self.input_text.edit_modified(False)
        self._invalidate_last_run_for(self._editor_analysis_id)
        self._update_title()

    def _current_analysis(self) -> AnalysisDocument | None:
        selection = self.analysis_tree.selection()
        if not selection:
            return None
        try:
            return self.project.analysis_by_id(selection[0])
        except KeyError:
            return None

    def _editor_analysis(self) -> AnalysisDocument | None:
        if self._editor_analysis_id is None:
            return None
        try:
            return self.project.analysis_by_id(self._editor_analysis_id)
        except KeyError:
            return None

    def _spatial_result_payload(self) -> dict | None:
        """Return only result evidence that still matches the active analysis input."""
        analysis = self._editor_analysis()
        if analysis is None:
            return None
        run = self._runs_by_analysis.get(analysis.id)
        if run is None:
            return None
        if not analysis_run_is_current(
            run,
            analysis.kind,
            analysis.input,
            base_dir=self._base_dir(),
        ):
            return None
        return run.result if isinstance(run.result, dict) else None

    def _commit_editor(self, analysis: AnalysisDocument | None = None) -> AnalysisDocument:
        analysis = analysis or self._editor_analysis() or self._current_analysis()
        if analysis is None:
            raise ValueError("select or add an analysis first")
        try:
            payload = _strict_json_loads(self.input_text.get("1.0", "end-1c"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"input JSON is invalid at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError("analysis input must be a JSON object")

        name = self.name_var.get().strip()
        if not name:
            raise ValueError("project name cannot be empty")
        description = self.description_var.get()
        input_changed = analysis.input != payload
        metadata_changed = (
            self.project.name != name or self.project.description != description
        )
        if input_changed and metadata_changed:
            edit_description = f"Edit {analysis.name} input and project fields"
        elif input_changed:
            edit_description = f"Edit {analysis.name} input"
        else:
            edit_description = "Edit project fields"

        def mutate() -> None:
            analysis.input = payload
            self.project.name = name
            self.project.description = description

        self._perform_project_edit(edit_description, mutate)
        cached_run = getattr(self, "_runs_by_analysis", {}).get(analysis.id)
        if input_changed and cached_run is not None and not analysis_run_is_current(
            cached_run, analysis.kind, payload, base_dir=self._base_dir()
        ):
            self._invalidate_last_run_for(analysis.id)
        return analysis

    def _sync_metadata(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            raise ValueError("project name cannot be empty")
        description = self.description_var.get()

        def mutate() -> None:
            self.project.name = name
            self.project.description = description

        self._perform_project_edit("Edit project fields", mutate)

    def _base_dir(self) -> Path | None:
        project_path = getattr(self, "project_path", None)
        if project_path is not None:
            return project_path.parent
        recovery_source = getattr(self, "_recovery_source_path", None)
        if recovery_source is not None:
            return recovery_source.parent
        return None

    def _project_state_signature(self) -> str:
        data = copy.deepcopy(self.project.to_dict())
        name = self.name_var.get().strip()
        if not name:
            raise ValueError("project name cannot be empty")
        data["project"]["name"] = name
        data["project"]["description"] = self.description_var.get()

        if self._editor_analysis_id is not None:
            text = self.input_text.get("1.0", "end-1c")
            try:
                payload = _strict_json_loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"input JSON is invalid at line {exc.lineno}, column {exc.colno}: {exc.msg}"
                ) from exc
            if not isinstance(payload, dict):
                raise ValueError("analysis input must be a JSON object")
            for analysis in data["analyses"]:
                if analysis["id"] == self._editor_analysis_id:
                    analysis["input"] = payload
                    break

        return json.dumps(
            data, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )

    def _has_unsaved_changes(self) -> bool:
        baseline = getattr(self, "_baseline_state", None)
        if baseline is None:
            return False
        try:
            return self._project_state_signature() != baseline
        except Exception:
            return True

    def _capture_saved_state(self) -> None:
        self._baseline_state = self._project_state_signature()
        self._update_title()

    def _build_recovery_snapshot(self) -> dict:
        project_data = copy.deepcopy(self.project.to_dict())
        name_text = self.name_var.get()
        description_text = self.description_var.get()
        editor_text = ""
        editor_json_valid = True

        if name_text.strip():
            project_data["project"]["name"] = name_text.strip()
        project_data["project"]["description"] = description_text

        if self._editor_analysis_id is not None:
            editor_text = self.input_text.get("1.0", "end-1c")
            try:
                payload = _strict_json_loads(editor_text)
                if not isinstance(payload, dict):
                    editor_json_valid = False
                else:
                    for analysis in project_data["analyses"]:
                        if analysis["id"] == self._editor_analysis_id:
                            analysis["input"] = payload
                            break
            except (json.JSONDecodeError, ValueError):
                editor_json_valid = False

        return {
            "project": project_data,
            "ui_state": {
                "name_text": name_text,
                "description_text": description_text,
                "editor_analysis_id": self._editor_analysis_id,
                "editor_text": editor_text,
                "editor_json_valid": editor_json_valid,
            },
        }

    def _begin_autosave_project(self, path: str | Path | None) -> None:
        self._cancel_recovery_checkpoint()
        manager = getattr(self, "_autosave_manager", None)
        if manager is not None:
            manager.begin_project(path)

    def _notify_explicit_save(self, path: str | Path) -> None:
        self._cancel_recovery_checkpoint()
        manager = getattr(self, "_autosave_manager", None)
        if manager is not None:
            manager.notify_explicit_save(path)
        autosave_var = getattr(self, "autosave_status_var", None)
        if autosave_var is not None:
            autosave_var.set("Autosave: clean")

    def _discard_current_autosave(self) -> None:
        self._cancel_recovery_checkpoint()
        manager = getattr(self, "_autosave_manager", None)
        if manager is not None:
            manager.discard_current_recoveries()

    def _discard_restored_recovery(self) -> None:
        artifact = getattr(self, "_restored_recovery_artifact", None)
        if artifact is None:
            return
        if not artifact.exists():
            self._restored_recovery_artifact = None
            return
        try:
            discard_recovery_artifact(artifact, recovery_dir=artifact.parent)
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            self.status_var.set(f"Recovery cleanup failed: {exc}")
            return
        self._restored_recovery_artifact = None

    def _autosave_source_path(self) -> Path | None:
        if self.project_path is not None:
            return self.project_path
        return getattr(self, "_recovery_source_path", None)

    def _cancel_recovery_checkpoint(self) -> None:
        token = getattr(self, "_recovery_checkpoint_after_id", None)
        if token is None:
            return
        cancel = getattr(self.root, "after_cancel", None)
        if callable(cancel):
            try:
                cancel(token)
            except tk.TclError:
                pass
        self._recovery_checkpoint_after_id = None

    def _schedule_recovery_checkpoint(self) -> None:
        if not getattr(self, "_autosave_interval_ms", 0):
            return
        schedule = getattr(self.root, "after", None)
        if not callable(schedule):
            return
        self._cancel_recovery_checkpoint()
        self._recovery_checkpoint_after_id = schedule(
            RECOVERY_CHECKPOINT_DEBOUNCE_MS,
            self._run_debounced_recovery_checkpoint,
        )

    def _checkpoint_recovery(self) -> None:
        try:
            if self._has_unsaved_changes():
                snapshot = self._build_recovery_snapshot()
                if self._autosave_manager.request_autosave(
                    snapshot,
                    source_path=self._autosave_source_path(),
                ):
                    self.autosave_status_var.set("Autosave: saving…")
            elif self._autosave_manager.status().state == "saved":
                self._discard_current_autosave()
                self.autosave_status_var.set("Autosave: clean")
        except (OSError, TypeError, ValueError) as exc:
            self.autosave_status_var.set("Autosave: failed")
            self.status_var.set(f"Autosave failed: {exc}")

    def _run_debounced_recovery_checkpoint(self) -> None:
        self._recovery_checkpoint_after_id = None
        if not getattr(self, "_autosave_interval_ms", 0):
            return
        self._checkpoint_recovery()

    def _autosave_tick(self) -> None:
        if not self._autosave_interval_ms:
            return
        try:
            self._checkpoint_recovery()
        finally:
            self.root.after(self._autosave_interval_ms, self._autosave_tick)

    def _poll_autosave_status(self) -> None:
        status = self._autosave_manager.status()
        if status.sequence != self._autosave_status_sequence:
            self._autosave_status_sequence = status.sequence
            if status.state == "saving":
                self.autosave_status_var.set("Autosave: saving…")
            elif status.state == "saved":
                self.autosave_status_var.set("Autosave: recovery saved")
            elif status.state == "failed":
                self.autosave_status_var.set("Autosave: failed")
                self.status_var.set(status.message)
            elif status.state == "idle":
                self.autosave_status_var.set("Autosave: ready")
        self.root.after(500, self._poll_autosave_status)

    def _confirm_project_replacement(self) -> bool:
        if not self._has_unsaved_changes():
            return True
        choice = messagebox.askyesnocancel(
            "Unsaved changes",
            "Save changes to the current project before continuing?",
            parent=self.root,
        )
        if choice is None:
            return False
        if choice:
            self.save_project()
            return not self._has_unsaved_changes()
        self._discard_current_autosave()
        self._discard_restored_recovery()
        return True

    def _refresh_analysis_list(self, select_id: str | None = None) -> None:
        self._restore_navigator_tree()
        for item in self.analysis_tree.get_children():
            self.analysis_tree.delete(item)

        sections = (
            ("nav-building", "Building"),
            ("nav-hvac", "HVAC Systems"),
            ("nav-devices", "Devices"),
            ("nav-pressure", "Pressure Network"),
            ("nav-analyses", "Analyses"),
            ("nav-simulation", "Simulation / Results"),
            ("nav-requirements", "Requirements"),
            ("nav-proofgraph", "ProofGraph"),
            ("nav-evidence", "Evidence"),
            ("nav-reports", "Reports"),
        )
        for iid, label in sections:
            self.analysis_tree.insert(
                "",
                "end",
                iid=iid,
                text=label,
                tags=("section",),
                open=iid in {"nav-building", "nav-analyses"},
            )

        for analysis in self.project.analyses:
            self.analysis_tree.insert(
                "nav-analyses",
                "end",
                iid=analysis.id,
                text=analysis.name,
                values=(analysis.kind,),
            )
        self._refresh_spatial_navigator()

        target = select_id or self.project.active_analysis_id
        if target and self.analysis_tree.exists(target):
            self.analysis_tree.selection_set(target)
            self.analysis_tree.focus(target)
            self.analysis_tree.see(target)
            self._load_analysis_into_editor(self.project.analysis_by_id(target))
        elif self.project.analyses:
            first = self.project.analyses[0].id
            self.project.active_analysis_id = first
            self.analysis_tree.selection_set(first)
            self.analysis_tree.focus(first)
            self.analysis_tree.see(first)
            self._load_analysis_into_editor(self.project.analyses[0])
        else:
            self._editor_analysis_id = None
            self.input_text.delete("1.0", "end")
            self.input_text.edit_modified(False)
            self.refresh_structure(silent=True)
        if hasattr(self, "spatial_workspace"):
            self.spatial_workspace.refresh()
        self._refresh_simulation_workspace()

    def _restore_navigator_tree(self) -> None:
        tree = getattr(self, "analysis_tree", None)
        if tree is None:
            return
        for iid, parent, index in list(
            getattr(self, "_navigator_tree_snapshot", [])
        ):
            if tree.exists(iid) and (not parent or tree.exists(parent)):
                tree.move(iid, parent, index)

    def _capture_navigator_tree(self) -> None:
        tree = getattr(self, "analysis_tree", None)
        if tree is None:
            self._navigator_tree_snapshot = []
            return
        snapshot: list[tuple[str, str, int]] = []

        def visit(parent: str) -> None:
            for index, iid in enumerate(tree.get_children(parent)):
                snapshot.append((iid, parent, index))
                visit(iid)

        visit("")
        self._navigator_tree_snapshot = snapshot

    def _navigator_recent_category(self, item_id: str) -> str:
        if item_id.startswith("room:"):
            return "Room"
        if item_id.startswith("device:"):
            return "Device"
        if item_id.startswith("nav-"):
            return "Workspace"
        return "Analysis"

    def _navigator_item_is_actionable(self, item_id: str) -> bool:
        if item_id.startswith(("room:", "device:")):
            return True
        if item_id in {
            "nav-simulation",
            "nav-proofgraph",
            "nav-evidence",
            "nav-reports",
        }:
            return True
        return bool(item_id and not item_id.startswith("nav-"))

    def _reset_navigator_recent_for_project(self) -> None:
        token = id(self.project)
        if token == getattr(self, "_navigator_recent_project_token", None):
            return
        self._navigator_recent_project_token = token
        self._navigator_recent_ids = []
        self._navigator_recent_display_to_id = {}
        recent_var = getattr(self, "navigator_recent_var", None)
        if recent_var is not None:
            recent_var.set("")

    def _refresh_navigator_recent_picker(self) -> None:
        self._reset_navigator_recent_for_project()
        tree = getattr(self, "analysis_tree", None)
        picker = getattr(self, "navigator_recent_picker", None)
        if tree is None or picker is None:
            return
        recent_ids = [
            item_id
            for item_id in getattr(self, "_navigator_recent_ids", [])
            if tree.exists(item_id) and self._navigator_item_is_actionable(item_id)
        ][:8]
        self._navigator_recent_ids = recent_ids

        display_to_id: dict[str, str] = {}
        displays: list[str] = []
        for item_id in recent_ids:
            label = str(tree.item(item_id, "text") or item_id)
            display = f"{label} · {self._navigator_recent_category(item_id)}"
            if display in display_to_id:
                display = f"{display} · {item_id}"
            display_to_id[display] = item_id
            displays.append(display)
        self._navigator_recent_display_to_id = display_to_id
        picker.configure(values=tuple(displays))
        if self.navigator_recent_var.get() not in display_to_id:
            self.navigator_recent_var.set("")

    def _remember_navigator_item(self, item_id: str) -> None:
        tree = getattr(self, "analysis_tree", None)
        if (
            tree is None
            or not item_id
            or not tree.exists(item_id)
            or not self._navigator_item_is_actionable(item_id)
        ):
            return
        self._reset_navigator_recent_for_project()
        recent_ids = list(getattr(self, "_navigator_recent_ids", []))
        if item_id in recent_ids:
            recent_ids.remove(item_id)
        recent_ids.insert(0, item_id)
        self._navigator_recent_ids = recent_ids[:8]
        self._refresh_navigator_recent_picker()

    def clear_navigator_recent(self) -> None:
        self._navigator_recent_ids = []
        self._navigator_recent_display_to_id = {}
        self.navigator_recent_var.set("")
        picker = getattr(self, "navigator_recent_picker", None)
        if picker is not None:
            picker.configure(values=())
        self.status_var.set("Recent navigator selections cleared")

    def _open_navigator_item(self, item_id: str) -> bool:
        tree = getattr(self, "analysis_tree", None)
        if tree is None or not item_id or not tree.exists(item_id):
            return False
        if self.navigator_filter_var.get():
            self.navigator_filter_var.set("")
        tree.selection_set(item_id)
        tree.focus(item_id)
        tree.see(item_id)
        self._on_navigator_selected()
        return True

    def _on_recent_navigator_selected(self, _event=None) -> None:
        item_id = self._navigator_recent_display_to_id.get(
            self.navigator_recent_var.get()
        )
        if not self._open_navigator_item(item_id or ""):
            self._refresh_navigator_recent_picker()

    def _navigator_favorites_project_key(self) -> str | None:
        path = getattr(self, "project_path", None)
        if path is None:
            return None
        try:
            return str(Path(path))
        except (TypeError, ValueError, OSError):
            return None

    def _sync_navigator_favorites_for_project(self) -> None:
        token = id(self.project)
        key = self._navigator_favorites_project_key()
        previous_token = getattr(self, "_navigator_favorites_project_token", None)
        previous_key = getattr(self, "_navigator_favorites_loaded_key", None)
        if token == previous_token and key == previous_key:
            return
        if token == previous_token:
            if key is not None:
                self._navigator_favorites_by_project[key] = list(
                    getattr(self, "_navigator_favorite_ids", [])
                )
            self._navigator_favorites_loaded_key = key
            return
        self._navigator_favorites_project_token = token
        self._navigator_favorites_loaded_key = key
        self._navigator_favorite_ids = (
            list(self._navigator_favorites_by_project.get(key, ()))
            if key is not None
            else []
        )
        self._navigator_favorite_display_to_id = {}
        favorites_var = getattr(self, "navigator_favorites_var", None)
        if favorites_var is not None:
            favorites_var.set("")

    def _store_current_navigator_favorites(self) -> None:
        self._sync_navigator_favorites_for_project()
        key = self._navigator_favorites_project_key()
        if key is None:
            return
        favorite_ids = list(getattr(self, "_navigator_favorite_ids", []))
        if favorite_ids:
            self._navigator_favorites_by_project[key] = favorite_ids
        else:
            self._navigator_favorites_by_project.pop(key, None)

    def _capture_navigator_favorites_state(self) -> dict[str, list[str]]:
        self._store_current_navigator_favorites()
        return {
            path: list(item_ids)
            for path, item_ids in self._navigator_favorites_by_project.items()
            if item_ids
        }

    def _refresh_navigator_favorites_picker(self) -> None:
        self._sync_navigator_favorites_for_project()
        tree = getattr(self, "analysis_tree", None)
        picker = getattr(self, "navigator_favorites_picker", None)
        if tree is None or picker is None:
            return
        original = list(getattr(self, "_navigator_favorite_ids", []))
        favorite_ids = [
            item_id
            for item_id in original
            if tree.exists(item_id) and self._navigator_item_is_actionable(item_id)
        ][:24]
        self._navigator_favorite_ids = favorite_ids
        if favorite_ids != original:
            self._store_current_navigator_favorites()

        display_to_id: dict[str, str] = {}
        displays: list[str] = []
        for item_id in favorite_ids:
            label = str(tree.item(item_id, "text") or item_id)
            display = f"{label} · {self._navigator_recent_category(item_id)}"
            if display in display_to_id:
                display = f"{display} · {item_id}"
            display_to_id[display] = item_id
            displays.append(display)
        self._navigator_favorite_display_to_id = display_to_id
        picker.configure(values=tuple(displays))
        if self.navigator_favorites_var.get() not in display_to_id:
            self.navigator_favorites_var.set("")
        self._update_navigator_favorite_button()

    def _is_navigator_favorite(self, item_id: str) -> bool:
        self._sync_navigator_favorites_for_project()
        return item_id in getattr(self, "_navigator_favorite_ids", ())

    def _toggle_navigator_favorite(self, item_id: str) -> bool:
        tree = getattr(self, "analysis_tree", None)
        if (
            tree is None
            or not item_id
            or not tree.exists(item_id)
            or not self._navigator_item_is_actionable(item_id)
        ):
            return False
        self._sync_navigator_favorites_for_project()
        favorite_ids = list(getattr(self, "_navigator_favorite_ids", []))
        if item_id in favorite_ids:
            favorite_ids.remove(item_id)
            added = False
        else:
            favorite_ids.insert(0, item_id)
            favorite_ids = favorite_ids[:24]
            added = True
        self._navigator_favorite_ids = favorite_ids
        self._store_current_navigator_favorites()
        self._refresh_navigator_favorites_picker()
        label = str(tree.item(item_id, "text") or item_id)
        self.status_var.set(
            f"{'Added to' if added else 'Removed from'} favorites: {label}"
        )
        self.root.after_idle(self._save_ui_layout_state)
        return True

    def toggle_selected_navigator_favorite(self) -> bool:
        tree = getattr(self, "analysis_tree", None)
        selection = tree.selection() if tree is not None else ()
        if not selection:
            self.status_var.set("Select an engineering item to favorite")
            self._update_navigator_favorite_button()
            return False
        return self._toggle_navigator_favorite(selection[0])

    def clear_navigator_favorites(self) -> None:
        self._sync_navigator_favorites_for_project()
        self._navigator_favorite_ids = []
        self._navigator_favorite_display_to_id = {}
        self.navigator_favorites_var.set("")
        self._store_current_navigator_favorites()
        picker = getattr(self, "navigator_favorites_picker", None)
        if picker is not None:
            picker.configure(values=())
        self._update_navigator_favorite_button()
        self.status_var.set("Project navigator favorites cleared")
        self.root.after_idle(self._save_ui_layout_state)

    def _on_favorite_navigator_selected(self, _event=None) -> None:
        item_id = self._navigator_favorite_display_to_id.get(
            self.navigator_favorites_var.get()
        )
        if not self._open_navigator_item(item_id or ""):
            self._refresh_navigator_favorites_picker()

    def _update_navigator_favorite_button(self) -> None:
        button = getattr(self, "navigator_favorite_toggle_button", None)
        tree = getattr(self, "analysis_tree", None)
        if button is None or tree is None:
            return
        selection = tree.selection()
        item_id = selection[0] if selection else ""
        actionable = bool(
            item_id
            and tree.exists(item_id)
            and self._navigator_item_is_actionable(item_id)
        )
        button.configure(
            text="★" if actionable and self._is_navigator_favorite(item_id) else "☆",
            state="normal" if actionable else "disabled",
        )

    def _apply_navigator_filter(self) -> None:
        tree = getattr(self, "analysis_tree", None)
        snapshot = list(getattr(self, "_navigator_tree_snapshot", []))
        if tree is None or not snapshot:
            return

        self._restore_navigator_tree()
        query = self.navigator_filter_var.get().strip().casefold()
        if not query:
            return

        children: dict[str, list[str]] = {}
        for iid, parent, _index in snapshot:
            children.setdefault(parent, []).append(iid)

        visible: set[str] = set()

        def include_subtree(iid: str) -> None:
            visible.add(iid)
            for child in children.get(iid, []):
                include_subtree(child)

        def match(iid: str) -> bool:
            if not tree.exists(iid):
                return False
            item = tree.item(iid)
            text = str(item.get("text") or "")
            values = " ".join(str(value) for value in item.get("values") or ())
            own_match = query in f"{text} {values}".casefold()
            if own_match:
                include_subtree(iid)
                return True
            child_match = False
            for child in children.get(iid, []):
                child_match = match(child) or child_match
            if child_match:
                visible.add(iid)
            return child_match

        for root_iid in children.get("", []):
            match(root_iid)

        for iid, _parent, _index in reversed(snapshot):
            if tree.exists(iid) and iid not in visible:
                tree.detach(iid)

        selection = tree.selection()
        if selection and selection[0] not in visible:
            tree.selection_remove(selection[0])

    def _build_navigator_context_menu(self, item_id: str) -> tk.Menu | None:
        tree = getattr(self, "analysis_tree", None)
        if tree is None or not item_id or not tree.exists(item_id):
            return None
        menu = tk.Menu(self.root, tearoff=False)
        if self._navigator_item_is_actionable(item_id):
            menu.add_command(
                label=(
                    "Remove from Favorites"
                    if self._is_navigator_favorite(item_id)
                    else "Add to Favorites"
                ),
                command=lambda selected=item_id: self._toggle_navigator_favorite(
                    selected
                ),
            )
            menu.add_separator()
        if item_id.startswith("room:") or item_id.startswith("device:"):
            kind, spatial_id = item_id.split(":", 1)

            def select_spatial() -> None:
                self.spatial_workspace.select_item(kind, spatial_id)
                self._activate_spatial_workspace()

            menu.add_command(label="Open / Properties", command=select_spatial)
            menu.add_command(
                label="Fit Selected",
                command=lambda: (
                    select_spatial(),
                    self.spatial_workspace.fit_selected(),
                ),
            )
            menu.add_separator()
            menu.add_command(
                label="Isolate",
                command=lambda: (
                    select_spatial(),
                    self.spatial_workspace.isolate_selected(),
                ),
            )
            menu.add_command(
                label="Hide",
                command=lambda: (
                    select_spatial(),
                    self.spatial_workspace.hide_selected(),
                ),
            )
            menu.add_command(
                label="Show All",
                command=self.spatial_workspace.show_all,
            )
            return menu
        if item_id == "nav-simulation":
            menu.add_command(
                label="Open Simulation",
                command=lambda: self.activate_workspace_profile("simulation"),
            )
            return menu
        if item_id == "nav-proofgraph":
            menu.add_command(
                label="Open ProofGraph",
                command=self._activate_proofgraph_workspace,
            )
            return menu
        if item_id == "nav-reports":
            menu.add_command(
                label="Open Reporting Workspace",
                command=self._activate_reporting_workspace,
            )
            menu.add_command(
                label="Export Project Engineering Dossier...",
                command=self.export_project_engineering_dossier,
            )
            return menu
        if not item_id.startswith("nav-"):
            menu.add_command(
                label="Open Analysis",
                command=lambda: self._on_navigator_selected(),
            )
            menu.add_command(label="Run Analysis", command=self.run_current)
            return menu
        menu.add_command(
            label="Expand",
            command=lambda: tree.item(item_id, open=True),
        )
        menu.add_command(
            label="Collapse",
            command=lambda: tree.item(item_id, open=False),
        )
        return menu

    def _show_navigator_context_menu(self, event: tk.Event):
        tree = self.analysis_tree
        item_id = tree.identify_row(event.y)
        if not item_id:
            return "break"
        tree.selection_set(item_id)
        tree.focus(item_id)
        menu = self._build_navigator_context_menu(item_id)
        if menu is None:
            return "break"
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _refresh_spatial_navigator(self) -> None:
        self._restore_navigator_tree()
        tree = getattr(self, "analysis_tree", None)
        if tree is None:
            return
        layout = self.project.metadata.get(SPATIAL_METADATA_KEY, {})
        if not isinstance(layout, dict):
            layout = {}
        rooms = layout.get("rooms", [])
        devices = layout.get("devices", [])
        if not isinstance(rooms, list):
            rooms = []
        if not isinstance(devices, list):
            devices = []

        previous_selection = tree.selection()
        previous_guard = self._selection_guard
        self._selection_guard = True
        try:
            if tree.exists("nav-building"):
                for child in tree.get_children("nav-building"):
                    tree.delete(child)
                floor = layout.get("floor", {})
                floor_name = (
                    str(floor.get("name", "Floor 01"))
                    if isinstance(floor, dict)
                    else "Floor 01"
                )
                tree.insert(
                    "nav-building",
                    "end",
                    iid="nav-floor",
                    text=floor_name,
                    open=True,
                )
                for room in rooms:
                    if not isinstance(room, dict) or not room.get("id"):
                        continue
                    room_id = str(room["id"])
                    tree.insert(
                        "nav-floor",
                        "end",
                        iid=f"room:{room_id}",
                        text=str(room.get("name") or room_id),
                    )

            if tree.exists("nav-devices"):
                for child in tree.get_children("nav-devices"):
                    tree.delete(child)
                for device in devices:
                    if not isinstance(device, dict) or not device.get("id"):
                        continue
                    device_id = str(device["id"])
                    device_type = str(device.get("type") or "device")
                    name = str(device.get("name") or device_id)
                    tree.insert(
                        "nav-devices",
                        "end",
                        iid=f"device:{device_id}",
                        text=f"{name}  [{device_type}]",
                    )

            if previous_selection:
                selected_iid = previous_selection[0]
                if tree.exists(selected_iid):
                    tree.selection_set(selected_iid)
                    tree.focus(selected_iid)
        finally:
            self._selection_guard = previous_guard

        model_status = getattr(self, "model_status_var", None)
        if model_status is not None:
            model_status.set(
                f"Spatial: {len(rooms)} rooms · {len(devices)} devices"
            )
        self._capture_navigator_tree()
        self._apply_navigator_filter()
        self._refresh_navigator_recent_picker()
        self._refresh_navigator_favorites_picker()

    def _sync_spatial_selection_status(self) -> None:
        workspace = getattr(self, "spatial_workspace", None)
        if workspace is None:
            self.selection_status_var.set("Selected: —")
            return
        self.selection_status_var.set(workspace.selection_status_text())

    def _sync_proofgraph_spatial_selection(self, kind: str, item_id: str) -> bool:
        if kind not in {"room", "device"} or not item_id:
            return False
        viewer = getattr(self, "proofgraph_viewer", None)
        if viewer is None:
            return False
        return bool(viewer.focus_node(f"model_object:{item_id}"))

    def _on_navigator_selected(self, event=None) -> None:
        if self._selection_guard:
            return
        selection = self.analysis_tree.selection()
        if not selection:
            return
        item_id = selection[0]
        self._update_navigator_favorite_button()
        if item_id.startswith("room:") or item_id.startswith("device:"):
            self._remember_navigator_item(item_id)
            kind, spatial_id = item_id.split(":", 1)
            if hasattr(self, "spatial_workspace"):
                self.spatial_workspace.select_item(kind, spatial_id)
                self._activate_spatial_workspace()
                self._sync_spatial_selection_status()
                self._sync_proofgraph_spatial_selection(kind, spatial_id)
            return
        if item_id == "nav-simulation":
            self._remember_navigator_item(item_id)
            self.activate_workspace_profile("simulation")
            self.selection_status_var.set("Selected: Simulation / Results")
            return
        if item_id == "nav-proofgraph":
            self._remember_navigator_item(item_id)
            self._activate_proofgraph_workspace()
            self.selection_status_var.set("Selected: ProofGraph")
            return
        if item_id == "nav-evidence":
            self._remember_navigator_item(item_id)
            if hasattr(self, "output_notebook") and hasattr(self, "evidence_text"):
                self.output_notebook.select(self.evidence_text.master)
            self.selection_status_var.set("Selected: Evidence")
            return
        if item_id == "nav-reports":
            self._remember_navigator_item(item_id)
            self._activate_reporting_workspace()
            self.selection_status_var.set("Selected: Reports")
            return
        if item_id.startswith("nav-"):
            return
        self._on_analysis_selected(event)
        analysis = self._current_analysis()
        if analysis is not None:
            self.selection_status_var.set(f"Selected: {analysis.name}")
            if analysis.id == item_id:
                self._remember_navigator_item(item_id)

    def _on_workspace_selection_change(self, kind: str, item_id: str) -> None:
        tree = getattr(self, "analysis_tree", None)
        if tree is None:
            return
        navigator_id = f"{kind}:{item_id}"
        self._sync_spatial_selection_status()
        self._sync_proofgraph_spatial_selection(kind, item_id)
        self._remember_navigator_item(navigator_id)
        if not tree.exists(navigator_id):
            self._refresh_spatial_navigator()
        if not tree.exists(navigator_id):
            return
        previous_guard = self._selection_guard
        self._selection_guard = True
        try:
            tree.selection_set(navigator_id)
            tree.focus(navigator_id)
            tree.see(navigator_id)
        finally:
            self._selection_guard = previous_guard

    def _on_analysis_selected(self, event=None) -> None:
        if self._selection_guard:
            return
        analysis = self._current_analysis()
        if analysis is None:
            return
        previous = self._editor_analysis()
        if self._running and previous is not None and previous.id != analysis.id:
            self._selection_guard = True
            try:
                if self.analysis_tree.exists(previous.id):
                    self.analysis_tree.selection_set(previous.id)
                    self.analysis_tree.focus(previous.id)
                    self.analysis_tree.see(previous.id)
            finally:
                self._selection_guard = False
            self.status_var.set(
                f"Running {previous.name} — abandon the current run before switching analyses."
            )
            return
        if previous is not None and previous.id != analysis.id:
            try:
                self._commit_editor(previous)
            except Exception as exc:
                self._selection_guard = True
                try:
                    if self.analysis_tree.exists(previous.id):
                        self.analysis_tree.selection_set(previous.id)
                        self.analysis_tree.focus(previous.id)
                        self.analysis_tree.see(previous.id)
                finally:
                    self._selection_guard = False
                messagebox.showerror(
                    "Cannot switch analysis",
                    f"Fix the current analysis input before switching.\n\n{exc}",
                    parent=self.root,
                )
                return
        self.project.active_analysis_id = analysis.id
        self._load_analysis_into_editor(analysis)
        self._update_title()

    def _load_analysis_into_editor(self, analysis: AnalysisDocument) -> None:
        self._editor_analysis_id = analysis.id
        self.input_text.delete("1.0", "end")
        self.input_text.insert(
            "1.0",
            json.dumps(analysis.input, indent=2, ensure_ascii=False, sort_keys=False),
        )
        self.input_text.edit_modified(False)
        self.status_var.set(f"{analysis.name} — {ANALYSIS_SPECS[analysis.kind].title}")
        self.refresh_structure(silent=True)
        self._restore_run_for(analysis.id)
        self._refresh_simulation_workspace()
        if hasattr(self, "spatial_workspace"):
            self.spatial_workspace.refresh()
            self._sync_spatial_selection_status()

    def _on_spatial_changed(self) -> None:
        self._update_title()
        self._refresh_spatial_navigator()
        self._schedule_project_diagnostics_refresh()

    def _select_ifc_source(self, *, title: str) -> Path | None:
        path = filedialog.askopenfilename(
            parent=self.root,
            title=title,
            filetypes=[("Industry Foundation Classes", "*.ifc"), ("All files", "*.*")],
        )
        return Path(path) if path else None

    def _show_ifc_plan(self, report: dict) -> None:
        dialog = IfcReimportPlanDialog(self.root, report)
        wait_window = getattr(self.root, "wait_window", None)
        if callable(wait_window):
            wait_window(dialog)

    def _extract_ifc_candidate(
        self,
        source: Path,
    ) -> tuple[dict, dict[str, str]]:
        """Extract an IFC candidate and bind provenance to the selected filename."""
        semantics, provenance = extract_ifc_semantics(source)
        if provenance.get("source_name") != source.name:
            raise IfcImportError(
                "IFC provenance source name does not match the selected file"
            )
        return semantics, provenance

    def _revalidate_reviewed_ifc_source(
        self,
        source: Path,
        *,
        expected_semantics: dict,
        expected_provenance: dict[str, str],
    ) -> tuple[dict, dict[str, str]]:
        """Reject review-to-apply IFC source drift before project mutation."""
        semantics, provenance = self._extract_ifc_candidate(source)
        if (
            provenance.get("source_sha256")
            != expected_provenance.get("source_sha256")
            or semantics.get("semantic_sha256")
            != expected_semantics.get("semantic_sha256")
        ):
            raise IfcImportError(
                "IFC source changed after review; no project changes were applied. "
                "Review the current IFC file again before applying it."
            )
        return semantics, provenance

    def _refresh_after_ifc_edit(self) -> None:
        workspace = getattr(self, "spatial_workspace", None)
        if workspace is not None:
            workspace.refresh()
        self._update_title()

    def import_ifc_spatial_layout(self) -> bool:
        """Import a new IFC baseline into project spatial metadata without auto-saving."""
        if self._running:
            messagebox.showwarning(
                "Analysis running",
                "Abandon the current run before importing IFC spatial data.",
                parent=self.root,
            )
            return False
        if IFC_LINK_METADATA_KEY in self.project.metadata:
            messagebox.showinfo(
                "IFC link already established",
                (
                    "This project already has an IFC identity baseline. Use Review IFC "
                    "Re-import and Apply IFC Re-import so GlobalId identity and conflict "
                    "checks are preserved."
                ),
                parent=self.root,
            )
            return False

        source = self._select_ifc_source(title="Import IFC spatial layout")
        if source is None:
            return False
        if not self._prepare_project_history_action("import IFC spatial data"):
            return False

        try:
            semantics, provenance = self._extract_ifc_candidate(source)
            preview = layout_from_ifc_semantics(semantics)
        except Exception as exc:
            self.status_var.set("IFC import failed")
            messagebox.showerror("IFC import failed", str(exc), parent=self.root)
            return False

        existing_layout = self.project.metadata.get(SPATIAL_METADATA_KEY)
        review_snapshot = ifc_import_review_snapshot(
            semantics,
            provenance,
            preview,
            existing_layout=(
                existing_layout if isinstance(existing_layout, dict) else None
            ),
        )
        if not show_ifc_import_review(self.root, review_snapshot):
            self.status_var.set("IFC import cancelled")
            return False

        try:
            semantics, provenance = self._revalidate_reviewed_ifc_source(
                source,
                expected_semantics=semantics,
                expected_provenance=provenance,
            )
            layout = self._perform_project_edit(
                "Import IFC spatial layout",
                lambda: apply_ifc_semantics_to_project(
                    self.project,
                    semantics,
                    source_name=provenance["source_name"],
                    source_sha256=provenance["source_sha256"],
                ),
            )
        except Exception as exc:
            self.status_var.set("IFC import failed")
            messagebox.showerror("IFC import failed", str(exc), parent=self.root)
            return False

        self._refresh_after_ifc_edit()
        self.status_var.set(
            f"Imported IFC spatial layout — {len(layout['rooms'])} room(s), "
            f"{len(layout['devices'])} device(s); save the project to persist it."
        )
        messagebox.showinfo(
            "IFC spatial layout imported",
            (
                f"Source: {provenance['source_name']}\n"
                f"Rooms: {len(layout['rooms'])}\n"
                f"Devices: {len(layout['devices'])}\n"
                f"SHA-256: {provenance['source_sha256']}\n\n"
                "Engineering analysis inputs were not changed automatically."
            ),
            parent=self.root,
        )
        return True

    def review_ifc_reimport(self) -> dict | None:
        """Show a read-only three-way IFC re-import plan."""
        if IFC_LINK_METADATA_KEY not in self.project.metadata:
            messagebox.showinfo(
                "No IFC identity baseline",
                "Import an IFC spatial layout first before reviewing a re-import.",
                parent=self.root,
            )
            return None
        source = self._select_ifc_source(title="Review revised IFC file")
        if source is None:
            return None
        try:
            semantics, provenance = extract_ifc_semantics(source)
            report = plan_ifc_semantic_reimport(
                self.project,
                semantics,
                source_name=provenance["source_name"],
                source_sha256=provenance["source_sha256"],
            )
        except Exception as exc:
            self.status_var.set("IFC re-import review failed")
            messagebox.showerror(
                "IFC re-import review failed",
                str(exc),
                parent=self.root,
            )
            return None

        self._show_ifc_plan(report)
        if report["can_apply"]:
            self.status_var.set("IFC re-import plan is conflict-free and ready to apply")
        else:
            self.status_var.set(
                f"IFC re-import blocked — {report['conflict_count']} conflict(s)"
            )
        return report

    def apply_ifc_reimport(self) -> bool:
        """Review and transactionally apply a conflict-free IFC revision."""
        if self._running:
            messagebox.showwarning(
                "Analysis running",
                "Abandon the current run before applying an IFC re-import.",
                parent=self.root,
            )
            return False
        if IFC_LINK_METADATA_KEY not in self.project.metadata:
            messagebox.showinfo(
                "No IFC identity baseline",
                "Import an IFC spatial layout first before applying a re-import.",
                parent=self.root,
            )
            return False

        source = self._select_ifc_source(title="Apply revised IFC file")
        if source is None:
            return False
        if not self._prepare_project_history_action("apply IFC re-import"):
            return False

        try:
            semantics, provenance = extract_ifc_semantics(source)
            report = plan_ifc_semantic_reimport(
                self.project,
                semantics,
                source_name=provenance["source_name"],
                source_sha256=provenance["source_sha256"],
            )
        except Exception as exc:
            self.status_var.set("IFC re-import planning failed")
            messagebox.showerror(
                "IFC re-import planning failed",
                str(exc),
                parent=self.root,
            )
            return False

        self._show_ifc_plan(report)
        if not report["can_apply"]:
            self.status_var.set(
                f"IFC re-import blocked — {report['conflict_count']} conflict(s)"
            )
            messagebox.showwarning(
                "IFC re-import blocked",
                (
                    "The revised IFC file cannot be applied safely. Resolve the "
                    "reported two-sided conflicts or spatial validation error first."
                ),
                parent=self.root,
            )
            return False

        if not messagebox.askyesno(
            "Apply IFC re-import?",
            (
                "Apply this conflict-free IFC revision to the spatial layout?\n\n"
                "Stable IFC GlobalId bindings will be preserved. Local-only edits are "
                "kept where the IFC entity is unchanged. Engineering analysis inputs "
                "are not synchronized automatically."
            ),
            parent=self.root,
        ):
            return False

        try:
            semantics, provenance = self._revalidate_reviewed_ifc_source(
                source,
                expected_semantics=semantics,
                expected_provenance=provenance,
            )
            self._perform_project_edit(
                "Apply IFC re-import",
                lambda: reimport_ifc_semantics_to_project(
                    self.project,
                    semantics,
                    source_name=provenance["source_name"],
                    source_sha256=provenance["source_sha256"],
                ),
            )
        except Exception as exc:
            self.status_var.set("IFC re-import failed")
            messagebox.showerror("IFC re-import failed", str(exc), parent=self.root)
            return False

        self._refresh_after_ifc_edit()
        summary = report.get("summary", {})
        changed = sum(
            int(summary.get(key, 0))
            for key in ("add", "update", "remove", "converged")
        )
        self.status_var.set(
            f"Applied IFC re-import — {changed} source change(s); save the project "
            "to persist it."
        )
        return True

    def _sync_spatial_to_current_analysis(self) -> None:
        if self._running:
            messagebox.showwarning(
                "Analysis running",
                "Abandon the current run before synchronizing spatial geometry.",
                parent=self.root,
            )
            return
        analysis = self._editor_analysis() or self._current_analysis()
        if analysis is None:
            messagebox.showinfo(
                "No active analysis",
                "Select a room-verification or multi-room verification analysis first.",
                parent=self.root,
            )
            return
        try:
            self._commit_editor(analysis)
        except Exception as exc:
            messagebox.showerror(
                "Cannot synchronize geometry",
                f"Fix the current analysis input before synchronizing.\n\n{exc}",
                parent=self.root,
            )
            return
        if analysis.kind not in {"room_verification", "project_verification"}:
            messagebox.showinfo(
                "Spatial synchronization",
                "Geometry synchronization currently targets room-verification and "
                "multi-room project-verification inputs. The spatial layout remains "
                "available for all projects.",
                parent=self.root,
            )
            return
        try:
            changed = self._perform_project_edit(
                f"Synchronize spatial geometry to {analysis.name}",
                lambda: sync_layout_to_analysis(self.spatial_workspace.layout, analysis),
            )
        except SpatialSyncError as exc:
            self.status_var.set("Spatial synchronization blocked by a mapping conflict")
            messagebox.showwarning(
                "Cannot synchronize geometry",
                str(exc),
                parent=self.root,
            )
            return
        # Synchronization also records a common geometry baseline used to prove
        # later geometry-newer / engineering-newer states without guessing.
        self.spatial_workspace.refresh()
        if not changed:
            self.status_var.set("Spatial geometry already matches the active analysis")
            return
        self._invalidate_last_run_for(analysis.id)
        self._load_analysis_into_editor(analysis)
        self._update_title()
        self.status_var.set(
            f"Synchronized spatial room dimensions to {analysis.name}; validate before running."
        )

    def _sync_current_analysis_to_spatial(self) -> None:
        if self._running:
            messagebox.showwarning(
                "Analysis running",
                "Abandon the current run before synchronizing spatial geometry.",
                parent=self.root,
            )
            return
        analysis = self._editor_analysis() or self._current_analysis()
        if analysis is None:
            messagebox.showinfo(
                "No active analysis",
                "Select a room-verification or multi-room verification analysis first.",
                parent=self.root,
            )
            return
        try:
            self._commit_editor(analysis)
        except Exception as exc:
            messagebox.showerror(
                "Cannot synchronize geometry",
                f"Fix the current analysis input before synchronizing.\n\n{exc}",
                parent=self.root,
            )
            return
        if analysis.kind not in {"room_verification", "project_verification"}:
            messagebox.showinfo(
                "Spatial synchronization",
                "Geometry synchronization currently targets room-verification and "
                "multi-room project-verification inputs.",
                parent=self.root,
            )
            return
        try:
            changed = self._perform_project_edit(
                f"Pull engineering dimensions from {analysis.name}",
                lambda: sync_analysis_to_layout(self.spatial_workspace.layout, analysis),
            )
        except SpatialSyncError as exc:
            self.status_var.set("Engineering-to-spatial synchronization blocked")
            messagebox.showwarning(
                "Cannot synchronize geometry",
                str(exc),
                parent=self.root,
            )
            return
        self.spatial_workspace.refresh()
        self._update_title()
        if changed:
            self.status_var.set(
                f"Pulled engineering room dimensions from {analysis.name} into the spatial layout."
            )
        else:
            self.status_var.set("Spatial geometry already matches the active analysis")

    def _edit_structured_input_value(self) -> bool:
        if self._running:
            self.status_var.set("Structured input edit blocked while analysis is running")
            messagebox.showwarning(
                "Analysis running",
                "Abandon the current run before editing analysis inputs.",
                parent=self.root,
            )
            return False

        selection = self.structure_tree.selection()
        if not selection:
            self.status_var.set("Select a structured input value to edit")
            return False
        row = self._structure_rows.get(selection[0])
        if row is None:
            return False
        tokens, current_value, unit = row
        if isinstance(current_value, (dict, list)):
            self.status_var.set(
                "Structured editing is limited to scalar values; use the JSON editor "
                "for objects and arrays"
            )
            return False

        path = str(self.structure_tree.item(selection[0], "text"))
        initial = json.dumps(
            current_value,
            ensure_ascii=False,
            allow_nan=False,
        )
        prompt = (
            f"{path}"
            + (f"  [{unit}]" if unit else "")
            + "\n\nEnter one JSON scalar value (text must be quoted):"
        )
        raw = simpledialog.askstring(
            "Edit structured analysis input",
            prompt,
            initialvalue=initial,
            parent=self.root,
        )
        if raw is None:
            return False

        try:
            replacement = _strict_json_loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            messagebox.showerror(
                "Invalid structured value",
                f"Enter one valid JSON scalar value.\n\n{exc}",
                parent=self.root,
            )
            return False
        if isinstance(replacement, (dict, list)):
            messagebox.showerror(
                "Structured edit not supported",
                "Objects and arrays must be edited in the JSON editor.",
                parent=self.root,
            )
            return False

        text = self.input_text.get("1.0", "end-1c").strip()
        try:
            payload = _strict_json_loads(text)
            candidate = replace_structured_json_value(payload, tokens, replacement)
            analysis = self._editor_analysis() or self._current_analysis()
            if analysis is None:
                raise ValueError("select or add an analysis first")
            validate_analysis_input(
                analysis.kind,
                candidate,
                base_dir=self._base_dir(),
            )
        except Exception as exc:
            self.status_var.set("Structured input edit rejected by analysis validation")
            messagebox.showerror(
                "Analysis input rejected",
                (
                    "The candidate value was not applied because the authoritative "
                    f"analysis parser/validator rejected the complete input.\n\n{exc}"
                ),
                parent=self.root,
            )
            return False

        serialized = json.dumps(
            candidate,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        self.input_text.edit_separator()
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", serialized)
        self.input_text.edit_modified(True)
        self.input_text.edit_separator()
        self.refresh_structure(silent=True)
        self.status_var.set(
            f"Updated {path}; validate/run or save to commit the edited analysis input"
        )
        return True

    def refresh_structure(self, silent: bool = False) -> None:
        for item in self.structure_tree.get_children():
            self.structure_tree.delete(item)
        self._structure_rows.clear()
        text = self.input_text.get("1.0", "end-1c").strip()
        if not text:
            return
        try:
            payload = _strict_json_loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            if not silent:
                detail = (
                    f"Line {exc.lineno}, column {exc.colno}: {exc.msg}"
                    if isinstance(exc, json.JSONDecodeError)
                    else str(exc)
                )
                messagebox.showerror("Invalid JSON", detail, parent=self.root)
            return
        for index, (path, tokens, raw_value, unit) in enumerate(
            structured_json_entries(payload)
        ):
            value = json.dumps(
                raw_value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            display = value if len(value) <= 160 else value[:157] + "..."
            iid = f"row-{index}"
            self.structure_tree.insert(
                "",
                "end",
                iid=iid,
                text=path,
                values=(display, unit),
            )
            self._structure_rows[iid] = (tokens, copy.deepcopy(raw_value), unit)

    def restore_recovery_path(self, path: str | Path) -> None:
        recovered = restore_recovery_artifact(path)
        self._discard_current_autosave()
        self.project = recovered.project
        self.project_path = None
        self._project_file_revision = None
        self._recovery_source_path = recovered.source_path
        self._restored_recovery_artifact = recovered.artifact_path
        self._migration_source_path = None
        self._begin_autosave_project(recovered.source_path)

        ui_state = recovered.ui_state
        name_text = ui_state.get("name_text")
        description_text = ui_state.get("description_text")
        self.name_var.set(
            name_text if isinstance(name_text, str) else self.project.name
        )
        self.description_var.set(
            description_text
            if isinstance(description_text, str)
            else self.project.description
        )
        self._clear_run_cache()
        self._clear_project_history()
        self._refresh_analysis_list()

        editor_id = ui_state.get("editor_analysis_id")
        editor_text = ui_state.get("editor_text")
        if (
            isinstance(editor_id, str)
            and isinstance(editor_text, str)
            and self.analysis_tree.exists(editor_id)
        ):
            self.project.active_analysis_id = editor_id
            self.analysis_tree.selection_set(editor_id)
            self.analysis_tree.focus(editor_id)
            self.analysis_tree.see(editor_id)
            self._editor_analysis_id = editor_id
            self.input_text.delete("1.0", "end")
            self.input_text.insert("1.0", editor_text)
            self.input_text.edit_modified(False)
            self.refresh_structure(silent=True)

        # A recovered copy must require an explicit Save As even when its recovered
        # model happens to equal the source project byte-for-byte.
        self._baseline_state = "__cleanroomx_recovered_copy_requires_save_as__"
        self.status_var.set(
            "Recovered unsaved work — use Save Project As to preserve it separately."
        )
        self.autosave_status_var.set("Autosave: recovered copy")
        self._update_title()

    def show_recovery_center(self, *, announce_empty: bool = True) -> bool:
        try:
            scan = scan_recovery_artifacts(self._autosave_manager.recovery_dir)
        except OSError as exc:
            messagebox.showerror(
                "Recovery scan failed",
                str(exc),
                parent=self.root,
            )
            return False
        if not scan.candidates and not scan.issues:
            if announce_empty:
                self.status_var.set("No recoverable sessions found.")
            return False

        dialog = RecoveryCenter(self.root, scan)
        self.root.wait_window(dialog)
        if dialog.result is None:
            return False
        if not self._confirm_project_replacement():
            return False
        try:
            self.restore_recovery_path(dialog.result)
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "Recovery restore failed",
                (
                    f"{exc}\n\n"
                    "The recovery artifact was preserved and the original project "
                    "was not changed."
                ),
                parent=self.root,
            )
            return False
        return True

    def show_saved_revisions(self) -> bool:
        if self.project_path is None:
            self.status_var.set("Save the project before browsing saved revisions.")
            return False

        try:
            scan = scan_project_revisions(self.project_path)
        except OSError as exc:
            messagebox.showerror(
                "Revision scan failed",
                str(exc),
                parent=self.root,
            )
            return False
        if not scan.revisions and not scan.issues:
            self.status_var.set("No saved project revisions found.")
            return False

        dialog = ProjectRevisionCenter(self.root, scan)
        self.root.wait_window(dialog)
        if dialog.result is None:
            return False

        base_name = self.project_path.name
        if base_name.endswith(".cleanroomx.json"):
            base_name = base_name[: -len(".cleanroomx.json")]
        destination_text = filedialog.asksaveasfilename(
            parent=self.root,
            title="Restore saved revision as a copy",
            initialdir=str(self.project_path.parent),
            initialfile=f"{base_name}.restored.cleanroomx.json",
            defaultextension=".cleanroomx.json",
            filetypes=[
                ("CleanroomX project", "*.cleanroomx.json"),
                ("JSON files", "*.json"),
            ],
        )
        if not destination_text:
            return False

        destination = Path(destination_text)
        try:
            _assert_project_output_is_safe(
                self.project,
                source=self.project_path,
                output=destination,
            )
            restored_path = restore_project_revision(
                dialog.result,
                destination,
                expected_source_path=self.project_path,
                before_replace=lambda target: _assert_project_output_is_safe(
                    self.project,
                    source=self.project_path,
                    output=target,
                ),
            )
        except ProjectWriteConflictError:
            self.status_var.set(
                f"Revision restore blocked: {destination.name} changed on disk."
            )
            messagebox.showwarning(
                "Restore destination changed on disk",
                (
                    f"{destination.name} changed after it was selected. "
                    "CleanroomX did not overwrite it. Choose another destination "
                    "or retry after reviewing the file."
                ),
                parent=self.root,
            )
            return False
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "Revision restore failed",
                (
                    f"{exc}\n\n"
                    "The current project and the saved revision artifact were preserved."
                ),
                parent=self.root,
            )
            return False

        self.status_var.set(f"Restored saved revision as {restored_path.name}")
        return True

    def offer_startup_recovery(self) -> bool:
        return self.show_recovery_center(announce_empty=False)

    def new_project(self) -> None:
        if self._running:
            messagebox.showwarning("Analysis running", "Abandon the current run first.")
            return
        if not self._confirm_project_replacement():
            return
        self._discard_current_autosave()
        self.project = new_project()
        self.project_path = None
        self._project_file_revision = None
        self._recovery_source_path = None
        self._restored_recovery_artifact = None
        self._migration_source_path = None
        self._begin_autosave_project(None)
        self.name_var.set(self.project.name)
        self.description_var.set("")
        self._clear_run_cache()
        self._clear_project_history()
        self._refresh_analysis_list()
        self._refresh_engineering_panels()
        self._capture_saved_state()
        self.status_var.set("New project")
        self._refresh_start_center()
        self._update_title()
        self._activate_spatial_workspace("split")

    def open_project(self) -> None:
        if self._running:
            messagebox.showwarning("Analysis running", "Abandon the current run first.")
            return
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Open CleanroomX project",
            filetypes=[
                ("CleanroomX project", "*.cleanroomx.json"),
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if path:
            if not self._confirm_project_replacement():
                return
            try:
                self.load_project_path(path)
            except Exception as exc:
                messagebox.showerror("Open failed", str(exc), parent=self.root)

    def open_portable_project_bundle(self) -> None:
        if self._running:
            messagebox.showwarning("Analysis running", "Abandon the current run first.")
            return
        bundle_path = filedialog.askopenfilename(
            parent=self.root,
            title="Open CleanroomX portable project bundle",
            filetypes=[
                ("CleanroomX portable bundle", "*.cleanroomx.zip"),
                ("ZIP archives", "*.zip"),
                ("All files", "*.*"),
            ],
        )
        if not bundle_path:
            return
        if not self._confirm_project_replacement():
            return
        parent_directory = filedialog.askdirectory(
            parent=self.root,
            title="Choose folder for the extracted portable project",
        )
        if not parent_directory:
            return

        bundle = Path(bundle_path)
        suffix = ".cleanroomx.zip"
        folder_name = (
            bundle.name[:-len(suffix)]
            if bundle.name.lower().endswith(suffix)
            else bundle.stem
        )
        folder_name = folder_name.strip()
        if folder_name in {"", ".", ".."}:
            folder_name = "CleanroomX Portable Project"
        destination = Path(parent_directory) / folder_name
        try:
            project_path = extract_project_bundle(bundle, destination)
            self.load_project_path(project_path)
        except Exception as exc:
            self.status_var.set("Portable project open failed")
            messagebox.showerror(
                "Portable project open failed",
                str(exc),
                parent=self.root,
            )
            return
        self.status_var.set(f"Opened portable project — {project_path.parent.name}")

    def export_portable_project_bundle(self) -> None:
        if self._running:
            messagebox.showwarning("Analysis running", "Abandon the current run first.")
            return
        try:
            if self._editor_analysis() is not None:
                self._commit_editor()
            else:
                self._sync_metadata()
        except Exception as exc:
            messagebox.showerror(
                "Cannot export portable project",
                str(exc),
                parent=self.root,
            )
            return

        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export CleanroomX portable project bundle",
            defaultextension=".cleanroomx.zip",
            filetypes=[
                ("CleanroomX portable bundle", "*.cleanroomx.zip"),
                ("ZIP archives", "*.zip"),
            ],
        )
        if not path:
            return
        try:
            report = export_project_bundle(
                path,
                self.project,
                source_base=self._base_dir(),
                source_project_path=self._autosave_source_path(),
            )
        except Exception as exc:
            self.status_var.set("Portable project export failed")
            messagebox.showerror(
                "Portable project export failed",
                str(exc),
                parent=self.root,
            )
            return

        self.status_var.set(
            f"Portable project exported — {report['dependency_count']} "
            f"dependency file(s)"
        )
        messagebox.showinfo(
            "Portable project exported",
            (
                f"Created {Path(path).name}.\n\n"
                f"Dependencies packaged: {report['dependency_count']}\n"
                f"Bundle SHA-256: {report['bundle_sha256']}"
            ),
            parent=self.root,
        )

    def export_selected_reporting_summary(self) -> None:
        workspace = getattr(self, "reporting_workspace", None)
        if workspace is None:
            return
        self._refresh_engineering_panels()
        if not workspace.selected_sections():
            self.status_var.set(
                "Select at least one report section before exporting."
            )
            messagebox.showwarning(
                "No report sections selected",
                "Select one or more report-composition sections in the Reporting workspace.",
                parent=self.root,
            )
            return

        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export CleanroomX selected report summary",
            initialfile=(
                f"{self.project_path.stem}.summary.md"
                if self.project_path is not None
                else "cleanroomx-summary.md"
            ),
            defaultextension=".md",
            filetypes=[
                ("Markdown report", "*.md"),
                ("Text files", "*.txt"),
            ],
        )
        if not path:
            return
        if self._write_export_file(
            path,
            workspace.build_selected_summary_markdown(),
            label="Selected report summary",
        ):
            self.status_var.set(
                f"Selected report summary exported: {Path(path).name}"
            )

    def export_project_engineering_dossier(self) -> None:
        if self._running:
            messagebox.showwarning(
                "Analysis running",
                "Abandon the current run first.",
                parent=self.root,
            )
            return
        try:
            if self._editor_analysis() is not None:
                self._commit_editor()
            else:
                self._sync_metadata()
        except Exception as exc:
            messagebox.showerror(
                "Cannot export project dossier",
                str(exc),
                parent=self.root,
            )
            return

        if self.project_path is None:
            self.status_var.set("Save the project before exporting a project dossier.")
            messagebox.showinfo(
                "Save project first",
                (
                    "The project-native dossier must be bound to exact saved project "
                    "bytes. Save the project first, then export the dossier."
                ),
                parent=self.root,
            )
            return
        if self._has_unsaved_changes():
            self.status_var.set("Save project changes before exporting a project dossier.")
            messagebox.showinfo(
                "Save project changes first",
                (
                    "The project has unsaved changes. Save them before exporting so "
                    "the dossier can record the exact source-project SHA-256."
                ),
                parent=self.root,
            )
            return

        try:
            revision_before = capture_project_file_revision(self.project_path)
            expected_revision = getattr(self, "_project_file_revision", None)
            if (
                expected_revision is not None
                and not project_file_revision_matches(
                    expected_revision,
                    revision_before,
                )
            ):
                raise RuntimeError(
                    "project file changed on disk after it was opened or saved"
                )
        except Exception as exc:
            self.status_var.set("Project dossier export blocked")
            messagebox.showerror(
                "Project dossier export blocked",
                str(exc),
                parent=self.root,
            )
            return

        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export CleanroomX project engineering dossier",
            initialfile=f"{self.project_path.stem}.dossier.json",
            defaultextension=".json",
            filetypes=[
                ("CleanroomX dossier JSON", "*.json"),
                ("Markdown report", "*.md"),
            ],
        )
        if not path:
            return

        try:
            _assert_project_output_is_safe(
                self.project,
                source=self.project_path,
                output=path,
            )
            dossier = build_project_engineering_dossier(
                self.project,
                source_project_revision=revision_before.sha256,
                base_dir=self.project_path.parent,
            )
            destination = Path(path)
            if destination.suffix.lower() in {".md", ".markdown"}:
                content = markdown_project_engineering_dossier(dossier)
                label = "Project dossier"
            else:
                content = (
                    json.dumps(
                        dossier,
                        indent=2,
                        sort_keys=True,
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                    + "\n"
                )
                label = "Project dossier"

            revision_after = capture_project_file_revision(self.project_path)
            if not project_file_revision_matches(revision_before, revision_after):
                raise RuntimeError(
                    "project file changed during dossier generation; export was discarded"
                )
            _assert_project_publication_safe(
                self.project,
                source=self.project_path,
                revision=revision_before,
                output=path,
            )
        except Exception as exc:
            self.status_var.set("Project dossier export failed")
            messagebox.showerror(
                "Project dossier export failed",
                str(exc),
                parent=self.root,
            )
            return

        if not self._write_export_file(
            path,
            content,
            label=label,
            before_replace=lambda: _assert_project_publication_safe(
                self.project,
                source=self.project_path,
                revision=revision_before,
                output=path,
            ),
        ):
            return
        messagebox.showinfo(
            "Project dossier exported",
            (
                f"Created {Path(path).name}.\n\n"
                f"Source project SHA-256: {dossier['source_project_revision']}\n"
                f"Dossier SHA-256: {dossier['dossier_sha256']}"
            ),
            parent=self.root,
        )

    def load_project_path(self, path: str | Path) -> None:
        project_path = Path(path)
        (
            project,
            project_revision,
            migration_info,
        ) = load_project_document_with_revision_info(project_path)
        self._discard_current_autosave()
        self.project = project
        self.project_path = project_path
        self._project_file_revision = project_revision
        self._recovery_source_path = None
        self._restored_recovery_artifact = None
        self._migration_source_path = (
            project_path.resolve(strict=False) if migration_info.migrated else None
        )
        self._begin_autosave_project(project_path)
        self.name_var.set(project.name)
        self.description_var.set(project.description)
        self._clear_run_cache()
        self._clear_project_history()
        self._refresh_analysis_list()
        self._refresh_engineering_panels()
        if migration_info.migrated:
            # Keep the current-schema conversion explicitly unsaved so the first
            # normal Save cannot destroy the only pre-migration source.
            self._baseline_state = "__cleanroomx_migrated_copy_requires_save_as__"
            self.status_var.set(
                "Legacy project migrated in memory — use Save Project As to preserve "
                "the original source file."
            )
            self._update_title()
        else:
            self._capture_saved_state()
            self.status_var.set(f"Opened {project_path.name}")
            self._update_title()
        self._remember_recent_project(project_path)
        self._activate_spatial_workspace()

    def _update_title(self) -> None:
        has_unsaved_changes = self._has_unsaved_changes()
        if has_unsaved_changes:
            self._schedule_recovery_checkpoint()

        title_method = getattr(self.root, "title", None)
        if not callable(title_method):
            return
        if getattr(self, "_migration_source_path", None) is not None:
            suffix = f" — Migrated copy of {self.project_path.name}"
        elif self.project_path is not None:
            suffix = f" — {self.project_path.name}"
        elif getattr(self, "_restored_recovery_artifact", None) is not None:
            suffix = " — Recovered copy"
        else:
            suffix = ""
        dirty = " *" if has_unsaved_changes else ""
        title_method(f"CleanroomX {__version__}{suffix}{dirty}")

    def _report_external_save_conflict(self, path: Path) -> None:
        self.status_var.set(
            f"Save blocked: {path.name} changed on disk. Use Save Project As or reopen."
        )
        messagebox.showwarning(
            "Project changed on disk",
            (
                f"{path.name} was changed by another process or CleanroomX session "
                "after this window opened it.\n\n"
                "CleanroomX did not overwrite that newer file. Use Save Project As "
                "to preserve this window's work under another name, or reopen the "
                "project to use the on-disk version."
            ),
            parent=self.root,
        )

    def _report_project_save_busy(self, path: Path) -> None:
        self.status_var.set(
            f"Save blocked: another CleanroomX process is saving {path.name}."
        )
        messagebox.showwarning(
            "Project save in progress",
            (
                f"Another CleanroomX process is currently saving {path.name}.\n\n"
                "This window did not write to the project. Retry Save after the "
                "other save completes; revision protection will still reject any "
                "newer on-disk content."
            ),
            parent=self.root,
        )

    def _report_save_durability_uncertain(self, path: Path) -> None:
        self.status_var.set(
            f"Save durability not confirmed for {path.name}; recovery state retained."
        )
        messagebox.showwarning(
            "Save durability not confirmed",
            (
                f"CleanroomX wrote and verified the new bytes for {path.name}, but "
                "the filesystem could not confirm that the directory update is "
                "crash-durable.\n\n"
                "This window remains marked as unsaved and recovery data is retained. "
                "Retry Save; if the warning continues, save to another location."
            ),
            parent=self.root,
        )

    def save_project(self) -> None:
        try:
            if self._editor_analysis() is not None:
                self._commit_editor()
            else:
                self._sync_metadata()
        except Exception as exc:
            messagebox.showerror("Cannot save", str(exc), parent=self.root)
            return
        if self.project_path is None:
            self.save_project_as()
            return
        if getattr(self, "_migration_source_path", None) is not None:
            self.save_project_as()
            return

        expected_revision = getattr(self, "_project_file_revision", None)
        try:
            if expected_revision is None:
                expected_revision = capture_project_file_revision(self.project_path)
            saved_path, saved_revision = save_project_document_guarded(
                self.project_path,
                self.project,
                expected_revision=expected_revision,
            )
        except ProjectFileBusyError:
            self._report_project_save_busy(self.project_path)
            return
        except ProjectSaveDurabilityError as exc:
            self._project_file_revision = exc.committed_revision
            self._report_save_durability_uncertain(self.project_path)
            return
        except ProjectWriteConflictError:
            self._report_external_save_conflict(self.project_path)
            return
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self.root)
            return

        self.project_path = saved_path
        self._project_file_revision = saved_revision
        self._capture_saved_state()
        self._notify_explicit_save(self.project_path)
        self._remember_recent_project(self.project_path)
        self.status_var.set(f"Saved {self.project_path.name}")

    def _assert_save_as_destination_safe(self, target: str | Path) -> None:
        """Reject Save As targets that alias protected project inputs."""
        destination = Path(target)
        migration_source = getattr(self, "_migration_source_path", None)
        if migration_source is not None and _paths_alias(
            Path(migration_source),
            destination,
        ):
            raise ValueError(
                "project save destination must be different from the protected "
                "legacy migration source"
            )

        recovery_source = getattr(self, "_recovery_source_path", None)
        restored_artifact = getattr(self, "_restored_recovery_artifact", None)
        if (
            restored_artifact is not None
            and recovery_source is not None
            and _paths_alias(Path(recovery_source), destination)
        ):
            raise ValueError(
                "project save destination must be different from the protected "
                "recovery source"
            )

        base_dir = self._base_dir()
        if base_dir is None and migration_source is not None:
            base_dir = Path(migration_source).parent

        for analysis in self.project.analyses:
            for field, declared_path in analysis_external_dependency_references(
                analysis.kind,
                analysis.input,
            ):
                dependency = Path(declared_path)
                if not dependency.is_absolute():
                    if base_dir is None:
                        continue
                    dependency = base_dir / dependency
                if _paths_alias(dependency, destination):
                    raise ValueError(
                        "project save destination must be different from external "
                        f"dependency {field!r} for analysis {analysis.id!r}: "
                        f"{dependency.resolve(strict=False)}"
                    )

    def save_project_as(self) -> None:
        try:
            if self._editor_analysis() is not None:
                self._commit_editor()
            else:
                self._sync_metadata()
        except Exception as exc:
            messagebox.showerror("Cannot save", str(exc), parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save CleanroomX project",
            defaultextension=".cleanroomx.json",
            filetypes=[("CleanroomX project", "*.cleanroomx.json"), ("JSON files", "*.json")],
        )
        if not path:
            return

        destination = Path(path)
        migration_source = getattr(self, "_migration_source_path", None)
        if (
            migration_source is not None
            and destination.resolve(strict=False)
            == migration_source.resolve(strict=False)
        ):
            messagebox.showwarning(
                "Preserve legacy project",
                (
                    "A migrated legacy project must be saved to a different file first. "
                    "The original legacy file is preserved so the pre-migration source "
                    "remains available for rollback or comparison."
                ),
                parent=self.root,
            )
            return

        recovery_source = getattr(self, "_recovery_source_path", None)
        restored_artifact = getattr(self, "_restored_recovery_artifact", None)
        if (
            restored_artifact is not None
            and recovery_source is not None
            and destination.resolve(strict=False)
            == recovery_source.resolve(strict=False)
        ):
            messagebox.showwarning(
                "Choose a different recovery file",
                (
                    "Recovered work must be saved to a different file first. "
                    "The original project is preserved so both versions remain "
                    "available for comparison."
                ),
                parent=self.root,
            )
            return

        try:
            self._assert_save_as_destination_safe(destination)
        except (OSError, ValueError) as exc:
            self.status_var.set("Save blocked")
            messagebox.showerror("Save blocked", str(exc), parent=self.root)
            return

        previous_base = self._base_dir()
        editor_id = self._editor_analysis_id
        candidate = copy.deepcopy(self.project)
        if (
            previous_base is not None
            and previous_base.resolve() != destination.parent.resolve()
        ):
            for analysis in candidate.analyses:
                analysis.input = rebase_analysis_file_references(
                    analysis.kind,
                    analysis.input,
                    source_base=previous_base,
                    target_base=destination.parent,
                )

        same_as_open_project = (
            self.project_path is not None
            and destination.resolve(strict=False)
            == self.project_path.resolve(strict=False)
        )
        try:
            expected_revision = (
                getattr(self, "_project_file_revision", None)
                if same_as_open_project
                else capture_project_file_revision(destination)
            )
            if expected_revision is None:
                expected_revision = capture_project_file_revision(destination)
            saved_path, saved_revision = save_project_document_guarded(
                destination,
                candidate,
                expected_revision=expected_revision,
                before_replace=self._assert_save_as_destination_safe,
            )
        except ProjectFileBusyError:
            self._report_project_save_busy(destination)
            return
        except ProjectSaveDurabilityError as exc:
            if same_as_open_project:
                self._project_file_revision = exc.committed_revision
            self._report_save_durability_uncertain(destination)
            return
        except ProjectWriteConflictError:
            self._report_external_save_conflict(destination)
            return
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self.root)
            return

        self.project = candidate
        self.project_path = saved_path
        self._project_file_revision = saved_revision
        self._recovery_source_path = None
        self._migration_source_path = None
        if previous_base is not None and self._base_dir() != previous_base:
            self._clear_run_cache()
            # History snapshots contain path-valued analysis inputs relative to the
            # previous project directory. Keeping them after a base-directory change
            # could restore strings under the wrong path context.
            self._clear_project_history()
        if editor_id is not None:
            try:
                self._load_analysis_into_editor(self.project.analysis_by_id(editor_id))
            except KeyError:
                self._refresh_analysis_list()
        self._capture_saved_state()
        self._notify_explicit_save(self.project_path)
        self._discard_restored_recovery()
        self._remember_recent_project(self.project_path)
        self.status_var.set(f"Saved {self.project_path.name}")
        self._update_title()

    def add_analysis(self) -> None:
        if self._running:
            messagebox.showwarning("Analysis running", "Abandon the current run first.")
            return
        previous = self._editor_analysis()
        if previous is not None:
            try:
                self._commit_editor(previous)
            except Exception as exc:
                messagebox.showerror(
                    "Cannot add analysis",
                    f"Fix the current analysis input before adding another analysis.\n\n{exc}",
                    parent=self.root,
                )
                return
        picker = AnalysisPicker(self.root)
        self.root.wait_window(picker)
        if picker.result is None:
            return
        kind = picker.result
        spec = ANALYSIS_SPECS[kind]
        analysis_id = f"{kind}-{uuid.uuid4().hex[:8]}"
        payload = {"name": "New Dossier"} if kind == "dossier" else {}
        analysis = AnalysisDocument(
            id=analysis_id,
            name=spec.title,
            kind=kind,
            input=payload,
        )

        def mutate() -> None:
            self.project.analyses.append(analysis)
            self.project.active_analysis_id = analysis_id
            self._editor_analysis_id = analysis_id

        try:
            self._perform_project_edit(f"Add analysis {analysis.name}", mutate)
        except Exception as exc:
            messagebox.showerror("Cannot add analysis", str(exc), parent=self.root)
            return
        self._refresh_analysis_list(select_id=analysis_id)
        self._update_title()

    def rename_analysis(self) -> None:
        if self._running:
            messagebox.showwarning("Analysis running", "Abandon the current run first.")
            return
        analysis = self._current_analysis()
        if analysis is None:
            return
        value = simpledialog.askstring(
            "Rename analysis", "Analysis name", initialvalue=analysis.name, parent=self.root
        )
        if value and value.strip():
            new_name = value.strip()
            try:
                self._perform_project_edit(
                    f"Rename analysis {analysis.name}",
                    lambda: setattr(analysis, "name", new_name),
                )
            except Exception as exc:
                messagebox.showerror("Cannot rename analysis", str(exc), parent=self.root)
                return
            self.analysis_tree.item(analysis.id, text=analysis.name)
            self._update_title()

    def remove_analysis(self) -> None:
        if self._running:
            messagebox.showwarning("Analysis running", "Abandon the current run first.")
            return
        analysis = self._current_analysis()
        if analysis is None:
            return
        if not messagebox.askyesno(
            "Remove analysis",
            f"Remove {analysis.name!r} from this project?",
            parent=self.root,
        ):
            return
        def mutate() -> None:
            self.project.analyses = [
                item for item in self.project.analyses if item.id != analysis.id
            ]
            self.project.active_analysis_id = (
                self.project.analyses[0].id if self.project.analyses else None
            )
            self._editor_analysis_id = self.project.active_analysis_id

        try:
            self._perform_project_edit(f"Remove analysis {analysis.name}", mutate)
        except Exception as exc:
            messagebox.showerror("Cannot remove analysis", str(exc), parent=self.root)
            return
        self._invalidate_last_run_for(analysis.id)
        self._refresh_analysis_list()
        self._update_title()

    def import_input_json(self) -> None:
        if self._running:
            messagebox.showwarning("Analysis running", "Abandon the current run first.")
            return
        analysis = self._current_analysis()
        if analysis is None:
            messagebox.showinfo("No analysis", "Add or select an analysis first.")
            return
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Import analysis input JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        source_path = Path(path)
        try:
            payload = load_strict_json(
                source_path,
                max_bytes=STRICT_JSON_FILE_MAX_BYTES,
            )
            if not isinstance(payload, dict):
                raise ValueError("input file must contain a JSON object")
            payload = rebase_analysis_file_references(
                analysis.kind,
                payload,
                source_base=source_path.parent,
                target_base=self._base_dir(),
            )
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc), parent=self.root)
            return
        try:
            self._perform_project_edit(
                f"Import input for {analysis.name}",
                lambda: setattr(analysis, "input", payload),
            )
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc), parent=self.root)
            return
        self._invalidate_last_run_for(analysis.id)
        self._load_analysis_into_editor(analysis)
        self.status_var.set(f"Imported {source_path.name}")
        self._update_title()

    def _write_export_file(
        self,
        path: str,
        content: str,
        *,
        label: str,
        before_replace=None,
    ) -> bool:
        target = Path(path)
        try:
            project = getattr(self, "project", None)
            source = getattr(self, "project_path", None)
            if source is None:
                source = getattr(self, "_recovery_source_path", None)

            protect_current_project_inputs = None
            if project is not None:
                if source is not None:
                    source_path = Path(source)

                    def protect_current_project_inputs() -> None:
                        _assert_project_output_is_safe(
                            project,
                            source=source_path,
                            output=target,
                        )
                else:

                    def protect_current_project_inputs() -> None:
                        for analysis in project.analyses:
                            for field, declared_path in (
                                analysis_external_dependency_references(
                                    analysis.kind,
                                    analysis.input,
                                )
                            ):
                                dependency = Path(declared_path).expanduser()
                                if not dependency.is_absolute():
                                    continue
                                if _paths_alias(dependency, target):
                                    raise ValueError(
                                        "export output path must be different from "
                                        "external dependency "
                                        f"{field!r} for analysis {analysis.id!r}: "
                                        f"{dependency.resolve(strict=False)}"
                                    )

                # Reject an already-dangerous selection before creating a
                # staged file, then repeat the same check at publication time.
                # Unsaved projects have no canonical base directory, so only
                # absolute file-backed dependencies can be protected there.
                protect_current_project_inputs()

            effective_before_replace = before_replace
            if (
                protect_current_project_inputs is not None
                and before_replace is not None
            ):

                def protect_then_validate_caller() -> None:
                    protect_current_project_inputs()
                    before_replace()

                effective_before_replace = protect_then_validate_caller
            elif protect_current_project_inputs is not None:
                effective_before_replace = protect_current_project_inputs

            if effective_before_replace is None:
                atomic_write_text(target, content)
            else:
                atomic_write_text(
                    target,
                    content,
                    before_replace=effective_before_replace,
                )
        except Exception as exc:
            self.status_var.set(f"{label} export failed")
            messagebox.showerror(
                f"{label} export failed",
                str(exc),
                parent=self.root,
            )
            return False
        self.status_var.set(f"Exported {label.lower()} — {target.name}")
        return True

    def export_input_json(self) -> None:
        try:
            analysis = self._commit_editor()
        except Exception as exc:
            messagebox.showerror("Cannot export", str(exc), parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if path:
            self._write_export_file(
                path,
                json.dumps(
                    analysis.input, indent=2, ensure_ascii=False, allow_nan=False
                ) + "\n",
                label="Input",
            )

    def validate_current(self) -> None:
        try:
            analysis = self._commit_editor()
            validate_analysis_input(analysis.kind, analysis.input, base_dir=self._base_dir())
        except Exception as exc:
            self.status_var.set("Validation failed")
            messagebox.showerror("Validation failed", str(exc), parent=self.root)
            return
        self.refresh_structure(silent=True)
        self.status_var.set(f"Input valid — {analysis.name}")
        messagebox.showinfo("Validation", "Input is valid for the selected backend workflow.")

    def _on_task_center_change(self, active: int, total: int) -> None:
        if active:
            self.task_status_var.set(f"Tasks: {active} active · {total} session")
        elif total:
            self.task_status_var.set(f"Tasks: idle · {total} session")
        else:
            self.task_status_var.set("Tasks: idle")

    def _abandon_task_from_center(self, task_key: str) -> bool:
        if (
            task_key != getattr(self, "_active_run_task_id", None)
            or not self._running
            or self._abandon_requested
        ):
            self.status_var.set("Selected task cannot be abandoned")
            return False
        self.cancel_run()
        return bool(self._abandon_requested)

    def show_task_center(self) -> None:
        self._restore_focus_workspace_snapshot(status=False)
        self.output_panel_visible_var.set(True)
        self._sync_output_panel_visibility()
        panel = getattr(self, "task_center", None)
        notebook = getattr(self, "output_notebook", None)
        if panel is not None and notebook is not None:
            notebook.select(panel)
        self.status_var.set("Output: Job / Task Center")

    def _current_run_elapsed_seconds(self) -> float | None:
        started = getattr(self, "_run_started_monotonic", None)
        if started is None:
            return None
        return max(0.0, time.monotonic() - started)

    def _update_active_run_task(self, **changes) -> None:
        center = getattr(self, "task_center", None)
        task_id = getattr(self, "_active_run_task_id", None)
        if center is None or not task_id:
            return
        center.update_task(task_id, **changes)

    def _finish_active_run_task(
        self,
        *,
        state: str,
        stage: str,
        result: str = "",
        detail: str = "",
    ) -> None:
        self._update_active_run_task(
            state=state,
            stage=stage,
            duration_seconds=self._current_run_elapsed_seconds(),
            result=result,
            detail=detail,
        )
        self._active_run_task_id = None
        self._run_started_monotonic = None

    def run_current(self) -> None:
        if self._running:
            return
        try:
            analysis = self._commit_editor()
            validate_analysis_input(analysis.kind, analysis.input, base_dir=self._base_dir())
        except Exception as exc:
            self.status_var.set("Cannot run — invalid input")
            simulation = getattr(self, "simulation_workspace", None)
            if simulation is not None:
                simulation.set_blocked(
                    "Input validation failed; the backend solver was not started."
                )
            messagebox.showerror("Cannot run analysis", str(exc), parent=self.root)
            return

        self._run_generation += 1
        generation = self._run_generation
        analysis_id = analysis.id
        kind = analysis.kind
        payload = copy.deepcopy(analysis.input)
        base_dir = self._base_dir()
        self._abandon_requested = False
        self._run_started_monotonic = time.monotonic()
        self._active_run_task_id = f"analysis:{generation}"
        task_center = getattr(self, "task_center", None)
        if task_center is not None:
            task_center.start_task(
                self._active_run_task_id,
                analysis.name,
                category="Analysis",
                stage=f"Executing {ANALYSIS_SPECS[analysis.kind].title}",
            )
        self._set_running(True)
        simulation = getattr(self, "simulation_workspace", None)
        if simulation is not None:
            simulation.set_context(
                analysis_name=analysis.name,
                analysis_kind=analysis.kind,
                analysis_input=analysis.input,
                last_run=self._runs_by_analysis.get(analysis.id),
                running=True,
            )
        self.status_var.set(f"Running {analysis.name}...")

        def worker() -> None:
            try:
                result = run_analysis(kind, payload, base_dir=base_dir)
            except Exception as exc:
                self._queue.put(("error", generation, analysis_id, str(exc)))
                return

            self._queue.put(
                ("stage", generation, analysis_id, "Finalizing run-history evidence")
            )
            history_evidence = None
            history_error = None
            try:
                history_evidence = build_run_history_evidence(payload, result)
            except Exception as exc:  # audit preparation must not hide a valid result
                history_error = str(exc)
            self._queue.put(
                (
                    "success",
                    generation,
                    analysis_id,
                    (result, history_evidence, history_error),
                )
            )

        threading.Thread(target=worker, daemon=True).start()

    def cancel_run(self) -> None:
        if not self._running or self._abandon_requested:
            return
        self._abandon_requested = True
        self.cancel_button.configure(state="disabled")
        simulation = getattr(self, "simulation_workspace", None)
        if simulation is not None:
            simulation.set_abandon_requested()
        self._update_active_run_task(
            state="abandon requested",
            stage="Waiting for backend worker to exit",
            duration_seconds=self._current_run_elapsed_seconds(),
            result="Pending result suppressed",
            detail=(
                "Abandon does not force-terminate the backend thread. "
                "The workstation remains exclusive until the worker exits."
            ),
        )
        self.status_var.set(
            "Run abandoned in the UI; waiting for the backend worker to finish before another run."
        )

    def _set_running(self, running: bool) -> None:
        self._running = running
        self.run_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")
        self.input_text.configure(state="disabled" if running else "normal")

    def _poll_worker(self) -> None:
        try:
            while True:
                kind, generation, analysis_id, payload = self._queue.get_nowait()
                if generation != self._run_generation:
                    continue
                if kind == "stage":
                    if not self._abandon_requested:
                        self._update_active_run_task(
                            state="finalizing",
                            stage=str(payload),
                            duration_seconds=self._current_run_elapsed_seconds(),
                        )
                    continue
                if self._abandon_requested:
                    self._abandon_requested = False
                    self._set_running(False)
                    simulation = getattr(self, "simulation_workspace", None)
                    if simulation is not None:
                        simulation.set_abandoned()
                    self._finish_active_run_task(
                        state="abandoned",
                        stage="Backend worker finished; result suppressed",
                        result="Suppressed",
                        detail="The operator abandoned this run before its pending result was accepted.",
                    )
                    self.status_var.set("Run abandoned; backend worker finished. Ready.")
                    continue
                self._set_running(False)
                if kind == "error":
                    simulation = getattr(self, "simulation_workspace", None)
                    if simulation is not None:
                        simulation.set_failed(str(payload))
                    self._finish_active_run_task(
                        state="failed",
                        stage="Backend execution failed",
                        result="Execution error",
                        detail=str(payload),
                    )
                    self.status_var.set("Analysis failed")
                    messagebox.showerror("Analysis failed", str(payload), parent=self.root)
                else:
                    history_evidence = None
                    history_error = None
                    run = payload
                    if (
                        isinstance(payload, tuple)
                        and len(payload) == 3
                        and isinstance(payload[0], AnalysisRun)
                    ):
                        run, history_evidence, history_error = payload

                    try:
                        analysis = self.project.analysis_by_id(analysis_id)
                    except KeyError:
                        self._invalidate_last_run_for(analysis_id)
                        simulation = getattr(self, "simulation_workspace", None)
                        if simulation is not None:
                            simulation.set_discarded(
                                "Completed result discarded because the analysis no longer exists."
                            )
                        self._finish_active_run_task(
                            state="discarded",
                            stage="Completed result rejected",
                            result="No retained result",
                            detail="The analysis no longer exists in the current project.",
                        )
                        self.status_var.set(
                            "Completed result discarded — the analysis no longer exists."
                        )
                        continue
                    if not analysis_run_is_current(
            run, analysis.kind, analysis.input, base_dir=self._base_dir()
        ):
                        self._invalidate_last_run_for(analysis_id)
                        simulation = getattr(self, "simulation_workspace", None)
                        if simulation is not None:
                            simulation.set_discarded(
                                "Completed result discarded because the active inputs changed."
                            )
                        self._finish_active_run_task(
                            state="discarded",
                            stage="Completed result rejected",
                            result="Stale result",
                            detail=(
                                "The analysis inputs changed before completion, so the "
                                "completed backend result was not accepted."
                            ),
                        )
                        self.status_var.set(
                            f"Completed result discarded — {analysis.name} inputs changed; "
                            "run the analysis again."
                        )
                        continue

                    if history_error is None:
                        try:
                            self._record_completed_run(
                                analysis, run, history_evidence
                            )
                        except RunHistoryIntegrityError as exc:
                            history_error = str(exc)

                    self._runs_by_analysis[analysis_id] = run
                    self.last_run = run
                    self.last_run_analysis_id = analysis_id
                    self._render_run(run)
                    if history_error is None:
                        self._finish_active_run_task(
                            state="completed",
                            stage="Result accepted into current session",
                            result=str(run.status or "completed").upper(),
                            detail=(
                                "Execution completed. Engineering/result status is "
                                "reported separately from task execution state."
                            ),
                        )
                        self.status_var.set(
                            f"Completed — {run.title} — status: {run.status}"
                        )
                    else:
                        self._finish_active_run_task(
                            state="completed",
                            stage="Result accepted; audit history not updated",
                            result=str(run.status or "completed").upper(),
                            detail=str(history_error),
                        )
                        self.status_var.set(
                            f"Completed — {run.title}; run history was not updated."
                        )
                        messagebox.showwarning(
                            "Run history not updated",
                            (
                                "The analysis completed and its result is available, but "
                                "CleanroomX did not append an audit record because run-history "
                                "evidence could not be prepared or the existing history failed "
                                "integrity validation. Existing history was left unchanged. "
                                "Export the run bundle if this result must be retained.\n\n"
                                f"{history_error}"
                            ),
                            parent=self.root,
                        )
        except queue.Empty:
            pass
        self.root.after(100, self._poll_worker)

    def _render_run(self, run: AnalysisRun, *, select_results: bool = True) -> None:
        if hasattr(self, "simulation_workspace"):
            self.simulation_workspace.set_completed(run)
        self._set_text(
            self.result_text,
            json.dumps(run.result, indent=2, ensure_ascii=False, allow_nan=False),
        )
        self._set_text(self.report_text, run.markdown)
        self._set_text(
            self.diagnostics_text,
            json.dumps(run.diagnostics, indent=2, ensure_ascii=False, allow_nan=False),
        )
        self._draw_plot()
        if hasattr(self, "spatial_workspace"):
            self.spatial_workspace.redraw()
            self.spatial_workspace._load_property_panel()
        self._refresh_engineering_panels()
        if select_results:
            self.output_notebook.select(self.result_text.master)

    def _draw_plot(self) -> None:
        canvas = self.plot_canvas
        canvas.delete("all")
        palette = getattr(
            self,
            "_theme_palette",
            {
                "plot": "#ffffff",
                "muted": "#5f6b78",
                "text": "#18212b",
                "accent": "#0b6aa8",
                "accent_hover": "#095786",
            },
        )
        canvas.configure(background=palette["plot"])
        run = self.last_run
        if run is None or run.plot is None:
            canvas.create_text(
                max(canvas.winfo_width() / 2, 150),
                max(canvas.winfo_height() / 2, 100),
                text="No plot is available for the selected result.",
                fill=palette["muted"],
            )
            return
        plot = run.plot
        width = max(canvas.winfo_width(), 500)
        height = max(canvas.winfo_height(), 350)
        left, right, top, bottom = 70, 30, 45, 60
        xs = [x for series in plot["series"] for x in series["x"]]
        ys = [y for series in plot["series"] for y in series["y"]]
        xs += [m["x"] for m in plot.get("markers", [])]
        ys += [m["y"] for m in plot.get("markers", [])]
        if not xs or not ys:
            return
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        if xmax == xmin:
            xmax = xmin + 1.0
        if ymax == ymin:
            ymax = ymin + 1.0
        xpad = (xmax - xmin) * 0.05
        ypad = (ymax - ymin) * 0.08
        xmin, xmax = xmin - xpad, xmax + xpad
        ymin, ymax = ymin - ypad, ymax + ypad

        def point(x, y):
            px = left + (x - xmin) / (xmax - xmin) * (width - left - right)
            py = height - bottom - (y - ymin) / (ymax - ymin) * (height - top - bottom)
            return px, py

        axis = palette["muted"]
        text_color = palette["text"]
        series_color = palette["accent"]
        canvas.create_line(left, height - bottom, width - right, height - bottom, fill=axis)
        canvas.create_line(left, top, left, height - bottom, fill=axis)
        canvas.create_text(width / 2, 18, text=plot["title"], font=("TkDefaultFont", 11, "bold"), fill=text_color)
        canvas.create_text(width / 2, height - 20, text=plot["x_label"], fill=text_color)
        canvas.create_text(18, height / 2, text=plot["y_label"], angle=90, fill=text_color)
        canvas.create_text(left, height - bottom + 18, text=f"{xmin:.3g}", anchor="n", fill=axis)
        canvas.create_text(width - right, height - bottom + 18, text=f"{xmax:.3g}", anchor="n", fill=axis)
        canvas.create_text(left - 8, height - bottom, text=f"{ymin:.3g}", anchor="e", fill=axis)
        canvas.create_text(left - 8, top, text=f"{ymax:.3g}", anchor="e", fill=axis)

        for index, series in enumerate(plot["series"]):
            coords = []
            for x, y in zip(series["x"], series["y"]):
                coords.extend(point(x, y))
            line_options = {"width": 2, "fill": series_color}
            if index % 2:
                line_options["dash"] = (6, 4)
            if len(coords) >= 4:
                canvas.create_line(*coords, **line_options)
            for x, y in zip(series["x"], series["y"]):
                px, py = point(x, y)
                canvas.create_oval(
                    px - 2, py - 2, px + 2, py + 2,
                    fill=series_color,
                    outline=series_color,
                )

            legend_x = max(left + 20, width - right - 170)
            legend_y = top + index * 18
            canvas.create_line(
                legend_x,
                legend_y,
                legend_x + 28,
                legend_y,
                **line_options,
            )
            canvas.create_text(
                legend_x + 34,
                legend_y,
                text=series.get("name", f"Series {index + 1}"),
                anchor="w",
                fill=text_color,
            )

        for marker in plot.get("markers", []):
            px, py = point(marker["x"], marker["y"])
            canvas.create_oval(
                px - 6, py - 6, px + 6, py + 6,
                width=2,
                outline=palette["accent_hover"],
            )
            canvas.create_text(
                px + 8, py - 8,
                text=marker["name"],
                anchor="sw",
                fill=text_color,
            )

    def export_result_json(self) -> None:
        run = self._current_fresh_run()
        if run is None:
            messagebox.showinfo(
                "No current result",
                "Run the current analysis before exporting a result.",
                parent=self.root,
            )
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if path:
            self._write_export_file(
                path,
                json.dumps(
                    run.result, indent=2, ensure_ascii=False, allow_nan=False
                ) + "\n",
                label="Result",
            )

    def export_run_bundle_json(self) -> None:
        run = self._current_fresh_run()
        if run is None:
            messagebox.showinfo(
                "No current result",
                "Run the current analysis before exporting a run bundle.",
                parent=self.root,
            )
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if path:
            self._write_export_file(
                path,
                json.dumps(
                    run.to_dict(),
                    indent=2,
                    ensure_ascii=False,
                    allow_nan=False,
                ) + "\n",
                label="Run bundle",
            )

    def export_report_markdown(self) -> None:
        run = self._current_fresh_run()
        if run is None:
            messagebox.showinfo(
                "No current report",
                "Run the current analysis before exporting a report.",
                parent=self.root,
            )
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".md",
            filetypes=[("Markdown files", "*.md"), ("Text files", "*.txt")],
        )
        if path:
            self._write_export_file(path, run.markdown, label="Report")

    def export_report_html(self) -> None:
        run = self._current_fresh_run()
        if run is None:
            messagebox.showinfo(
                "No current report",
                "Run the current analysis before exporting a portable report.",
                parent=self.root,
            )
            return
        analysis_id = self.last_run_analysis_id
        if analysis_id is None:
            return
        try:
            analysis = self.project.analysis_by_id(analysis_id)
            document = engineering_report_html(
                run,
                project_name=self.project.name,
                project_description=self.project.description,
                analysis_id=analysis.id,
                analysis_name=analysis.name,
                analysis_kind=analysis.kind,
                input_payload=analysis.input,
                base_dir=self._base_dir(),
            )
        except (KeyError, TypeError, ValueError) as exc:
            self.status_var.set("HTML report export failed")
            messagebox.showerror(
                "HTML report export failed",
                str(exc),
                parent=self.root,
            )
            return

        path = filedialog.asksaveasfilename(
            parent=self.root,
            defaultextension=".html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
        )
        if path:
            self._write_export_file(
                path,
                document,
                label="HTML report",
            )

    def show_about(self) -> None:
        messagebox.showinfo(
            "About CleanroomX",
            (
                f"CleanroomX {__version__}\n\n"
                f"{len(ANALYSIS_SPECS)} backend workflows are available through the application layer.\n\n"
                "CleanroomX provides engineering screening and numerical/provenance evidence. "
                "It does not by itself establish cleanroom certification, CFD validation, "
                "commissioning/TAB acceptance, manufacturer approval, or regulatory compliance."
            ),
            parent=self.root,
        )

    def smoke_run_active(self) -> AnalysisRun:
        analysis = self._current_analysis()
        if analysis is None:
            raise ValueError("smoke project has no active analysis")
        run = run_analysis(analysis.kind, analysis.input, base_dir=self._base_dir())
        self._runs_by_analysis[analysis.id] = run
        self.last_run = run
        self.last_run_analysis_id = analysis.id
        self._render_run(run)
        return run

    def _on_close(self) -> None:
        if self._running and not messagebox.askyesno(
            "Analysis running",
            "A backend analysis is still running. Close CleanroomX anyway?",
            parent=self.root,
        ):
            return
        if not self._confirm_project_replacement():
            return
        self._save_ui_layout_state()
        self._discard_current_autosave()
        manager = getattr(self, "_autosave_manager", None)
        if manager is not None:
            manager.shutdown(wait=False)
        self.root.destroy()


def bundled_demo_project_path() -> Path:
    """Return the self-contained demonstration project shipped in the package."""
    path = Path(__file__).resolve().parent / "demo" / "gui_demo.cleanroomx.json"
    if not path.is_file():
        raise FileNotFoundError(f"bundled CleanroomX demo is missing: {path}")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-gui",
        description="CleanroomX desktop engineering application",
    )
    parser.add_argument("project", nargs="?", help="Optional CleanroomX project file to open")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Open the self-contained demonstration project bundled with CleanroomX",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate GUI/application imports and print capability information without opening a window",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Open the real Tk GUI, optionally load a project, run its active analysis, then exit",
    )
    parser.add_argument(
        "--autosave-interval-seconds",
        type=float,
        default=DEFAULT_AUTOSAVE_INTERVAL_SECONDS,
        help=(
            "Recovery autosave interval in seconds; use 0 to disable "
            f"(default: {DEFAULT_AUTOSAVE_INTERVAL_SECONDS:g})"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo and args.project:
        parser.error("project path and --demo cannot be used together")
    if args.autosave_interval_seconds < 0:
        parser.error("--autosave-interval-seconds must be zero or greater")
    if args.check:
        print(json.dumps(application_info(), indent=2, ensure_ascii=False))
        return 0

    registry = validate_application_registry()
    project_path = bundled_demo_project_path() if args.demo else args.project

    root = tk.Tk()
    app = CleanroomXApp(
        root,
        autosave_interval_seconds=args.autosave_interval_seconds,
    )
    if not args.smoke and registry["plugin_issue_count"]:
        issues = registry["plugin_issues"]
        lines = [
            f"{item['entry_point_name'] or '<unnamed>'}: {item['error']}"
            for item in issues[:8]
        ]
        if len(issues) > 8:
            lines.append(f"... and {len(issues) - 8} more issue(s)")
        messagebox.showwarning(
            "CleanroomX plugin issues",
            "Some installed analysis plugins were disabled. Built-in workflows "
            "remain available.\n\n" + "\n".join(lines)
            + "\n\nRun cleanroomx-gui --check for machine-readable details.",
            parent=root,
        )
    recovered_at_startup = False
    if not args.smoke:
        recovered_at_startup = app.offer_startup_recovery()

    if project_path and not recovered_at_startup:
        try:
            app.load_project_path(project_path)
        except Exception as exc:
            if args.smoke:
                root.destroy()
                print(f"CleanroomX GUI smoke: FAIL — {exc}")
                return 2
            messagebox.showerror("Open failed", str(exc), parent=root)

    if args.smoke:
        try:
            if project_path and app.project.analyses:
                run = app.smoke_run_active()
                json.dumps(run.to_dict(), allow_nan=False)
            root.update_idletasks()
            root.update()
            if args.demo:
                layout = app.spatial_workspace.layout
                if len(layout.get("rooms", [])) < 3:
                    raise RuntimeError("packaged demo spatial layout did not load")
                if not app.spatial_workspace.canvas_2d.find_withtag("room"):
                    raise RuntimeError("2D layout did not render demo rooms")
                if not app.spatial_workspace.canvas_3d.find_withtag("room3d"):
                    raise RuntimeError("3D viewer did not render demo rooms")
                if not app.spatial_workspace.canvas_2d.find_withtag("pressure_relationship"):
                    raise RuntimeError("2D pressure-cascade relationships did not render")
                if not app.spatial_workspace.canvas_3d.find_withtag("pressure_relationship_3d"):
                    raise RuntimeError("3D pressure-cascade relationships did not render")
        except Exception as exc:
            root.destroy()
            print(f"CleanroomX GUI smoke: FAIL — {exc}")
            return 2
        root.destroy()
        print("CleanroomX GUI smoke: PASS")
        return 0

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
