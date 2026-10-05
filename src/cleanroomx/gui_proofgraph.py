from __future__ import annotations

import json
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .proofgraph_io import proofgraph_from_dict
from .gui_theme import theme_palette


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


def _node_search_text(node: dict[str, Any]) -> str:
    """Return a deterministic search surface for one projected node."""
    raw = node.get("raw")
    raw_text = ""
    if isinstance(raw, (dict, list, tuple)):
        raw_text = json.dumps(
            raw,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            default=str,
        )
    elif raw is not None:
        raw_text = str(raw)
    return " ".join(
        (
            _text(node.get("type")),
            _text(node.get("id")),
            _text(node.get("label")),
            _text(node.get("status")),
            " ".join(str(flag) for flag in node.get("flags") or ()),
            raw_text,
        )
    ).casefold()


def _search_projection(
    projection: dict[str, Any],
    query: str,
) -> dict[str, Any]:
    """Search projected graph data while retaining one-hop traceability context."""
    tokens = tuple(part.casefold() for part in query.split() if part.strip())
    if not tokens:
        return projection

    nodes = projection.get("nodes", [])
    edges = projection.get("edges", [])
    matched = {
        node["key"]
        for node in nodes
        if all(token in _node_search_text(node) for token in tokens)
    }
    if not matched:
        return {"nodes": [], "edges": []}

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


def proofgraph_review_summary(projection: dict[str, Any]) -> dict[str, int]:
    """Summarize explicit graph review state without deriving compliance verdicts."""
    nodes = projection.get("nodes", [])
    edges = projection.get("edges", [])
    check_keys = {
        node["key"]
        for node in nodes
        if node.get("type") == "check"
    }
    supported_checks = {
        edge["target"]
        for edge in edges
        if edge.get("relation") == "supports" and edge.get("target") in check_keys
    }
    failure_states = {"fail", "failed", "error"}
    warning_states = {"warning", "warn"}
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "requirement_count": sum(
            1 for node in nodes if node.get("type") == "requirement"
        ),
        "evidence_count": sum(
            1 for node in nodes if node.get("type") in {"source", "evidence"}
        ),
        "check_count": len(check_keys),
        "checks_with_evidence": len(supported_checks),
        "failure_count": sum(
            1
            for node in nodes
            if _text(node.get("status")).casefold() in failure_states
        ),
        "warning_count": sum(
            1
            for node in nodes
            if _text(node.get("status")).casefold() in warning_states
        ),
        "unresolved_evidence_count": sum(
            1 for node in nodes if "unresolved" in set(node.get("flags") or ())
        ),
    }



def _node_detail_lines(node: dict[str, Any]) -> list[str]:
    """Format a ProofGraph node for engineering review without raw JSON dumping."""
    node_type = str(node.get("type") or "node").replace("_", " ").upper()
    label = str(node.get("label") or node.get("id") or "Unnamed")
    lines = [node_type, label]
    status = str(node.get("status") or "").strip()
    if status:
        lines.append(f"Status: {status.upper()}")

    raw = node.get("raw")
    raw = raw if isinstance(raw, dict) else {}
    preferred = (
        "id",
        "title",
        "kind",
        "property_name",
        "subject_ref",
        "requirement_id",
        "check_id",
        "source_id",
        "reason",
        "comparison",
        "unit",
        "value",
        "reference",
        "created_at_utc",
    )
    shown: set[str] = set()
    detail_rows: list[str] = []
    for key in preferred:
        value = raw.get(key)
        if value in (None, "", [], {}):
            continue
        shown.add(key)
        label_key = key.replace("_", " ").title()
        if isinstance(value, (list, tuple)):
            rendered = f"{len(value)} item(s)"
        elif isinstance(value, dict):
            rendered = f"{len(value)} field(s)"
        else:
            rendered = str(value)
        detail_rows.append(f"{label_key}: {rendered}")

    for key, value in sorted(raw.items()):
        if key in shown or value in (None, "", [], {}):
            continue
        if not isinstance(value, (dict, list, tuple)):
            detail_rows.append(f"{key.replace('_', ' ').title()}: {value}")

    if detail_rows:
        lines.extend(("", "TRACEABILITY DETAILS", *detail_rows))

    flags = tuple(node.get("flags") or ())
    if flags:
        lines.extend(("", "Markers: " + ", ".join(str(flag).upper() for flag in flags)))
    return lines


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
        self._theme_name = "dark"
        self._zoom = 1.0
        self._search_refresh_after: str | None = None
        self._palette = theme_palette(self._theme_name)

        self.graph_var = tk.StringVar(value="")
        self.filter_var = tk.StringVar(value="All")
        self.search_var = tk.StringVar(value="")
        self.summary_var = tk.StringVar(value="No persisted ProofGraph evidence")
        self.review_var = tk.StringVar(value="")
        self.zoom_var = tk.StringVar(value="100%")

        toolbar = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 5))
        toolbar.pack(fill="x")
        ttk.Label(
            toolbar,
            text="PROOFGRAPH TRACEABILITY",
            style="CX.Section.TLabel",
        ).pack(side="left", padx=(0, 10))
        ttk.Label(toolbar, text="Graph").pack(side="left")
        self.graph_picker = ttk.Combobox(
            toolbar,
            textvariable=self.graph_var,
            state="readonly",
            width=30,
        )
        self.graph_picker.pack(side="left", padx=(5, 10))
        ttk.Label(
            toolbar,
            textvariable=self.summary_var,
            style="CX.Muted.TLabel",
        ).pack(side="right", padx=(10, 0))
        self.graph_picker.bind("<<ComboboxSelected>>", lambda _event: self._refresh())

        controls = ttk.Frame(self, style="CX.Toolbar.TFrame", padding=(8, 4))
        controls.pack(fill="x")
        ttk.Label(controls, text="Filter").pack(side="left")
        self.filter_picker = ttk.Combobox(
            controls,
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
            width=18,
        )
        self.filter_picker.pack(side="left", padx=(5, 10))
        ttk.Label(controls, text="Search").pack(side="left")
        self.search_entry = ttk.Entry(
            controls,
            textvariable=self.search_var,
            width=24,
        )
        self.search_entry.pack(side="left", padx=(5, 10))
        ttk.Button(
            controls,
            text="Fit",
            style="CX.Compact.TButton",
            command=self._fit_graph,
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            controls,
            text="−",
            width=3,
            style="CX.Compact.TButton",
            command=lambda: self._zoom_by(0.85),
        ).pack(side="left")
        ttk.Label(
            controls,
            textvariable=self.zoom_var,
            style="CX.Muted.TLabel",
            width=6,
            anchor="center",
        ).pack(side="left", padx=3)
        ttk.Button(
            controls,
            text="+",
            width=3,
            style="CX.Compact.TButton",
            command=lambda: self._zoom_by(1.18),
        ).pack(side="left")
        ttk.Button(
            controls,
            text="100%",
            style="CX.Compact.TButton",
            command=self._reset_zoom,
        ).pack(side="left", padx=(4, 0))
        ttk.Button(
            controls,
            text="Expand tree",
            style="CX.Compact.TButton",
            command=lambda: self._set_tree_groups_open(True),
        ).pack(side="right")
        ttk.Button(
            controls,
            text="Collapse tree",
            style="CX.Compact.TButton",
            command=lambda: self._set_tree_groups_open(False),
        ).pack(side="right", padx=(0, 4))
        self.filter_picker.bind("<<ComboboxSelected>>", lambda _event: self._refresh())
        self.search_var.trace_add("write", self._schedule_search_refresh)

        lifecycle = ttk.Frame(self, style="CX.SubtlePanel.TFrame", padding=(8, 5))
        lifecycle.pack(fill="x", padx=6, pady=(0, 5))
        ttk.Label(
            lifecycle,
            text="TRACEABILITY",
            style="CX.SurfaceSection.TLabel",
        ).pack(side="left", padx=(0, 10))
        stages = (
            ("REQUIREMENT", "CX.Status.Info.TLabel"),
            ("MODEL", "CX.Status.Info.TLabel"),
            ("CALCULATION", "CX.Status.Simulation.TLabel"),
            ("VERIFICATION", "CX.Status.Warning.TLabel"),
            ("EVIDENCE", "CX.Status.Pass.TLabel"),
            ("REPORT", "CX.Status.Neutral.TLabel"),
        )
        for index, (label, style_name) in enumerate(stages):
            if index:
                ttk.Label(
                    lifecycle,
                    text="→",
                    style="CX.SurfaceMuted.TLabel",
                ).pack(side="left", padx=3)
            ttk.Label(lifecycle, text=label, style=style_name).pack(side="left", padx=1)
        ttk.Label(
            lifecycle,
            textvariable=self.review_var,
            style="CX.SurfaceMuted.TLabel",
        ).pack(side="right", padx=(12, 0))

        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)

        tree_host = ttk.Frame(panes)
        graph_host = ttk.Frame(panes)
        detail_host = ttk.Frame(panes)
        panes.add(tree_host, weight=2)
        panes.add(graph_host, weight=5)
        panes.add(detail_host, weight=2)

        legend = ttk.Frame(graph_host, style="CX.PanelHeader.TFrame", padding=(6, 4))
        legend.grid(row=0, column=0, sticky="ew")
        for text, style_name in (
            ("REQ", "CX.Status.Info.TLabel"),
            ("CALC", "CX.Status.Simulation.TLabel"),
            ("EVIDENCE", "CX.Status.Pass.TLabel"),
            ("CHECK", "CX.Status.Warning.TLabel"),
            ("FAIL", "CX.Status.Fail.TLabel"),
        ):
            ttk.Label(legend, text=text, style=style_name).pack(side="left", padx=(0, 5))

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
            background=self._palette["canvas_2d"],
            highlightthickness=1,
            highlightbackground=self._palette["border"],
        )
        graph_y = ttk.Scrollbar(graph_host, orient="vertical", command=self.canvas.yview)
        graph_x = ttk.Scrollbar(graph_host, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=graph_y.set, xscrollcommand=graph_x.set)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        graph_y.grid(row=1, column=1, sticky="ns")
        graph_x.grid(row=2, column=0, sticky="ew")
        graph_host.rowconfigure(1, weight=1)
        graph_host.columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self._on_canvas_selected)
        self.canvas.bind("<Double-1>", self._navigate_selected)
        self.canvas.bind("<ButtonPress-2>", self._start_pan)
        self.canvas.bind("<B2-Motion>", self._pan_canvas)
        self.canvas.bind("<Control-MouseWheel>", self._on_zoom_wheel)
        self.canvas.bind("<Control-Button-4>", lambda _event: self._zoom_by(1.12))
        self.canvas.bind("<Control-Button-5>", lambda _event: self._zoom_by(0.89))
        self.canvas.bind("<Configure>", lambda _event: self._draw_graph())

        detail_header = ttk.Frame(detail_host, style="CX.PanelHeader.TFrame")
        detail_header.pack(fill="x", padx=6, pady=(6, 3))
        ttk.Label(
            detail_header,
            text="TRACEABILITY INSPECTOR",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Button(
            detail_header,
            text="Open target",
            style="CX.Compact.TButton",
            command=self._navigate_selected,
        ).pack(side="right")
        ttk.Button(
            detail_header,
            text="Center",
            style="CX.Compact.TButton",
            command=self._center_selected,
        ).pack(side="right", padx=(0, 4))
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
        review = proofgraph_review_summary(projection)
        if review["node_count"]:
            coverage = (
                f"{review['checks_with_evidence']}/{review['check_count']} checks linked"
                if review["check_count"]
                else "No checks"
            )
            self.review_var.set(
                f"{coverage} · Fail {review['failure_count']} · "
                f"Unresolved evidence {review['unresolved_evidence_count']}"
            )
        else:
            self.review_var.set("")

    def _schedule_search_refresh(self, *_args) -> None:
        if self._search_refresh_after is not None:
            try:
                self.after_cancel(self._search_refresh_after)
            except tk.TclError:
                pass
        self._search_refresh_after = self.after(120, self._run_search_refresh)

    def _run_search_refresh(self) -> None:
        self._search_refresh_after = None
        self._refresh()

    def _set_tree_groups_open(self, value: bool) -> None:
        for iid in self.tree.get_children():
            self.tree.item(iid, open=value)

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

    def apply_theme(self, value: Any, *, redraw: bool = True) -> None:
        self._theme_name = str(value or "dark")
        self._palette = theme_palette(self._theme_name)
        self.canvas.configure(
            background=self._palette["canvas_2d"],
            highlightbackground=self._palette["border"],
        )
        self.detail.configure(
            background=self._palette["field"],
            foreground=self._palette["field_text"],
            insertbackground=self._palette["text"],
            selectbackground=self._palette["selection"],
            selectforeground=self._palette["selection_text"],
        )
        if redraw:
            self._draw_graph()

    def _node_accent(self, node: dict[str, Any]) -> str:
        status = _text(node.get("status")).casefold()
        if status in {"fail", "failed", "error"}:
            return self._palette["error"]
        if status in {"warning", "warn"}:
            return self._palette["warning"]
        if status in {"pass", "passed"}:
            return self._palette["success"]
        return {
            "requirement": self._palette["requirement"],
            "model_object": self._palette["accent"],
            "ifc": self._palette["info"],
            "source": self._palette["secondary_text"],
            "calculation": self._palette["simulation"],
            "evidence": self._palette["evidence"],
            "check": self._palette["warning"],
            "finding": self._palette["attention"],
            "verdict": self._palette["info"],
            "verification_run": self._palette["success"],
        }.get(node.get("type"), self._palette["muted"])

    def _node_fill(self, node: dict[str, Any]) -> str:
        status = _text(node.get("status")).casefold()
        if status in {"fail", "failed", "error"}:
            return self._palette["error_surface"]
        if status in {"warning", "warn"}:
            return self._palette["warning_surface"]
        if status in {"pass", "passed"}:
            return self._palette["success_surface"]
        return self._palette["surface_alt"]

    def _start_pan(self, event: tk.Event) -> None:
        self.canvas.scan_mark(event.x, event.y)

    def _pan_canvas(self, event: tk.Event) -> None:
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_zoom_wheel(self, event: tk.Event):
        delta = getattr(event, "delta", 0)
        self._zoom_by(1.12 if delta > 0 else 0.89)
        return "break"

    def _zoom_by(self, factor: float) -> None:
        target = min(2.2, max(0.55, self._zoom * float(factor)))
        if abs(target - self._zoom) < 0.001:
            return
        self._zoom = target
        self.zoom_var.set(f"{round(self._zoom * 100):d}%")
        self._draw_graph()

    def _reset_zoom(self) -> None:
        self._zoom = 1.0
        self.zoom_var.set("100%")
        self._draw_graph()
        self.canvas.xview_moveto(0.0)
        self.canvas.yview_moveto(0.0)

    def _fit_graph(self) -> None:
        self._draw_graph()
        bbox = self.canvas.bbox("all")
        if not bbox:
            return
        width = max(1, bbox[2] - bbox[0])
        height = max(1, bbox[3] - bbox[1])
        viewport_width = max(1, self.canvas.winfo_width() - 24)
        viewport_height = max(1, self.canvas.winfo_height() - 24)
        factor = min(viewport_width / width, viewport_height / height)
        target = min(1.35, max(0.55, self._zoom * factor))
        self._zoom = target
        self.zoom_var.set(f"{round(self._zoom * 100):d}%")
        self._draw_graph()
        self.canvas.xview_moveto(0.0)
        self.canvas.yview_moveto(0.0)

    def _center_selected(self) -> None:
        key = self._selected_key
        if not key:
            return
        tag = f"proofnode:{key}"
        bbox = self.canvas.bbox(tag)
        all_bbox = self.canvas.bbox("all")
        if not bbox or not all_bbox:
            return
        center_x = (bbox[0] + bbox[2]) / 2
        center_y = (bbox[1] + bbox[3]) / 2
        total_width = max(1, all_bbox[2] - all_bbox[0])
        total_height = max(1, all_bbox[3] - all_bbox[1])
        view_width = max(1, self.canvas.winfo_width())
        view_height = max(1, self.canvas.winfo_height())
        self.canvas.xview_moveto(
            min(1.0, max(0.0, (center_x - view_width / 2) / total_width))
        )
        self.canvas.yview_moveto(
            min(1.0, max(0.0, (center_y - view_height / 2) / total_height))
        )

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
                fill=self._palette["muted"],
                font=("TkDefaultFont", 10),
            )
            canvas.configure(scrollregion=(0, 0, 800, 500))
            return

        by_column: dict[int, list[dict[str, Any]]] = {}
        for node in nodes:
            column = _TYPE_ORDER.get(node["type"], 99)
            by_column.setdefault(column, []).append(node)

        positions: dict[str, tuple[float, float]] = {}
        zoom = self._zoom
        x_spacing = max(130, round(235 * zoom))
        y_spacing = max(58, round(88 * zoom))
        margin_x = max(20, round(35 * zoom))
        margin_y = max(34, round(55 * zoom))
        node_width = max(104, round(160 * zoom))
        node_height = max(34, round(48 * zoom))
        max_rows = 1
        for column in sorted(by_column):
            column_nodes = by_column[column]
            max_rows = max(max_rows, len(column_nodes))
            for row, node in enumerate(column_nodes):
                positions[node["key"]] = (
                    margin_x + column * x_spacing,
                    margin_y + row * y_spacing,
                )

        for column in sorted(by_column):
            column_nodes = by_column[column]
            if not column_nodes:
                continue
            title = _NODE_TITLES.get(
                column_nodes[0]["type"],
                column_nodes[0]["type"].replace("_", " ").title(),
            )
            x = margin_x + column * x_spacing
            canvas.create_text(
                x,
                24,
                anchor="w",
                text=title.upper(),
                fill=self._palette["muted"],
                font=("TkDefaultFont", 8, "bold"),
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
                fill=self._palette["border_strong"],
                width=1,
                arrow="last",
                arrowshape=(7, 8, 3),
            )

        for node in nodes:
            x, y = positions[node["key"]]
            selected = node["key"] == self._selected_key
            accent = self._node_accent(node)
            outline = self._palette["accent"] if selected else accent
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
            stripe = canvas.create_rectangle(
                x,
                y,
                x + max(4, round(5 * zoom)),
                y + node_height,
                fill=accent,
                outline=accent,
                width=0,
            )
            label = node["label"]
            if len(label) > 32:
                label = label[:29] + "…"
            status = f"\n{node['status'].upper()}" if node.get("status") else ""
            tag = f"proofnode:{node['key']}"
            canvas.itemconfigure(rect, tags=(tag,))
            canvas.itemconfigure(stripe, tags=(tag,))
            text_item = canvas.create_text(
                x + node_width / 2,
                y + node_height / 2,
                width=max(88, node_width - round(18 * zoom)),
                text=label + status,
                justify="center",
                fill=self._palette["text"],
                font=(
                    "TkDefaultFont",
                    max(7, round(8 * zoom)),
                    "bold" if selected else "normal",
                ),
                tags=(tag,),
            )
            self._canvas_key_by_item[rect] = node["key"]
            self._canvas_key_by_item[stripe] = node["key"]
            self._canvas_key_by_item[text_item] = node["key"]

        width = margin_x + (max(by_column) + 1) * x_spacing + node_width + 30
        height = margin_y + max_rows * y_spacing + node_height + 30
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
            self.detail.insert("1.0", "\n".join(_node_detail_lines(node)))
        else:
            self.detail.insert(
                "1.0",
                "No traceability node selected. Select a node to inspect its persisted engineering evidence.",
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
