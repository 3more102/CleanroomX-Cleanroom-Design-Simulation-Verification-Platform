from __future__ import annotations

from typing import Any, Callable
import json

import tkinter as tk
from tkinter import ttk

from .proofgraph_io import proofgraph_from_dict


def diagnostic_issue_rows(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Project the canonical project-diagnostics report into stable GUI rows."""
    if not isinstance(report, dict):
        return []
    issues = report.get("issues")
    if not isinstance(issues, list):
        return []

    rows: list[dict[str, Any]] = []
    for index, issue in enumerate(issues, start=1):
        if not isinstance(issue, dict):
            continue
        element = issue.get("element")
        if not isinstance(element, dict):
            element = {}
        details = issue.get("details")
        if not isinstance(details, dict):
            details = {}
        element_id = element.get("id")
        element_name = element.get("name")
        element_type = str(element.get("type") or "project")
        object_text = str(element_name or element_id or element_type)
        level = (
            details.get("level")
            or details.get("level_name")
            or details.get("floor")
            or details.get("floor_name")
            or ""
        )
        rows.append(
            {
                "sequence": int(issue.get("sequence") or index),
                "severity": str(issue.get("severity") or "info").lower(),
                "code": str(issue.get("rule") or ""),
                "description": str(issue.get("message") or ""),
                "object": object_text,
                "level": str(level),
                "source": str(issue.get("category") or ""),
                "issue": issue,
            }
        )
    return rows


def verification_rows(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Project canonical verification-currency state into GUI rows."""
    if not isinstance(report, dict):
        return []
    currency = report.get("verification_currency")
    if not isinstance(currency, dict):
        return []
    analyses = currency.get("analyses")
    if not isinstance(analyses, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in analyses:
        if not isinstance(item, dict):
            continue
        latest = item.get("latest_record")
        if not isinstance(latest, dict):
            latest = {}
        rows.append(
            {
                "analysis_id": str(item.get("analysis_id") or ""),
                "analysis_name": str(
                    item.get("analysis_name") or item.get("analysis_id") or ""
                ),
                "state": str(item.get("state") or ""),
                "current": bool(item.get("current") is True),
                "complete": bool(item.get("complete") is True),
                "latest_sequence": latest.get("sequence"),
                "latest_status": str(latest.get("status") or ""),
                "mismatch_reasons": tuple(
                    str(value)
                    for value in item.get("mismatch_reasons", [])
                    if str(value)
                ),
                "record": item,
            }
        )
    return rows


class DiagnosticsPanel(ttk.Frame):
    """IDE-style view over the canonical deterministic project diagnostics."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_navigate: Callable[[dict[str, Any]], None] | None = None,
        on_refresh: Callable[[], None] | None = None,
    ):
        super().__init__(master)
        self._on_navigate = on_navigate
        self._on_refresh = on_refresh
        self._report: dict[str, Any] | None = None
        self._rows_by_iid: dict[str, dict[str, Any]] = {}

        self.search_var = tk.StringVar()
        self.severity_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="No diagnostics loaded")

        toolbar = ttk.Frame(self, padding=(6, 5))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Search").pack(side="left")
        search = ttk.Entry(toolbar, textvariable=self.search_var, width=28)
        search.pack(side="left", padx=(5, 8))
        ttk.Label(toolbar, text="Severity").pack(side="left")
        severity = ttk.Combobox(
            toolbar,
            textvariable=self.severity_var,
            values=("All", "Error", "Warning", "Info"),
            state="readonly",
            width=10,
        )
        severity.pack(side="left", padx=(5, 8))
        if on_refresh is not None:
            ttk.Button(toolbar, text="Refresh", command=on_refresh).pack(
                side="right", padx=(4, 0)
            )
        ttk.Button(toolbar, text="Copy", command=self.copy_selected).pack(
            side="right"
        )
        ttk.Label(toolbar, textvariable=self.summary_var).pack(
            side="right", padx=(8, 12)
        )

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        columns = ("severity", "code", "description", "object", "level", "source")
        self.tree = ttk.Treeview(
            body,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        headings = {
            "severity": "Severity",
            "code": "Code",
            "description": "Description",
            "object": "Object",
            "level": "Level",
            "source": "Source",
        }
        widths = {
            "severity": 82,
            "code": 205,
            "description": 520,
            "object": 160,
            "level": 105,
            "source": 130,
        }
        for name in columns:
            self.tree.heading(name, text=headings[name])
            self.tree.column(
                name,
                width=widths[name],
                minwidth=70,
                stretch=name == "description",
            )
        yscroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(body, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self.tree.tag_configure("error", foreground="#b42318")
        self.tree.tag_configure("warning", foreground="#9a6700")
        self.tree.tag_configure("info", foreground="#57606a")
        self.tree.bind("<Double-1>", self._activate_selected)
        self.tree.bind("<Return>", self._activate_selected)
        self.search_var.trace_add("write", lambda *_: self._refresh_rows())
        self.severity_var.trace_add("write", lambda *_: self._refresh_rows())

    def clear(self) -> None:
        self._report = None
        self._rows_by_iid.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.summary_var.set("No diagnostics loaded")

    def set_error(self, message: str) -> None:
        self.clear()
        self.summary_var.set(f"Diagnostics unavailable: {message}")

    def set_report(self, report: dict[str, Any]) -> None:
        self._report = report
        self._refresh_rows()

    def _refresh_rows(self) -> None:
        rows = diagnostic_issue_rows(self._report)
        query = self.search_var.get().strip().casefold()
        severity = self.severity_var.get().strip().lower()
        if severity == "all":
            severity = ""

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._rows_by_iid.clear()

        visible = 0
        for row in rows:
            if severity and row["severity"] != severity:
                continue
            haystack = " ".join(
                str(row[key])
                for key in ("severity", "code", "description", "object", "level", "source")
            ).casefold()
            if query and query not in haystack:
                continue
            iid = f"issue:{row['sequence']}:{visible}"
            self._rows_by_iid[iid] = row
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    row["severity"].upper(),
                    row["code"],
                    row["description"],
                    row["object"],
                    row["level"],
                    row["source"],
                ),
                tags=(row["severity"],),
            )
            visible += 1

        summary = (
            self._report.get("summary", {})
            if isinstance(self._report, dict)
            else {}
        )
        total = int(summary.get("issue_count", len(rows)) or 0)
        errors = int(summary.get("error_count", 0) or 0)
        warnings = int(summary.get("warning_count", 0) or 0)
        self.summary_var.set(
            f"{visible}/{total} shown · {errors} error · {warnings} warning"
        )

    def selected_issue(self) -> dict[str, Any] | None:
        selection = self.tree.selection()
        if not selection:
            return None
        row = self._rows_by_iid.get(selection[0])
        if row is None:
            return None
        issue = row.get("issue")
        return issue if isinstance(issue, dict) else None

    def _activate_selected(self, event=None):
        issue = self.selected_issue()
        if issue is not None and self._on_navigate is not None:
            self._on_navigate(issue)
        return "break"

    def copy_selected(self) -> None:
        issue = self.selected_issue()
        if issue is None:
            return
        element = issue.get("element")
        if not isinstance(element, dict):
            element = {}
        object_text = element.get("name") or element.get("id") or element.get("type") or "project"
        text = (
            f"{str(issue.get('severity') or '').upper()} "
            f"{issue.get('rule') or ''}: {issue.get('message') or ''} "
            f"[{object_text}]"
        )
        self.clipboard_clear()
        self.clipboard_append(text)


class VerificationPanel(ttk.Frame):
    """Read-only current verification/currency view over canonical project evidence."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_navigate_analysis: Callable[[str], None] | None = None,
    ):
        super().__init__(master)
        self._on_navigate_analysis = on_navigate_analysis
        self._rows_by_iid: dict[str, dict[str, Any]] = {}
        self.summary_var = tk.StringVar(value="No verification state loaded")

        header = ttk.Frame(self, padding=(6, 5))
        header.pack(fill="x")
        ttk.Label(header, textvariable=self.summary_var).pack(side="left")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        columns = ("analysis", "state", "current", "complete", "latest", "reasons")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse")
        headings = {
            "analysis": "Analysis",
            "state": "State",
            "current": "Current",
            "complete": "Complete",
            "latest": "Latest evidence",
            "reasons": "Mismatch / notes",
        }
        widths = {
            "analysis": 220,
            "state": 145,
            "current": 85,
            "complete": 85,
            "latest": 140,
            "reasons": 460,
        }
        for name in columns:
            self.tree.heading(name, text=headings[name])
            self.tree.column(
                name,
                width=widths[name],
                minwidth=70,
                stretch=name == "reasons",
            )
        yscroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(body, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self._activate_selected)
        self.tree.bind("<Return>", self._activate_selected)

    def set_report(self, report: dict[str, Any]) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._rows_by_iid.clear()

        rows = verification_rows(report)
        for index, row in enumerate(rows):
            iid = f"verification:{index}"
            self._rows_by_iid[iid] = row
            latest = (
                f"#{row['latest_sequence']} {row['latest_status']}".strip()
                if row["latest_sequence"] is not None
                else "—"
            )
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    row["analysis_name"],
                    row["state"],
                    "Yes" if row["current"] else "No",
                    "Yes" if row["complete"] else "No",
                    latest,
                    ", ".join(row["mismatch_reasons"]) or "—",
                ),
            )

        currency = report.get("verification_currency", {}) if isinstance(report, dict) else {}
        summary = currency.get("summary", {}) if isinstance(currency, dict) else {}
        self.summary_var.set(
            "Verification currency · "
            f"{summary.get('current_count', 0)} current · "
            f"{summary.get('stale_count', 0)} stale · "
            f"{summary.get('not_verified_count', 0)} not verified"
        )

    def _activate_selected(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return "break"
        row = self._rows_by_iid.get(selection[0])
        if row is None:
            return "break"
        analysis_id = row.get("analysis_id")
        if analysis_id and self._on_navigate_analysis is not None:
            self._on_navigate_analysis(str(analysis_id))
        return "break"

class ProofGraphViewer(ttk.Frame):
    """Read-only tree and graph projection of canonical ProofGraph documents."""

    _KINDS = (
        "All",
        "Requirements",
        "Evidence",
        "Checks",
        "Findings",
        "Verdicts",
        "Runs",
        "Failures",
        "Unresolved",
    )

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_subject_navigate: Callable[[str], None] | None = None,
    ):
        super().__init__(master)
        self._on_subject_navigate = on_subject_navigate
        self._documents: list[dict[str, Any]] = []
        self._nodes: dict[str, dict[str, Any]] = {}
        self._tree_to_key: dict[str, str] = {}
        self._canvas_to_key: dict[int, str] = {}

        self.search_var = tk.StringVar()
        self.kind_var = tk.StringVar(value="All")
        self.graph_var = tk.StringVar()
        self.summary_var = tk.StringVar(value="No ProofGraph evidence loaded")

        toolbar = ttk.Frame(self, padding=(7, 5))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="PROOFGRAPH", style="CX.Section.TLabel").pack(
            side="left", padx=(0, 8)
        )
        ttk.Label(toolbar, text="Graph").pack(side="left")
        self.graph_combo = ttk.Combobox(
            toolbar,
            textvariable=self.graph_var,
            state="readonly",
            width=30,
        )
        self.graph_combo.pack(side="left", padx=(4, 8))
        self.graph_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh())
        ttk.Label(toolbar, text="Filter").pack(side="left")
        kind_combo = ttk.Combobox(
            toolbar,
            textvariable=self.kind_var,
            values=self._KINDS,
            state="readonly",
            width=12,
        )
        kind_combo.pack(side="left", padx=(4, 8))
        kind_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh())
        ttk.Label(toolbar, text="Search").pack(side="left")
        search = ttk.Entry(toolbar, textvariable=self.search_var, width=24)
        search.pack(side="left", fill="x", expand=True, padx=(4, 8))
        ttk.Label(toolbar, textvariable=self.summary_var).pack(side="right")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)

        tree_host = ttk.Frame(body)
        body.add(tree_host, weight=2)
        self.tree = ttk.Treeview(tree_host, show="tree", selectmode="browse")
        tree_scroll = ttk.Scrollbar(tree_host, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._navigate_selected)
        self.tree.bind("<Return>", self._navigate_selected)

        graph_host = ttk.Frame(body)
        body.add(graph_host, weight=5)
        self.canvas = tk.Canvas(
            graph_host,
            background="#f7f9fb",
            highlightthickness=1,
            highlightbackground="#c7d0d9",
        )
        graph_y = ttk.Scrollbar(graph_host, orient="vertical", command=self.canvas.yview)
        graph_x = ttk.Scrollbar(graph_host, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=graph_y.set, xscrollcommand=graph_x.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        graph_y.grid(row=0, column=1, sticky="ns")
        graph_x.grid(row=1, column=0, sticky="ew")
        graph_host.rowconfigure(0, weight=1)
        graph_host.columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Configure>", lambda _event: self._draw_graph())

        details_host = ttk.Frame(body, padding=(7, 0, 0, 0))
        body.add(details_host, weight=2)
        ttk.Label(
            details_host, text="DETAILS", style="CX.Section.TLabel"
        ).pack(anchor="w", pady=(0, 4))
        self.details = tk.Text(details_host, wrap="word", state="disabled", width=38)
        details_scroll = ttk.Scrollbar(
            details_host, orient="vertical", command=self.details.yview
        )
        self.details.configure(yscrollcommand=details_scroll.set)
        self.details.pack(side="left", fill="both", expand=True)
        details_scroll.pack(side="right", fill="y")

        self.search_var.trace_add("write", lambda *_: self._refresh())

    def clear(self) -> None:
        self._documents = []
        self.graph_combo.configure(values=())
        self.graph_var.set("")
        self._refresh()

    def set_documents(self, documents: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> None:
        validated: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in documents:
            graph = proofgraph_from_dict(raw)
            document = graph.to_dict()
            digest = document["graph_sha256"]
            if digest in seen:
                continue
            seen.add(digest)
            validated.append(document)
        validated.sort(key=lambda item: (item.get("id", ""), item["graph_sha256"]))
        self._documents = validated
        labels = [
            f"{item.get('id', 'ProofGraph')} · {item['graph_sha256'][:10]}"
            for item in validated
        ]
        self.graph_combo.configure(values=labels)
        if labels:
            if self.graph_var.get() not in labels:
                self.graph_var.set(labels[0])
        else:
            self.graph_var.set("")
        self._refresh()

    def _current_document(self) -> dict[str, Any] | None:
        if not self._documents:
            return None
        values = list(self.graph_combo.cget("values"))
        try:
            index = values.index(self.graph_var.get())
        except ValueError:
            index = 0
        return self._documents[index]

    @staticmethod
    def _node_label(kind: str, item: dict[str, Any]) -> str:
        if kind == "requirement":
            return str(item.get("title") or item.get("id") or "Requirement")
        if kind == "evidence":
            value = item.get("value")
            unit = item.get("unit") or ""
            rendered = f"{value} {unit}".strip() if value is not None else "missing"
            return f"{item.get('property_name') or item.get('id')} = {rendered}"
        if kind == "finding":
            return f"{str(item.get('status') or '').upper()} · {item.get('id')}"
        if kind == "verdict":
            return f"{str(item.get('status') or '').upper()} · {item.get('id')}"
        return str(item.get("id") or kind.title())

    @staticmethod
    def _status(item: dict[str, Any]) -> str:
        return str(item.get("status") or "").lower()

    def _include_node(self, node: dict[str, Any]) -> bool:
        kind_filter = self.kind_var.get()
        kind = node["kind"]
        status = self._status(node["data"])
        mapping = {
            "Requirements": {"requirement"},
            "Evidence": {"evidence"},
            "Checks": {"check"},
            "Findings": {"finding"},
            "Verdicts": {"verdict"},
            "Runs": {"run"},
        }
        if kind_filter in mapping and kind not in mapping[kind_filter]:
            return False
        if kind_filter == "Failures" and status not in {"fail", "warning"}:
            return False
        if kind_filter == "Unresolved" and status not in {
            "unknown", "indeterminate", "not_checked"
        }:
            return False
        query = self.search_var.get().strip().casefold()
        if query:
            haystack = json.dumps(
                node["data"], sort_keys=True, ensure_ascii=False, default=str
            ).casefold()
            haystack += " " + node["label"].casefold()
            if query not in haystack:
                return False
        return True

    def _build_nodes(self, document: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[tuple[str, str]]]:
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[tuple[str, str]] = []

        requirements = document.get("requirement_set", {}).get("requirements", [])
        for item in requirements:
            key = f"requirement:{item['id']}"
            nodes[key] = {
                "key": key, "kind": "requirement",
                "label": self._node_label("requirement", item), "data": item,
            }

        for item in document.get("evidence", []):
            key = f"evidence:{item['id']}"
            nodes[key] = {
                "key": key, "kind": "evidence",
                "label": self._node_label("evidence", item), "data": item,
            }

        for item in document.get("checks", []):
            key = f"check:{item['id']}"
            nodes[key] = {
                "key": key, "kind": "check",
                "label": self._node_label("check", item), "data": item,
            }
            edges.append((f"requirement:{item['requirement_id']}", key))
            for evidence_id in item.get("evidence_ids", []):
                edges.append((f"evidence:{evidence_id}", key))

        for item in document.get("findings", []):
            key = f"finding:{item['id']}"
            nodes[key] = {
                "key": key, "kind": "finding",
                "label": self._node_label("finding", item), "data": item,
            }
            edges.append((f"check:{item['check_id']}", key))

        for item in document.get("verdicts", []):
            key = f"verdict:{item['id']}"
            nodes[key] = {
                "key": key, "kind": "verdict",
                "label": self._node_label("verdict", item), "data": item,
            }
            for finding_id in item.get("finding_ids", []):
                edges.append((f"finding:{finding_id}", key))

        for item in document.get("verification_runs", []):
            key = f"run:{item['id']}"
            nodes[key] = {
                "key": key, "kind": "run",
                "label": self._node_label("run", item), "data": item,
            }
            for verdict_id in item.get("verdict_ids", []):
                edges.append((f"verdict:{verdict_id}", key))

        return nodes, edges

    def _refresh(self) -> None:
        document = self._current_document()
        self._nodes = {}
        self._tree_to_key.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        if document is None:
            self.summary_var.set("No ProofGraph evidence loaded")
            self._set_details("")
            self._draw_graph()
            return

        nodes, _edges = self._build_nodes(document)
        self._nodes = {key: value for key, value in nodes.items() if self._include_node(value)}
        groups = (
            ("requirement", "Requirements"),
            ("evidence", "Evidence"),
            ("check", "Checks / Analysis"),
            ("finding", "Findings"),
            ("verdict", "Verdicts"),
            ("run", "Verification runs"),
        )
        for kind, title in groups:
            members = [node for node in self._nodes.values() if node["kind"] == kind]
            if not members:
                continue
            root = self.tree.insert("", "end", text=f"{title} ({len(members)})", open=True)
            for node in sorted(members, key=lambda value: value["label"].casefold()):
                iid = self.tree.insert(root, "end", text=node["label"])
                self._tree_to_key[iid] = node["key"]

        verdicts = document.get("verdicts", [])
        fail_count = sum(
            str(item.get("status") or "").lower() in {"fail", "warning"}
            for item in verdicts
        )
        unresolved_count = sum(
            str(item.get("status") or "").lower()
            in {"unknown", "indeterminate", "not_checked"}
            for item in verdicts
        )
        self.summary_var.set(
            f"{len(nodes)} nodes · {len(verdicts)} verdicts · "
            f"{fail_count} adverse · {unresolved_count} unresolved"
        )
        self._draw_graph()

    def _draw_graph(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        self._canvas_to_key.clear()
        document = self._current_document()
        if document is None:
            canvas.create_text(
                max(canvas.winfo_width(), 300) / 2,
                max(canvas.winfo_height(), 180) / 2,
                text="No persisted ProofGraph documents are available.",
                fill="#667788",
            )
            return

        all_nodes, all_edges = self._build_nodes(document)
        visible = self._nodes
        columns = ["requirement", "evidence", "check", "finding", "verdict", "run"]
        x_by_kind = {
            kind: 90 + index * 205 for index, kind in enumerate(columns)
        }
        positions: dict[str, tuple[float, float]] = {}
        for kind in columns:
            members = sorted(
                (node for node in visible.values() if node["kind"] == kind),
                key=lambda value: value["label"].casefold(),
            )
            for index, node in enumerate(members):
                positions[node["key"]] = (x_by_kind[kind], 55 + index * 86)

        for source, target in all_edges:
            if source not in positions or target not in positions:
                continue
            x0, y0 = positions[source]
            x1, y1 = positions[target]
            canvas.create_line(
                x0 + 75, y0, x1 - 75, y1,
                fill="#9aa9b7", width=1, arrow="last",
            )

        for key, (x, y) in positions.items():
            node = visible[key]
            status = self._status(node["data"])
            outline = {
                "pass": "#2f855a",
                "fail": "#c53030",
                "warning": "#b7791f",
                "unknown": "#718096",
                "indeterminate": "#805ad5",
                "not_checked": "#718096",
            }.get(status, "#526577")
            rectangle = canvas.create_rectangle(
                x - 75, y - 25, x + 75, y + 25,
                fill="#ffffff", outline=outline, width=2,
                tags=(f"proofnode:{key}", "proofnode"),
            )
            text_id = canvas.create_text(
                x, y,
                text=node["label"][:38],
                width=136,
                justify="center",
                fill="#1f2937",
                tags=(f"proofnode:{key}", "proofnode"),
            )
            self._canvas_to_key[rectangle] = key
            self._canvas_to_key[text_id] = key

        width = max([x for x, _ in positions.values()], default=500) + 120
        height = max([y for _, y in positions.values()], default=250) + 70
        canvas.configure(scrollregion=(0, 0, width, height))

    def _set_details(self, text: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def _select_key(self, key: str) -> None:
        node = self._nodes.get(key)
        if node is None:
            return
        self._set_details(
            json.dumps(node["data"], indent=2, sort_keys=True, ensure_ascii=False)
        )
        for iid, mapped in self._tree_to_key.items():
            if mapped == key:
                self.tree.selection_set(iid)
                self.tree.focus(iid)
                self.tree.see(iid)
                break

    def _on_tree_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        key = self._tree_to_key.get(selection[0])
        if key:
            node = self._nodes.get(key)
            if node is not None:
                self._set_details(
                    json.dumps(node["data"], indent=2, sort_keys=True, ensure_ascii=False)
                )

    def _on_canvas_click(self, _event=None) -> None:
        current = self.canvas.find_withtag("current")
        if not current:
            return
        key = self._canvas_to_key.get(current[0])
        if key:
            self._select_key(key)

    def _navigate_selected(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return "break"
        key = self._tree_to_key.get(selection[0])
        node = self._nodes.get(key or "")
        if node is None or self._on_subject_navigate is None:
            return "break"
        data = node["data"]
        subject = data.get("subject_ref")
        if not subject and node["kind"] == "evidence":
            provenance = data.get("provenance")
            if isinstance(provenance, list):
                for item in provenance:
                    if isinstance(item, dict) and item.get("cleanroomx_entity_id"):
                        subject = item["cleanroomx_entity_id"]
                        break
        if subject:
            self._on_subject_navigate(str(subject))
        return "break"

class StartCenter(ttk.Frame):
    """Professional zero-state surface; delegates all actions to application APIs."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_new: Callable[[], None],
        on_open: Callable[[], None],
        on_import_ifc: Callable[[], None],
        on_open_demo: Callable[[], None],
    ):
        super().__init__(master, padding=(34, 30))
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)

        brand = ttk.Frame(self)
        brand.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(10, 24))
        ttk.Label(brand, text="CleanroomX", style="CX.Brand.TLabel").pack(anchor="w")
        ttk.Label(
            brand,
            text="Engineering Design • Simulation • Verification",
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            brand,
            text=(
                "Project-native cleanroom engineering with traceable analysis, "
                "verification, diagnostics, IFC semantics, and ProofGraph evidence."
            ),
            wraplength=760,
        ).pack(anchor="w", pady=(8, 0))

        actions = ttk.LabelFrame(self, text="Start", padding=18)
        actions.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        for index in range(2):
            actions.columnconfigure(index, weight=1)

        ttk.Button(
            actions,
            text="New Project",
            style="CX.Primary.TButton",
            command=on_new,
        ).grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        ttk.Button(
            actions,
            text="Open Project",
            style="CX.Primary.TButton",
            command=on_open,
        ).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(
            actions,
            text="Import IFC",
            command=on_import_ifc,
        ).grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        ttk.Button(
            actions,
            text="Open Example Project",
            command=on_open_demo,
        ).grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        capabilities = ttk.LabelFrame(self, text="Engineering workspace", padding=18)
        capabilities.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        ttk.Label(
            capabilities,
            text=(
                "2D / 3D / Split\n"
                "Project Navigator + contextual properties\n"
                "Analysis + verification overlays\n"
                "Deterministic diagnostics navigation\n"
                "ProofGraph + evidence traceability\n"
                "IFC semantic import / re-import review"
            ),
            justify="left",
        ).pack(anchor="w")

        note = ttk.LabelFrame(self, text="Authority boundary", padding=18)
        note.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(20, 0),
        )
        ttk.Label(
            note,
            text=(
                "The desktop UI presents existing CleanroomX domain results. "
                "Solver equations, requirement verdicts, diagnostic rules, "
                "project persistence, and ProofGraph validation remain owned by "
                "their canonical application/domain services."
            ),
            wraplength=900,
            justify="left",
        ).pack(anchor="w")

