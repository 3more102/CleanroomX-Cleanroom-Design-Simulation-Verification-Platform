from __future__ import annotations

import json
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import theme_palette
from .proofgraph_io import proofgraph_from_dict


_TYPE_ORDER = {
    "requirement": 0,
    "model_object": 1,
    "ifc": 1,
    "source": 2,
    "calculation": 2,
    "evidence": 3,
    "check": 4,
    "finding": 5,
    "verdict": 6,
    "verification_run": 7,
}

_NODE_TITLES = {
    "requirement": "Requirements",
    "model_object": "Model Objects",
    "ifc": "IFC",
    "source": "Evidence Sources",
    "calculation": "Calculations",
    "evidence": "Evidence",
    "check": "Checks",
    "finding": "Findings",
    "verdict": "Verdicts",
    "verification_run": "Verification Runs",
}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _node_key(node_type: str, node_id: str) -> str:
    return f"{node_type}:{node_id}"


def proofgraph_projection(document: dict[str, Any] | None) -> dict[str, Any]:
    """Project one canonical ProofGraph document into GUI-only nodes and edges.

    This is presentation logic only. It does not evaluate requirements or derive
    verdicts; statuses and relationships are read directly from the persisted graph.
    """
    if not isinstance(document, dict):
        return {"nodes": [], "edges": []}

    # Persisted ProofGraph is an evidence artifact, not display input that the GUI
    # may trust implicitly. Re-parse it through the canonical validator so digest,
    # identity, provenance, check/finding/verdict closure, and run relationships
    # are verified before anything is rendered.
    document = proofgraph_from_dict(document).to_dict()

    nodes: dict[str, dict[str, Any]] = {}
    edges: set[tuple[str, str, str]] = set()

    def add_node(
        node_type: str,
        node_id: Any,
        *,
        label: Any = None,
        status: Any = None,
        raw: Any = None,
        flags: tuple[str, ...] = (),
    ) -> str | None:
        ident = _text(node_id)
        if not ident:
            return None
        key = _node_key(node_type, ident)
        if key not in nodes:
            nodes[key] = {
                "key": key,
                "type": node_type,
                "id": ident,
                "label": _text(label) or ident,
                "status": _text(status).lower(),
                "flags": tuple(sorted(set(flags))),
                "raw": raw if isinstance(raw, dict) else {},
            }
        return key

    def add_edge(source: str | None, target: str | None, relation: str) -> None:
        if source and target and source != target:
            edges.add((source, target, relation))

    requirement_set = document.get("requirement_set")
    requirements = (
        requirement_set.get("requirements", [])
        if isinstance(requirement_set, dict)
        else []
    )
    requirement_keys: dict[str, str] = {}
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        requirement_id = _text(requirement.get("id"))
        key = add_node(
            "requirement",
            requirement_id,
            label=requirement.get("title") or requirement_id,
            raw=requirement,
        )
        if key:
            requirement_keys[requirement_id] = key

    source_keys: dict[str, str] = {}
    for source in document.get("evidence_sources", []):
        if not isinstance(source, dict):
            continue
        source_id = _text(source.get("id"))
        key = add_node(
            "source",
            source_id,
            label=source.get("reference") or source.get("kind") or source_id,
            raw=source,
            flags=("ifc",) if "ifc" in _text(source.get("kind")).casefold() else (),
        )
        if key:
            source_keys[source_id] = key

    evidence_keys: dict[str, str] = {}
    for evidence in document.get("evidence", []):
        if not isinstance(evidence, dict):
            continue
        evidence_id = _text(evidence.get("id"))
        kind = _text(evidence.get("kind")).lower()
        flags = []
        if kind == "calculation":
            flags.append("calculation")
        provenance = evidence.get("provenance", [])
        has_ifc = False
        if isinstance(provenance, list):
            has_ifc = any(
                isinstance(item, dict) and _text(item.get("ifc_global_id"))
                for item in provenance
            )
        if has_ifc:
            flags.append("ifc")
        key = add_node(
            "evidence",
            evidence_id,
            label=evidence.get("property_name") or evidence_id,
            raw=evidence,
            flags=tuple(flags),
        )
        if not key:
            continue
        evidence_keys[evidence_id] = key
        add_edge(source_keys.get(_text(evidence.get("source_id"))), key, "provides")

        subject_ref = _text(evidence.get("subject_ref"))
        if subject_ref:
            object_key = add_node(
                "model_object",
                subject_ref,
                label=subject_ref,
                raw={"subject_ref": subject_ref},
            )
            add_edge(object_key, key, "describes")

        if isinstance(provenance, list):
            for record in provenance:
                if not isinstance(record, dict):
                    continue
                entity_id = _text(record.get("cleanroomx_entity_id"))
                if entity_id:
                    object_key = add_node(
                        "model_object",
                        entity_id,
                        label=entity_id,
                        raw=record,
                    )
                    add_edge(object_key, key, "provenance")

                ifc_id = _text(record.get("ifc_global_id"))
                if ifc_id:
                    ifc_key = add_node(
                        "ifc",
                        ifc_id,
                        label=f"IFC {ifc_id}",
                        raw=record,
                        flags=("ifc",),
                    )
                    add_edge(ifc_key, key, "provenance")

                calculation = _text(record.get("originating_calculation"))
                if calculation:
                    calc_key = add_node(
                        "calculation",
                        calculation,
                        label=calculation,
                        raw=record,
                        flags=("calculation",),
                    )
                    add_edge(calc_key, key, "produces")

                upstream = record.get("upstream_evidence_ids", [])
                if isinstance(upstream, list):
                    for upstream_id in upstream:
                        upstream_key = _node_key("evidence", _text(upstream_id))
                        add_edge(upstream_key, key, "upstream")

    check_keys: dict[str, str] = {}
    for check in document.get("checks", []):
        if not isinstance(check, dict):
            continue
        check_id = _text(check.get("id"))
        key = add_node("check", check_id, label=check_id, raw=check)
        if not key:
            continue
        check_keys[check_id] = key
        add_edge(
            requirement_keys.get(_text(check.get("requirement_id"))),
            key,
            "checked_by",
        )
        evidence_ids = check.get("evidence_ids", [])
        if isinstance(evidence_ids, list):
            for evidence_id in evidence_ids:
                add_edge(
                    evidence_keys.get(_text(evidence_id)),
                    key,
                    "supports",
                )

    finding_keys: dict[str, str] = {}
    for finding in document.get("findings", []):
        if not isinstance(finding, dict):
            continue
        finding_id = _text(finding.get("id"))
        status = _text(finding.get("status")).lower()
        flags = []
        if finding.get("evidence_present") is False:
            flags.append("unresolved")
        key = add_node(
            "finding",
            finding_id,
            label=finding.get("reason") or finding_id,
            status=status,
            raw=finding,
            flags=tuple(flags),
        )
        if not key:
            continue
        finding_keys[finding_id] = key
        add_edge(check_keys.get(_text(finding.get("check_id"))), key, "produces")

    verdict_keys: dict[str, str] = {}
    for verdict in document.get("verdicts", []):
        if not isinstance(verdict, dict):
            continue
        verdict_id = _text(verdict.get("id"))
        status = _text(verdict.get("status")).lower()
        key = add_node(
            "verdict",
            verdict_id,
            label=verdict.get("reason") or verdict_id,
            status=status,
            raw=verdict,
        )
        if not key:
            continue
        verdict_keys[verdict_id] = key
        finding_ids = verdict.get("finding_ids", [])
        if isinstance(finding_ids, list):
            for finding_id in finding_ids:
                add_edge(finding_keys.get(_text(finding_id)), key, "verdict")

    for run in document.get("verification_runs", []):
        if not isinstance(run, dict):
            continue
        run_id = _text(run.get("id"))
        run_key = add_node(
            "verification_run",
            run_id,
            label=run_id,
            raw=run,
        )
        verdict_ids = run.get("verdict_ids", [])
        if isinstance(verdict_ids, list):
            for verdict_id in verdict_ids:
                add_edge(
                    verdict_keys.get(_text(verdict_id)),
                    run_key,
                    "included_in",
                )

    # Remove edges whose endpoint was not materialized. This can occur only for
    # optional upstream references in presentation input; canonical parsing remains
    # the authority for whether persisted ProofGraph is structurally valid.
    valid_keys = set(nodes)
    normalized_edges = [
        {"source": source, "target": target, "relation": relation}
        for source, target, relation in sorted(edges)
        if source in valid_keys and target in valid_keys
    ]
    ordered_nodes = sorted(
        nodes.values(),
        key=lambda node: (
            _TYPE_ORDER.get(node["type"], 99),
            node["label"].casefold(),
            node["id"],
        ),
    )
    return {"nodes": ordered_nodes, "edges": normalized_edges}


def proofgraph_summary(projection: dict[str, Any]) -> dict[str, int]:
    """Summarize persisted graph state without deriving a new engineering verdict."""
    nodes = projection.get("nodes", [])
    summary = {
        "requirements": 0,
        "evidence": 0,
        "findings": 0,
        "unresolved_evidence": 0,
        "verdict_pass": 0,
        "verdict_fail": 0,
        "verdict_not_checked": 0,
    }
    for node in nodes:
        node_type = node.get("type")
        status = _text(node.get("status")).casefold()
        flags = set(node.get("flags") or ())
        if node_type == "requirement":
            summary["requirements"] += 1
        elif node_type == "evidence":
            summary["evidence"] += 1
        elif node_type == "finding":
            summary["findings"] += 1
            if "unresolved" in flags:
                summary["unresolved_evidence"] += 1
        elif node_type == "verdict":
            if status in {"pass", "passed", "ok"}:
                summary["verdict_pass"] += 1
            elif status in {"fail", "failed", "error"}:
                summary["verdict_fail"] += 1
            else:
                summary["verdict_not_checked"] += 1
    return summary


def _search_projection(
    projection: dict[str, Any],
    query: str,
) -> dict[str, Any]:
    """Search graph presentation fields and keep one-hop traceability context."""
    term = _text(query).casefold()
    if not term:
        return projection

    nodes = projection.get("nodes", [])
    edges = projection.get("edges", [])
    matched: set[str] = set()
    for node in nodes:
        haystack = " ".join(
            (
                _text(node.get("type")),
                _text(node.get("id")),
                _text(node.get("label")),
                _text(node.get("status")),
                " ".join(str(flag) for flag in node.get("flags") or ()),
                json.dumps(
                    node.get("raw") or {},
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                ),
            )
        ).casefold()
        if term in haystack:
            matched.add(node["key"])

    expanded = set(matched)
    for edge in edges:
        if edge["source"] in matched or edge["target"] in matched:
            expanded.add(edge["source"])
            expanded.add(edge["target"])

    return {
        "nodes": [node for node in nodes if node["key"] in expanded],
        "edges": [
            edge
            for edge in edges
            if edge["source"] in expanded and edge["target"] in expanded
        ],
    }


def _filtered_projection(
    projection: dict[str, Any],
    filter_name: str,
) -> dict[str, Any]:
    filter_key = filter_name.strip().casefold()
    if filter_key in {"", "all"}:
        return projection

    nodes = projection.get("nodes", [])
    edges = projection.get("edges", [])
    matched: set[str] = set()

    for node in nodes:
        node_type = node.get("type")
        status = _text(node.get("status")).casefold()
        flags = set(node.get("flags") or ())
        include = False
        if filter_key == "requirements":
            include = node_type == "requirement"
        elif filter_key == "evidence":
            include = node_type in {"source", "evidence"}
        elif filter_key == "calculations":
            include = node_type == "calculation" or "calculation" in flags
        elif filter_key == "ifc":
            include = node_type == "ifc" or "ifc" in flags
        elif filter_key == "verification":
            include = node_type in {
                "check",
                "finding",
                "verdict",
                "verification_run",
            }
        elif filter_key == "failures":
            include = status in {"fail", "failed", "error"}
        elif filter_key == "unresolved evidence":
            include = "unresolved" in flags
        if include:
            matched.add(node["key"])

    # Keep immediate context around filtered nodes so the graph does not become
    # a collection of disconnected status boxes. For unresolved-evidence review,
    # only retain upstream context: downstream verdicts are consequences of the
    # unresolved finding, not unresolved evidence themselves.
    expanded = set(matched)
    for edge in edges:
        if filter_key == "unresolved evidence":
            if edge["target"] in matched:
                expanded.add(edge["source"])
        elif edge["source"] in matched or edge["target"] in matched:
            expanded.add(edge["source"])
            expanded.add(edge["target"])

    return {
        "nodes": [node for node in nodes if node["key"] in expanded],
        "edges": [
            edge
            for edge in edges
            if edge["source"] in expanded and edge["target"] in expanded
        ],
    }


class ProofGraphViewer(ttk.Frame):
    """Read-only tree + interactive graph view over canonical ProofGraph documents."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_navigate: Callable[[dict[str, Any]], None] | None = None,
        status_setter: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._on_navigate = on_navigate
        self._status_setter = status_setter or (lambda _message: None)
        self._documents: list[dict[str, Any]] = []
        self._projection: dict[str, Any] = {"nodes": [], "edges": []}
        self._nodes_by_key: dict[str, dict[str, Any]] = {}
        self._tree_key_by_iid: dict[str, str] = {}
        self._canvas_key_by_item: dict[int, str] = {}
        self._selected_key: str | None = None

        self.graph_var = tk.StringVar(value="")
        self.filter_var = tk.StringVar(value="All")
        self.search_var = tk.StringVar(value="")
        self.summary_var = tk.StringVar(value="No persisted ProofGraph evidence")
        self.health_var = tk.StringVar(value="No validated graph selected")

        toolbar = ttk.Frame(self, padding=(7, 5), style="CX.Toolbar.TFrame")
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Graph").pack(side="left")
        self.graph_picker = ttk.Combobox(
            toolbar,
            textvariable=self.graph_var,
            state="readonly",
            width=42,
        )
        self.graph_picker.pack(side="left", padx=(5, 10))
        ttk.Label(toolbar, text="Filter").pack(side="left")
        self.filter_picker = ttk.Combobox(
            toolbar,
            textvariable=self.filter_var,
            values=(
                "All",
                "Requirements",
                "Evidence",
                "Calculations",
                "IFC",
                "Verification",
                "Failures",
                "Unresolved Evidence",
            ),
            state="readonly",
            width=20,
        )
        self.filter_picker.pack(side="left", padx=(5, 10))
        ttk.Label(toolbar, text="Search").pack(side="left")
        self.search_entry = ttk.Entry(
            toolbar,
            textvariable=self.search_var,
            width=24,
        )
        self.search_entry.pack(side="left", padx=(5, 10))
        ttk.Button(
            toolbar,
            text="Clear",
            style="CX.Compact.TButton",
            command=lambda: self.search_var.set(""),
        ).pack(side="left")
        ttk.Label(toolbar, textvariable=self.summary_var).pack(
            side="right", padx=(10, 0)
        )
        self.graph_picker.bind("<<ComboboxSelected>>", lambda _event: self._refresh())
        self.filter_picker.bind("<<ComboboxSelected>>", lambda _event: self._refresh())
        self.search_var.trace_add("write", lambda *_: self._refresh())

        lifecycle = ttk.Frame(
            self,
            style="CX.Toolbar.TFrame",
            padding=(7, 3),
        )
        lifecycle.pack(fill="x", pady=(0, 4))
        ttk.Label(
            lifecycle,
            text="TRACEABILITY",
            style="CX.Section.TLabel",
        ).pack(side="left", padx=(0, 8))
        ttk.Label(
            lifecycle,
            text=(
                "Requirement  →  Model  →  Calculation  →  "
                "Verification  →  Evidence  →  Report"
            ),
            style="CX.Muted.TLabel",
        ).pack(side="left")
        ttk.Button(
            lifecycle,
            text="Locate selected",
            style="CX.Compact.TButton",
            command=self._navigate_selected,
        ).pack(side="right")

        health = ttk.Frame(
            self,
            style="CX.Toolbar.TFrame",
            padding=(7, 2, 7, 5),
        )
        health.pack(fill="x")
        ttk.Label(
            health,
            text="EVIDENCE / VERDICT STATE",
            style="CX.Section.TLabel",
        ).pack(side="left", padx=(0, 8))
        ttk.Label(
            health,
            textvariable=self.health_var,
            style="CX.Muted.TLabel",
        ).pack(side="left")

        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)

        tree_host = ttk.Frame(panes)
        graph_host = ttk.Frame(panes)
        detail_host = ttk.Frame(panes)
        panes.add(tree_host, weight=2)
        panes.add(graph_host, weight=5)
        panes.add(detail_host, weight=2)

        self.tree = ttk.Treeview(tree_host, show="tree", selectmode="browse")
        tree_scroll = ttk.Scrollbar(tree_host, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_selected)
        self.tree.bind("<Double-1>", self._navigate_selected)
        self.tree.bind("<Return>", self._navigate_selected)

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
        self.canvas.bind("<Button-1>", self._on_canvas_selected)
        self.canvas.bind("<Double-1>", self._navigate_selected)
        self.canvas.bind("<Configure>", lambda _event: self._draw_graph())

        detail_header = ttk.Frame(
            detail_host,
            style="CX.PanelHeader.TFrame",
        )
        detail_header.pack(fill="x", padx=4, pady=(4, 3))
        ttk.Label(
            detail_header,
            text="TRACEABILITY INSPECTOR",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Button(
            detail_header,
            text="Locate",
            style="CX.Compact.TButton",
            command=self._navigate_selected,
        ).pack(side="right")

        self.detail_notebook = ttk.Notebook(detail_host)
        self.detail_notebook.pack(fill="both", expand=True, padx=4, pady=(0, 5))

        summary_tab = ttk.Frame(self.detail_notebook)
        technical_tab = ttk.Frame(self.detail_notebook)
        self.detail_notebook.add(summary_tab, text="Summary")
        self.detail_notebook.add(technical_tab, text="Technical JSON")

        self.summary_detail = tk.Text(
            summary_tab,
            wrap="word",
            state="disabled",
            borderwidth=0,
        )
        summary_scroll = ttk.Scrollbar(
            summary_tab,
            orient="vertical",
            command=self.summary_detail.yview,
        )
        self.summary_detail.configure(yscrollcommand=summary_scroll.set)
        self.summary_detail.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(5, 0),
            pady=4,
        )
        summary_scroll.pack(side="right", fill="y", pady=4)

        self.technical_detail = tk.Text(
            technical_tab,
            wrap="none",
            state="disabled",
            borderwidth=0,
        )
        technical_y = ttk.Scrollbar(
            technical_tab,
            orient="vertical",
            command=self.technical_detail.yview,
        )
        technical_x = ttk.Scrollbar(
            technical_tab,
            orient="horizontal",
            command=self.technical_detail.xview,
        )
        self.technical_detail.configure(
            yscrollcommand=technical_y.set,
            xscrollcommand=technical_x.set,
        )
        self.technical_detail.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(5, 0),
            pady=4,
        )
        technical_y.grid(row=0, column=1, sticky="ns", pady=4)
        technical_x.grid(row=1, column=0, sticky="ew", padx=(5, 0))
        technical_tab.rowconfigure(0, weight=1)
        technical_tab.columnconfigure(0, weight=1)

        # Compatibility handle retained for callers that previously themed detail.
        self.detail = self.summary_detail

    def set_documents(self, documents: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> None:
        unique: dict[str, dict[str, Any]] = {}
        for document in documents:
            if not isinstance(document, dict):
                continue
            canonical = proofgraph_from_dict(document).to_dict()
            digest = _text(canonical.get("graph_sha256"))
            graph_id = _text(canonical.get("id"))
            key = digest or graph_id
            if key and key not in unique:
                unique[key] = canonical
        self._documents = list(unique.values())
        labels = [self._document_label(document) for document in self._documents]
        self.graph_picker.configure(values=labels)
        if labels:
            if self.graph_var.get() not in labels:
                self.graph_var.set(labels[0])
        else:
            self.graph_var.set("")
        self._refresh()

    @staticmethod
    def _document_label(document: dict[str, Any]) -> str:
        graph_id = _text(document.get("id")) or "ProofGraph"
        digest = _text(document.get("graph_sha256"))
        return f"{graph_id} · {digest[:10]}" if digest else graph_id

    def _active_document(self) -> dict[str, Any] | None:
        label = self.graph_var.get()
        for document in self._documents:
            if self._document_label(document) == label:
                return document
        return self._documents[0] if self._documents else None

    def _refresh(self) -> None:
        projection = proofgraph_projection(self._active_document())
        filtered = _filtered_projection(projection, self.filter_var.get())
        self._projection = _search_projection(filtered, self.search_var.get())
        self._nodes_by_key = {
            node["key"]: node for node in self._projection.get("nodes", [])
        }
        if self._selected_key not in self._nodes_by_key:
            self._selected_key = None
        self._populate_tree()
        self._draw_graph()
        self._show_selected_detail()

        all_nodes = projection.get("nodes", [])
        shown = self._projection.get("nodes", [])
        self.summary_var.set(
            f"{len(shown)}/{len(all_nodes)} nodes · "
            f"{len(self._projection.get('edges', []))} links"
            if all_nodes
            else "No persisted ProofGraph evidence"
        )
        summary = proofgraph_summary(projection)
        if all_nodes:
            self.health_var.set(
                "{requirements} requirements · {evidence} evidence · "
                "{unresolved_evidence} missing-evidence finding(s) · "
                "verdicts {verdict_pass} pass / {verdict_fail} fail / "
                "{verdict_not_checked} not checked".format(**summary)
            )
        else:
            self.health_var.set("No validated graph selected")

    def _populate_tree(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._tree_key_by_iid.clear()

        groups: dict[str, str] = {}
        for node in self._projection.get("nodes", []):
            node_type = node["type"]
            if node_type not in groups:
                iid = f"group:{node_type}"
                groups[node_type] = iid
                self.tree.insert(
                    "",
                    "end",
                    iid=iid,
                    text=_NODE_TITLES.get(node_type, node_type.replace("_", " ").title()),
                    open=True,
                    tags=("group",),
                )
            iid = f"node:{len(self._tree_key_by_iid)}"
            suffix = f" [{node['status'].upper()}]" if node.get("status") else ""
            status_tag = (
                f"status:{node['status'].casefold()}"
                if node.get("status")
                else "status:unknown"
            )
            self.tree.insert(
                groups[node_type],
                "end",
                iid=iid,
                text=f"{node['label']}{suffix}",
                tags=(f"type:{node_type}", status_tag),
            )
            self._tree_key_by_iid[iid] = node["key"]
            if node["key"] == self._selected_key:
                self.tree.selection_set(iid)
                self.tree.see(iid)

    def _node_fill(self, node: dict[str, Any]) -> str:
        status = _text(node.get("status")).casefold()
        dark = self._theme_palette["background"].upper() == "#0B1220"
        if status in {"fail", "failed", "error"}:
            return "#3B171C" if dark else "#FEE2E2"
        if status in {"warning", "warn"}:
            return "#3A2A0E" if dark else "#FEF3C7"
        if status == "pass":
            return "#10351F" if dark else "#DCFCE7"
        dark_nodes = {
            "requirement": "#123554",
            "model_object": "#103A47",
            "ifc": "#272D52",
            "source": "#223047",
            "calculation": "#332857",
            "evidence": "#193B2B",
            "check": "#3B3210",
            "finding": "#442A17",
            "verdict": "#273449",
            "verification_run": "#15372E",
        }
        light_nodes = {
            "requirement": "#DBEAFE",
            "model_object": "#E0F2FE",
            "ifc": "#E0E7FF",
            "source": "#F1F5F9",
            "calculation": "#EDE9FE",
            "evidence": "#DCFCE7",
            "check": "#FEF9C3",
            "finding": "#FFEDD5",
            "verdict": "#E2E8F0",
            "verification_run": "#D1FAE5",
        }
        return (dark_nodes if dark else light_nodes).get(
            node.get("type"),
            self._theme_palette["surface_alt"],
        )

    def apply_theme(self, value: str, *, redraw: bool = True) -> None:
        """Retheme graph surfaces without changing ProofGraph evidence state."""
        self._theme_palette = theme_palette(value)
        self.canvas.configure(
            background=self._theme_palette["canvas_2d"],
            highlightbackground=self._theme_palette["border"],
        )
        for widget in (self.summary_detail, self.technical_detail):
            widget.configure(
                background=self._theme_palette["field"],
                foreground=self._theme_palette["field_text"],
                insertbackground=self._theme_palette["text"],
                selectbackground=self._theme_palette["selection"],
                selectforeground=self._theme_palette["selection_text"],
            )
        type_colors = {
            "requirement": self._theme_palette["hvac"],
            "model_object": self._theme_palette["geometry"],
            "ifc": self._theme_palette["geometry"],
            "source": self._theme_palette["muted"],
            "calculation": self._theme_palette["simulation"],
            "evidence": self._theme_palette["evidence"],
            "check": self._theme_palette["warning"],
            "finding": self._theme_palette["utilities"],
            "verdict": self._theme_palette["verification"],
            "verification_run": self._theme_palette["verification"],
        }
        for node_type, color in type_colors.items():
            self.tree.tag_configure(f"type:{node_type}", foreground=color)
        self.tree.tag_configure(
            "status:fail",
            foreground=self._theme_palette["error"],
        )
        self.tree.tag_configure(
            "status:failed",
            foreground=self._theme_palette["error"],
        )
        self.tree.tag_configure(
            "status:error",
            foreground=self._theme_palette["error"],
        )
        self.tree.tag_configure(
            "status:warning",
            foreground=self._theme_palette["warning"],
        )
        if redraw:
            self._draw_graph()

    def _draw_graph(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        self._canvas_key_by_item.clear()
        nodes = self._projection.get("nodes", [])
        edges = self._projection.get("edges", [])
        if not nodes:
            canvas.create_text(
                24,
                24,
                anchor="nw",
                text="No ProofGraph nodes for the current graph/filter.",
                fill=self._theme_palette["muted"],
            )
            canvas.configure(scrollregion=(0, 0, 800, 500))
            return

        by_column: dict[int, list[dict[str, Any]]] = {}
        for node in nodes:
            column = _TYPE_ORDER.get(node["type"], 99)
            by_column.setdefault(column, []).append(node)

        positions: dict[str, tuple[float, float]] = {}
        x_spacing = 235
        y_spacing = 88
        margin_x = 35
        margin_y = 55
        max_rows = 1
        for column in sorted(by_column):
            column_nodes = by_column[column]
            max_rows = max(max_rows, len(column_nodes))
            for row, node in enumerate(column_nodes):
                positions[node["key"]] = (
                    margin_x + column * x_spacing,
                    margin_y + row * y_spacing,
                )

        for edge in edges:
            source = positions.get(edge["source"])
            target = positions.get(edge["target"])
            if source is None or target is None:
                continue
            canvas.create_line(
                source[0] + 160,
                source[1] + 24,
                target[0],
                target[1] + 24,
                fill=self._theme_palette["strong_border"],
                width=1,
                arrow="last",
            )

        for node in nodes:
            x, y = positions[node["key"]]
            selected = node["key"] == self._selected_key
            outline = (
                self._theme_palette["accent"]
                if selected
                else self._theme_palette["strong_border"]
            )
            width = 3 if selected else 1
            rect = canvas.create_rectangle(
                x,
                y,
                x + 160,
                y + 48,
                fill=self._node_fill(node),
                outline=outline,
                width=width,
            )
            label = node["label"]
            if len(label) > 32:
                label = label[:29] + "…"
            status = f"\n{node['status'].upper()}" if node.get("status") else ""
            text_item = canvas.create_text(
                x + 80,
                y + 24,
                width=148,
                text=label + status,
                justify="center",
                fill=self._theme_palette["text"],
            )
            self._canvas_key_by_item[rect] = node["key"]
            self._canvas_key_by_item[text_item] = node["key"]

        width = margin_x + (max(by_column) + 1) * x_spacing + 190
        height = margin_y + max_rows * y_spacing + 70
        canvas.configure(scrollregion=(0, 0, width, height))

    def _select_key(self, key: str | None) -> None:
        if key not in self._nodes_by_key:
            return
        self._selected_key = key
        self._populate_tree()
        self._draw_graph()
        self._show_selected_detail()

    def _on_tree_selected(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        key = self._tree_key_by_iid.get(selection[0])
        if key:
            self._select_key(key)

    def _on_canvas_selected(self, _event=None) -> None:
        current = self.canvas.find_withtag("current")
        if not current:
            return
        key = self._canvas_key_by_item.get(current[0])
        if key:
            self._select_key(key)

    @staticmethod
    def _summary_lines(node: dict[str, Any]) -> list[str]:
        raw = node.get("raw", {})
        if not isinstance(raw, dict):
            raw = {}
        lines = [
            node["type"].replace("_", " ").upper(),
            node["label"],
            "",
            f"Identifier: {node.get('id', '')}",
        ]
        if node.get("status"):
            lines.append(f"Status: {str(node['status']).upper()}")
        flags = [str(value) for value in node.get("flags", ()) if value]
        if flags:
            lines.append("Traceability flags: " + ", ".join(flags))

        field_labels = (
            ("requirement_id", "Requirement"),
            ("check_id", "Check"),
            ("subject_ref", "Model subject"),
            ("cleanroomx_entity_id", "CleanroomX entity"),
            ("ifc_global_id", "IFC GlobalId"),
            ("source_id", "Evidence source"),
            ("kind", "Kind"),
            ("property_name", "Property"),
            ("unit", "Unit"),
            ("reason", "Reason"),
            ("reference", "Source reference"),
            ("timestamp", "Timestamp"),
            ("created_at", "Created"),
            ("version", "Version"),
        )
        presented = False
        for key, label in field_labels:
            value = raw.get(key)
            if value not in (None, "", [], {}):
                if not presented:
                    lines.extend(("", "TRACEABILITY CONTEXT"))
                    presented = True
                lines.append(f"{label}: {value}")

        provenance = raw.get("provenance")
        if isinstance(provenance, list):
            if not presented:
                lines.extend(("", "TRACEABILITY CONTEXT"))
            lines.append(f"Provenance records: {len(provenance)}")
        evidence_ids = raw.get("evidence_ids")
        if isinstance(evidence_ids, list):
            if not presented:
                lines.extend(("", "TRACEABILITY CONTEXT"))
            lines.append(f"Linked evidence items: {len(evidence_ids)}")
        finding_ids = raw.get("finding_ids")
        if isinstance(finding_ids, list):
            if not presented:
                lines.extend(("", "TRACEABILITY CONTEXT"))
            lines.append(f"Linked findings: {len(finding_ids)}")
        return lines

    def _show_selected_detail(self) -> None:
        for widget in (self.summary_detail, self.technical_detail):
            widget.configure(state="normal")
            widget.delete("1.0", "end")

        node = self._nodes_by_key.get(self._selected_key or "")
        if node is None:
            self.summary_detail.insert(
                "1.0",
                (
                    "No ProofGraph node selected.\n\n"
                    "Select a requirement, model object, calculation, verification "
                    "node, or evidence node to inspect its traceability context."
                ),
            )
        else:
            self.summary_detail.insert("1.0", "\n".join(self._summary_lines(node)))
            self.technical_detail.insert(
                "1.0",
                json.dumps(
                    node.get("raw", {}),
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                ),
            )

        for widget in (self.summary_detail, self.technical_detail):
            widget.configure(state="disabled")

    def selected_node(self) -> dict[str, Any] | None:
        node = self._nodes_by_key.get(self._selected_key or "")
        return node if isinstance(node, dict) else None

    def _navigate_selected(self, _event=None):
        node = self.selected_node()
        if node is None:
            return "break"
        if self._on_navigate is not None:
            self._on_navigate(node)
        else:
            self._status_setter("No model navigation target configured")
        return "break"
