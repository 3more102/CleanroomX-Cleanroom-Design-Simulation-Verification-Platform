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


def _searched_projection(
    projection: dict[str, Any],
    query: str,
) -> dict[str, Any]:
    tokens = [
        token
        for token in str(query or "").strip().casefold().split()
        if token
    ]
    if not tokens:
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
                " ".join(str(flag) for flag in (node.get("flags") or ())),
                json.dumps(
                    node.get("raw", {}),
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                ),
            )
        ).casefold()
        if all(token in haystack for token in tokens):
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
        self._zoom = 1.0
        self._theme_palette = theme_palette("light")

        self.graph_var = tk.StringVar(value="")
        self.filter_var = tk.StringVar(value="All")
        self.search_var = tk.StringVar(value="")
        self.summary_var = tk.StringVar(value="No persisted ProofGraph evidence")
        self.zoom_var = tk.StringVar(value="100%")

        toolbar = ttk.Frame(self, padding=(7, 5, 7, 2))
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Graph").pack(side="left")
        self.graph_picker = ttk.Combobox(
            toolbar,
            textvariable=self.graph_var,
            state="readonly",
            width=30,
        )
        self.graph_picker.pack(side="left", padx=(5, 8))
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
            width=16,
        )
        self.filter_picker.pack(side="left", padx=(5, 8))
        ttk.Label(toolbar, text="Search").pack(side="left")
        ttk.Entry(
            toolbar,
            textvariable=self.search_var,
            width=18,
        ).pack(side="left", padx=(5, 8))
        ttk.Button(
            toolbar,
            text="Fit",
            width=5,
            style="CX.Compact.TButton",
            command=self.fit_graph,
        ).pack(side="left", padx=1)
        ttk.Button(
            toolbar,
            text="−",
            width=3,
            style="CX.Compact.TButton",
            command=lambda: self.zoom_graph(1 / 1.15),
        ).pack(side="left", padx=1)
        ttk.Button(
            toolbar,
            text="+",
            width=3,
            style="CX.Compact.TButton",
            command=lambda: self.zoom_graph(1.15),
        ).pack(side="left", padx=1)

        graph_status = ttk.Frame(self, padding=(7, 0, 7, 4))
        graph_status.pack(fill="x")
        ttk.Label(graph_status, textvariable=self.summary_var).pack(side="left")
        ttk.Label(
            graph_status,
            textvariable=self.zoom_var,
        ).pack(side="right")
        ttk.Label(
            graph_status,
            text="Ctrl+wheel zoom · middle-drag pan",
        ).pack(side="right", padx=(0, 10))

        self.graph_picker.bind("<<ComboboxSelected>>", lambda _event: self._refresh())
        self.filter_picker.bind("<<ComboboxSelected>>", lambda _event: self._refresh())
        self.search_var.trace_add("write", lambda *_: self._refresh())

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
            background=self._theme_palette["plot"],
            highlightthickness=1,
            highlightbackground=self._theme_palette["border"],
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
        self.canvas.bind("<Button-2>", self._pan_start)
        self.canvas.bind("<B2-Motion>", self._pan_drag)
        self.canvas.bind(
            "<Control-MouseWheel>",
            lambda event: self.zoom_graph(1.15 if event.delta > 0 else 1 / 1.15),
        )
        self.canvas.bind(
            "<Control-Button-4>",
            lambda _event: self.zoom_graph(1.15),
        )
        self.canvas.bind(
            "<Control-Button-5>",
            lambda _event: self.zoom_graph(1 / 1.15),
        )

        ttk.Label(
            detail_host,
            text="NODE DETAILS",
            style="CX.Section.TLabel",
        ).pack(anchor="w", padx=7, pady=(6, 3))
        self.detail = tk.Text(
            detail_host,
            wrap="word",
            state="disabled",
            borderwidth=0,
        )
        detail_scroll = ttk.Scrollbar(
            detail_host,
            orient="vertical",
            command=self.detail.yview,
        )
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=(0, 6))
        detail_scroll.pack(side="right", fill="y", pady=(0, 6))
        self.apply_theme("light", redraw=False)

    def apply_theme(self, value: str, *, redraw: bool = True) -> None:
        self._theme_palette = theme_palette(value)
        self.canvas.configure(
            background=self._theme_palette["plot"],
            highlightbackground=self._theme_palette["border"],
        )
        self.detail.configure(
            background=self._theme_palette["field"],
            foreground=self._theme_palette["field_text"],
            insertbackground=self._theme_palette["text"],
            selectbackground=self._theme_palette["selection"],
            selectforeground=self._theme_palette["selection_text"],
        )
        if redraw:
            self._draw_graph()

    def zoom_graph(self, factor: float) -> float:
        self._zoom = min(2.5, max(0.45, self._zoom * float(factor)))
        self.zoom_var.set(f"{round(self._zoom * 100):d}%")
        self._draw_graph()
        return self._zoom

    def fit_graph(self) -> float:
        self.canvas.update_idletasks()
        if not self._projection.get("nodes"):
            self._zoom = 1.0
            self.zoom_var.set("100%")
            self._draw_graph()
            return self._zoom
        current = self.canvas.bbox("all")
        if current is None:
            return self._zoom
        current_width = max(1.0, float(current[2] - current[0]))
        current_height = max(1.0, float(current[3] - current[1]))
        base_width = current_width / max(self._zoom, 0.01)
        base_height = current_height / max(self._zoom, 0.01)
        available_width = max(120.0, float(self.canvas.winfo_width()) - 24.0)
        available_height = max(120.0, float(self.canvas.winfo_height()) - 24.0)
        self._zoom = min(
            2.5,
            max(
                0.45,
                min(available_width / base_width, available_height / base_height),
            ),
        )
        self.zoom_var.set(f"{round(self._zoom * 100):d}%")
        self._draw_graph()
        self.canvas.xview_moveto(0.0)
        self.canvas.yview_moveto(0.0)
        return self._zoom

    def _pan_start(self, event: tk.Event) -> str:
        self.canvas.scan_mark(event.x, event.y)
        return "break"

    def _pan_drag(self, event: tk.Event) -> str:
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        return "break"

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
        self._projection = _searched_projection(filtered, self.search_var.get())
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
        if all_nodes:
            failures = sum(
                _text(node.get("status")).casefold()
                in {"fail", "failed", "error"}
                for node in all_nodes
            )
            unresolved = sum(
                "unresolved" in set(node.get("flags") or ())
                for node in all_nodes
            )
            evidence = sum(
                node.get("type") in {"source", "evidence"}
                for node in all_nodes
            )
            requirements = sum(
                node.get("type") == "requirement"
                for node in all_nodes
            )
            self.summary_var.set(
                f"{len(shown)}/{len(all_nodes)} nodes · "
                f"{len(self._projection.get('edges', []))} links · "
                f"{requirements} req · {evidence} evidence · "
                f"{failures} fail · {unresolved} unresolved"
            )
        else:
            self.summary_var.set("No persisted ProofGraph evidence")

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
            self.tree.insert(
                groups[node_type],
                "end",
                iid=iid,
                text=f"{node['label']}{suffix}",
            )
            self._tree_key_by_iid[iid] = node["key"]
            if node["key"] == self._selected_key:
                self.tree.selection_set(iid)
                self.tree.see(iid)

    @staticmethod
    def _node_fill(node: dict[str, Any]) -> str:
        status = _text(node.get("status")).casefold()
        if status in {"fail", "failed", "error"}:
            return "#fee2e2"
        if status in {"warning", "warn"}:
            return "#fef3c7"
        if status == "pass":
            return "#dcfce7"
        return {
            "requirement": "#dbeafe",
            "model_object": "#e0f2fe",
            "ifc": "#e0e7ff",
            "source": "#f1f5f9",
            "calculation": "#ede9fe",
            "evidence": "#f3e8ff",
            "check": "#fef9c3",
            "finding": "#ffedd5",
            "verdict": "#e2e8f0",
            "verification_run": "#d1fae5",
        }.get(node.get("type"), "#f8fafc")

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
        zoom = self._zoom
        x_spacing = 235 * zoom
        y_spacing = 88 * zoom
        margin_x = 35 * zoom
        margin_y = 55 * zoom
        node_width = 160 * zoom
        node_height = 48 * zoom
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
                source[0] + node_width,
                source[1] + node_height / 2,
                target[0],
                target[1] + node_height / 2,
                fill=self._theme_palette["muted"],
                width=1,
                arrow="last",
            )

        for node in nodes:
            x, y = positions[node["key"]]
            selected = node["key"] == self._selected_key
            outline = (
                self._theme_palette["accent"]
                if selected
                else self._theme_palette["muted"]
            )
            width = 3 if selected else 1
            rect = canvas.create_rectangle(
                x,
                y,
                x + node_width,
                y + node_height,
                fill=self._node_fill(node),
                outline=outline,
                width=width,
            )
            label = node["label"]
            if len(label) > 32:
                label = label[:29] + "…"
            status = f"\n{node['status'].upper()}" if node.get("status") else ""
            text_item = canvas.create_text(
                x + node_width / 2,
                y + node_height / 2,
                width=max(90, int(148 * zoom)),
                text=label + status,
                justify="center",
                fill="#0f172a",
            )
            self._canvas_key_by_item[rect] = node["key"]
            self._canvas_key_by_item[text_item] = node["key"]

        width = margin_x + (max(by_column) + 1) * x_spacing + 190 * zoom
        height = margin_y + max_rows * y_spacing + 70 * zoom
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

    def _show_selected_detail(self) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        node = self._nodes_by_key.get(self._selected_key or "")
        if node is not None:
            header = (
                f"{node['type'].replace('_', ' ').upper()}\n"
                f"{node['label']}\n"
            )
            if node.get("status"):
                header += f"Status: {node['status'].upper()}\n"
            self.detail.insert("1.0", header + "\n")
            self.detail.insert(
                "end",
                json.dumps(
                    node.get("raw", {}),
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                ),
            )
        self.detail.configure(state="disabled")

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
