from __future__ import annotations

import json
from typing import Any, Callable, Iterable

import tkinter as tk
from tkinter import ttk

from .proofgraph_io import proofgraph_from_dict


PROOFGRAPH_FILTERS = (
    "All",
    "Requirements",
    "Evidence",
    "Calculations",
    "IFC",
    "Verification",
    "Failures",
    "Unresolved Evidence",
)

_KIND_TITLES = {
    "requirement": "Requirements",
    "evidence_source": "Evidence Sources",
    "provenance": "Provenance",
    "evidence": "Evidence / Results",
    "check": "Verification Checks",
    "finding": "Findings / Results",
    "verdict": "Verdicts",
    "run": "Verification Runs",
}

_KIND_ORDER = (
    "requirement",
    "evidence_source",
    "provenance",
    "evidence",
    "check",
    "finding",
    "verdict",
    "run",
)

_NODE_FILL = {
    "requirement": "#eef4fb",
    "evidence_source": "#f4f0f8",
    "provenance": "#f8f5ed",
    "evidence": "#edf6f8",
    "check": "#f1f3f5",
    "finding": "#ffffff",
    "verdict": "#ffffff",
    "run": "#eef1f4",
}

_STATUS_OUTLINE = {
    "pass": "#2f7d4f",
    "warning": "#9a6700",
    "fail": "#b42318",
    "unknown": "#667085",
    "indeterminate": "#6941c6",
    "not_checked": "#667085",
}

_STATUS_FILL = {
    "pass": "#edf7f0",
    "warning": "#fff7e6",
    "fail": "#fff1f0",
    "unknown": "#f2f4f7",
    "indeterminate": "#f4f0ff",
    "not_checked": "#f2f4f7",
}


def _status(value: dict[str, Any]) -> str:
    return str(value.get("status") or "").strip().lower()


def _string_values(values: Iterable[Any]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return tuple(result)


def _display_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return str(value)


def _node_label(kind: str, item: dict[str, Any]) -> str:
    if kind == "requirement":
        return str(item.get("title") or item.get("id") or "Requirement")
    if kind == "evidence_source":
        reference = str(item.get("reference") or item.get("id") or "Source")
        source_kind = str(item.get("kind") or "source").upper()
        return f"{source_kind} · {reference}"
    if kind == "provenance":
        return str(
            item.get("originating_calculation")
            or item.get("method")
            or item.get("origin")
            or item.get("id")
            or "Provenance"
        )
    if kind == "evidence":
        property_name = str(item.get("property_name") or item.get("id") or "Evidence")
        value = item.get("value")
        unit = str(item.get("unit") or "")
        rendered = _display_value(value) if value is not None else "missing"
        if unit:
            rendered = f"{rendered} {unit}"
        return f"{property_name} = {rendered}"
    if kind in {"finding", "verdict"}:
        status = str(item.get("status") or "unknown").upper()
        reason = str(item.get("reason") or item.get("id") or kind.title())
        return f"{status} · {reason}"
    if kind == "run":
        return str(item.get("id") or "Verification run")
    return str(item.get("id") or kind.title())


def build_proofgraph_view_model(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and project one canonical ProofGraph document for GUI display.

    The projection is read-only. It does not recompute findings or verdicts.
    """

    graph = proofgraph_from_dict(raw)
    document = graph.to_dict()
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[tuple[str, str, str]] = []

    def add_node(
        key: str,
        kind: str,
        data: dict[str, Any],
        *,
        subjects: Iterable[Any] = (),
        calculation: bool = False,
        ifc: bool = False,
        unresolved: bool = False,
    ) -> None:
        nodes[key] = {
            "key": key,
            "kind": kind,
            "label": _node_label(kind, data),
            "status": _status(data),
            "subjects": _string_values(subjects),
            "calculation": bool(calculation),
            "ifc": bool(ifc),
            "unresolved": bool(unresolved),
            "data": data,
        }

    source_by_id: dict[str, dict[str, Any]] = {}
    for source in document.get("evidence_sources", []):
        source_id = str(source["id"])
        source_by_id[source_id] = source
        is_ifc = str(source.get("kind") or "").casefold() == "ifc"
        add_node(
            f"source:{source_id}",
            "evidence_source",
            source,
            ifc=is_ifc,
        )

    requirement_by_id: dict[str, dict[str, Any]] = {}
    requirement_set = document.get("requirement_set", {})
    for requirement in requirement_set.get("requirements", []):
        requirement_id = str(requirement["id"])
        requirement_by_id[requirement_id] = requirement
        add_node(
            f"requirement:{requirement_id}",
            "requirement",
            requirement,
            subjects=requirement.get("scope", []),
        )

    evidence_by_id: dict[str, dict[str, Any]] = {}
    provenance_keys_by_evidence: dict[str, list[str]] = {}
    for evidence in document.get("evidence", []):
        evidence_id = str(evidence["id"])
        evidence_by_id[evidence_id] = evidence
        source_id = str(evidence.get("source_id") or "")
        source = source_by_id.get(source_id, {})
        kind = str(evidence.get("kind") or "")
        provenance = evidence.get("provenance", [])
        if not isinstance(provenance, list):
            provenance = []

        direct_subjects: list[Any] = [evidence.get("subject_ref")]
        direct_subjects.extend(
            item.get("cleanroomx_entity_id")
            for item in provenance
            if isinstance(item, dict)
        )
        is_ifc = (
            str(source.get("kind") or "").casefold() == "ifc"
            or any(
                bool(item.get("ifc_global_id"))
                for item in provenance
                if isinstance(item, dict)
            )
        )
        is_calculation = kind == "calculation" or any(
            bool(item.get("originating_calculation"))
            for item in provenance
            if isinstance(item, dict)
        )
        add_node(
            f"evidence:{evidence_id}",
            "evidence",
            evidence,
            subjects=direct_subjects,
            calculation=is_calculation,
            ifc=is_ifc,
        )
        if source_id:
            edges.append(
                (f"source:{source_id}", f"evidence:{evidence_id}", "source")
            )

        provenance_keys: list[str] = []
        for index, record in enumerate(provenance):
            if not isinstance(record, dict):
                continue
            provenance_id = str(record.get("id") or f"{evidence_id}:{index}")
            provenance_key = f"provenance:{evidence_id}:{provenance_id}"
            provenance_keys.append(provenance_key)
            provenance_source_id = str(record.get("source_id") or source_id)
            provenance_ifc = bool(record.get("ifc_global_id")) or (
                str(source_by_id.get(provenance_source_id, {}).get("kind") or "")
                .casefold()
                == "ifc"
            )
            provenance_calculation = bool(record.get("originating_calculation"))
            add_node(
                provenance_key,
                "provenance",
                record,
                subjects=(record.get("cleanroomx_entity_id"),),
                calculation=provenance_calculation,
                ifc=provenance_ifc,
            )
            if provenance_source_id:
                edges.append(
                    (
                        f"source:{provenance_source_id}",
                        provenance_key,
                        "provenance source",
                    )
                )
            for upstream_id in record.get("upstream_evidence_ids", []):
                edges.append(
                    (
                        f"evidence:{upstream_id}",
                        provenance_key,
                        "upstream evidence",
                    )
                )
            edges.append((provenance_key, f"evidence:{evidence_id}", "provenance"))
        provenance_keys_by_evidence[evidence_id] = provenance_keys

    check_by_id: dict[str, dict[str, Any]] = {}
    for check in document.get("checks", []):
        check_id = str(check["id"])
        check_by_id[check_id] = check
        evidence_ids = tuple(str(value) for value in check.get("evidence_ids", []))
        subjects = [
            subject
            for evidence_id in evidence_ids
            for subject in nodes.get(f"evidence:{evidence_id}", {}).get("subjects", ())
        ]
        unresolved = not evidence_ids and bool(check.get("required_evidence_kinds"))
        add_node(
            f"check:{check_id}",
            "check",
            check,
            subjects=subjects,
            unresolved=unresolved,
        )
        requirement_id = str(check.get("requirement_id") or "")
        if requirement_id:
            edges.append(
                (f"requirement:{requirement_id}", f"check:{check_id}", "requirement")
            )
        for evidence_id in evidence_ids:
            edges.append(
                (f"evidence:{evidence_id}", f"check:{check_id}", "evidence")
            )

    finding_by_id: dict[str, dict[str, Any]] = {}
    for finding in document.get("findings", []):
        finding_id = str(finding["id"])
        finding_by_id[finding_id] = finding
        evidence_ids = tuple(str(value) for value in finding.get("evidence_ids", []))
        subjects = [
            subject
            for evidence_id in evidence_ids
            for subject in nodes.get(f"evidence:{evidence_id}", {}).get("subjects", ())
        ]
        status = _status(finding)
        unresolved = (
            not bool(finding.get("evidence_present"))
            or status in {"unknown", "indeterminate", "not_checked"}
        )
        add_node(
            f"finding:{finding_id}",
            "finding",
            finding,
            subjects=subjects,
            unresolved=unresolved,
        )
        check_id = str(finding.get("check_id") or "")
        if check_id:
            edges.append((f"check:{check_id}", f"finding:{finding_id}", "finding"))
        for evidence_id in evidence_ids:
            edges.append(
                (f"evidence:{evidence_id}", f"finding:{finding_id}", "supports")
            )

    verdict_by_id: dict[str, dict[str, Any]] = {}
    for verdict in document.get("verdicts", []):
        verdict_id = str(verdict["id"])
        verdict_by_id[verdict_id] = verdict
        finding_ids = tuple(str(value) for value in verdict.get("finding_ids", []))
        subjects = [
            subject
            for finding_id in finding_ids
            for subject in nodes.get(f"finding:{finding_id}", {}).get("subjects", ())
        ]
        status = _status(verdict)
        add_node(
            f"verdict:{verdict_id}",
            "verdict",
            verdict,
            subjects=subjects,
            unresolved=status in {"unknown", "indeterminate", "not_checked"},
        )
        requirement_id = str(verdict.get("requirement_id") or "")
        if requirement_id:
            edges.append(
                (
                    f"requirement:{requirement_id}",
                    f"verdict:{verdict_id}",
                    "verdict for",
                )
            )
        for finding_id in finding_ids:
            edges.append(
                (f"finding:{finding_id}", f"verdict:{verdict_id}", "verdict")
            )

    for run in document.get("verification_runs", []):
        run_id = str(run["id"])
        verdict_ids = tuple(str(value) for value in run.get("verdict_ids", []))
        subjects = [
            subject
            for verdict_id in verdict_ids
            for subject in nodes.get(f"verdict:{verdict_id}", {}).get("subjects", ())
        ]
        add_node(f"run:{run_id}", "run", run, subjects=subjects)
        for check_id in run.get("check_ids", []):
            edges.append((f"check:{check_id}", f"run:{run_id}", "run check"))
        for verdict_id in verdict_ids:
            edges.append((f"verdict:{verdict_id}", f"run:{run_id}", "run verdict"))

    # Propagate calculation/IFC flags through supporting evidence to verification nodes.
    evidence_flags: dict[str, tuple[bool, bool]] = {
        evidence_id: (
            bool(nodes[f"evidence:{evidence_id}"]["calculation"]),
            bool(nodes[f"evidence:{evidence_id}"]["ifc"]),
        )
        for evidence_id in evidence_by_id
    }
    for check_id, check in check_by_id.items():
        flags = [
            evidence_flags.get(str(evidence_id), (False, False))
            for evidence_id in check.get("evidence_ids", [])
        ]
        if flags:
            nodes[f"check:{check_id}"]["calculation"] = any(v[0] for v in flags)
            nodes[f"check:{check_id}"]["ifc"] = any(v[1] for v in flags)
    for finding_id, finding in finding_by_id.items():
        evidence_ids = finding.get("evidence_ids", [])
        flags = [
            evidence_flags.get(str(evidence_id), (False, False))
            for evidence_id in evidence_ids
        ]
        if flags:
            nodes[f"finding:{finding_id}"]["calculation"] = any(v[0] for v in flags)
            nodes[f"finding:{finding_id}"]["ifc"] = any(v[1] for v in flags)
    for verdict_id, verdict in verdict_by_id.items():
        finding_nodes = [
            nodes.get(f"finding:{finding_id}")
            for finding_id in verdict.get("finding_ids", [])
        ]
        finding_nodes = [node for node in finding_nodes if node is not None]
        if finding_nodes:
            nodes[f"verdict:{verdict_id}"]["calculation"] = any(
                node["calculation"] for node in finding_nodes
            )
            nodes[f"verdict:{verdict_id}"]["ifc"] = any(
                node["ifc"] for node in finding_nodes
            )

    return {
        "document": document,
        "nodes": nodes,
        "edges": tuple(
            edge
            for edge in edges
            if edge[0] in nodes and edge[1] in nodes
        ),
    }


def proofgraph_node_matches(
    node: dict[str, Any],
    filter_name: str,
    query: str = "",
) -> bool:
    kind = str(node.get("kind") or "")
    status = str(node.get("status") or "")
    selected = filter_name if filter_name in PROOFGRAPH_FILTERS else "All"

    if selected == "Requirements" and kind != "requirement":
        return False
    if selected == "Evidence" and kind not in {
        "evidence_source",
        "provenance",
        "evidence",
    }:
        return False
    if selected == "Calculations" and not bool(node.get("calculation")):
        return False
    if selected == "IFC" and not bool(node.get("ifc")):
        return False
    if selected == "Verification" and kind not in {
        "check",
        "finding",
        "verdict",
        "run",
    }:
        return False
    if selected == "Failures" and status not in {"fail", "warning"}:
        return False
    if selected == "Unresolved Evidence" and not bool(node.get("unresolved")):
        return False

    token = query.strip().casefold()
    if token:
        haystack = " ".join(
            (
                str(node.get("label") or ""),
                " ".join(node.get("subjects") or ()),
                json.dumps(
                    node.get("data") or {},
                    sort_keys=True,
                    ensure_ascii=False,
                    default=str,
                ),
            )
        ).casefold()
        if token not in haystack:
            return False
    return True


class ProofGraphExplorer(ttk.Frame):
    """Tree and interactive graph viewer for persisted canonical ProofGraphs."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_subject_navigate: Callable[[str], bool | None] | None = None,
        status_setter: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(master)
        self._on_subject_navigate = on_subject_navigate
        self._status_setter = status_setter or (lambda _message: None)
        self._models: list[dict[str, Any]] = []
        self._labels: list[str] = []
        self._visible_nodes: dict[str, dict[str, Any]] = {}
        self._tree_to_key: dict[str, str] = {}
        self._canvas_to_key: dict[int, str] = {}
        self._selected_key: str | None = None

        self.graph_var = tk.StringVar()
        self.filter_var = tk.StringVar(value="All")
        self.search_var = tk.StringVar()
        self.summary_var = tk.StringVar(value="No persisted ProofGraph evidence")

        self._build()
        self.search_var.trace_add("write", lambda *_: self._refresh_projection())

    def _build(self) -> None:
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
            width=32,
        )
        self.graph_combo.pack(side="left", padx=(4, 8))
        self.graph_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._refresh_projection(),
        )

        ttk.Label(toolbar, text="Filter").pack(side="left")
        filter_combo = ttk.Combobox(
            toolbar,
            textvariable=self.filter_var,
            values=PROOFGRAPH_FILTERS,
            state="readonly",
            width=18,
        )
        filter_combo.pack(side="left", padx=(4, 8))
        filter_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._refresh_projection(),
        )

        ttk.Label(toolbar, text="Search").pack(side="left")
        ttk.Entry(
            toolbar,
            textvariable=self.search_var,
            width=26,
        ).pack(side="left", fill="x", expand=True, padx=(4, 8))
        ttk.Label(toolbar, textvariable=self.summary_var).pack(side="right")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)

        view_host = ttk.Frame(body)
        details_host = ttk.Frame(body, padding=(7, 0, 0, 0))
        body.add(view_host, weight=5)
        body.add(details_host, weight=2)

        self.view_notebook = ttk.Notebook(view_host)
        self.view_notebook.pack(fill="both", expand=True)

        tree_host = ttk.Frame(self.view_notebook)
        graph_host = ttk.Frame(self.view_notebook)
        self.view_notebook.add(tree_host, text="Tree")
        self.view_notebook.add(graph_host, text="Graph")

        self.tree = ttk.Treeview(tree_host, show="tree", selectmode="browse")
        tree_scroll = ttk.Scrollbar(
            tree_host,
            orient="vertical",
            command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._navigate_selected)
        self.tree.bind("<Return>", self._navigate_selected)

        self.canvas = tk.Canvas(
            graph_host,
            background="#f7f9fb",
            highlightthickness=1,
            highlightbackground="#c7d0d9",
        )
        graph_y = ttk.Scrollbar(
            graph_host,
            orient="vertical",
            command=self.canvas.yview,
        )
        graph_x = ttk.Scrollbar(
            graph_host,
            orient="horizontal",
            command=self.canvas.xview,
        )
        self.canvas.configure(
            yscrollcommand=graph_y.set,
            xscrollcommand=graph_x.set,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        graph_y.grid(row=0, column=1, sticky="ns")
        graph_x.grid(row=1, column=0, sticky="ew")
        graph_host.rowconfigure(0, weight=1)
        graph_host.columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Double-1>", self._navigate_selected)
        self.canvas.bind("<Configure>", lambda _event: self._draw_graph())

        ttk.Label(
            details_host,
            text="NODE DETAILS",
            style="CX.Section.TLabel",
        ).pack(anchor="w", pady=(0, 4))
        self.details = tk.Text(
            details_host,
            wrap="word",
            state="disabled",
            width=40,
            borderwidth=0,
        )
        details_scroll = ttk.Scrollbar(
            details_host,
            orient="vertical",
            command=self.details.yview,
        )
        self.details.configure(yscrollcommand=details_scroll.set)
        self.details.pack(side="left", fill="both", expand=True)
        details_scroll.pack(side="right", fill="y")

    def clear(self, message: str = "No persisted ProofGraph evidence") -> None:
        self._models = []
        self._labels = []
        self.graph_combo.configure(values=())
        self.graph_var.set("")
        self._selected_key = None
        self.summary_var.set(message)
        self._refresh_projection()

    def set_documents(
        self,
        documents: Iterable[dict[str, Any]],
    ) -> None:
        models: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in documents:
            model = build_proofgraph_view_model(raw)
            document = model["document"]
            digest = str(document["graph_sha256"])
            if digest in seen:
                continue
            seen.add(digest)
            models.append(model)

        models.sort(
            key=lambda item: (
                str(item["document"].get("id") or ""),
                str(item["document"]["graph_sha256"]),
            )
        )
        self._models = models
        self._labels = [
            (
                f"{model['document'].get('id', 'ProofGraph')} · "
                f"{model['document']['graph_sha256'][:10]}"
            )
            for model in models
        ]
        self.graph_combo.configure(values=self._labels)
        if self._labels:
            if self.graph_var.get() not in self._labels:
                self.graph_var.set(self._labels[0])
        else:
            self.graph_var.set("")
        self._selected_key = None
        self._refresh_projection()

    def _current_model(self) -> dict[str, Any] | None:
        if not self._models:
            return None
        try:
            index = self._labels.index(self.graph_var.get())
        except ValueError:
            index = 0
        return self._models[index]

    def _refresh_projection(self) -> None:
        model = self._current_model()
        self._visible_nodes = {}
        self._tree_to_key.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        if model is None:
            self._set_details("")
            self.canvas.delete("all")
            self.canvas.create_text(
                max(300, self.canvas.winfo_width()) / 2,
                max(160, self.canvas.winfo_height()) / 2,
                text="No persisted canonical ProofGraph documents are available.",
                fill="#667085",
            )
            return

        nodes = model["nodes"]
        selected_filter = self.filter_var.get()
        query = self.search_var.get()
        self._visible_nodes = {
            key: node
            for key, node in nodes.items()
            if proofgraph_node_matches(node, selected_filter, query)
        }

        for kind in _KIND_ORDER:
            members = [
                node
                for node in self._visible_nodes.values()
                if node["kind"] == kind
            ]
            if not members:
                continue
            root = self.tree.insert(
                "",
                "end",
                text=f"{_KIND_TITLES[kind]} ({len(members)})",
                open=True,
            )
            for node in sorted(
                members,
                key=lambda value: value["label"].casefold(),
            ):
                iid = self.tree.insert(root, "end", text=node["label"])
                self._tree_to_key[iid] = node["key"]

        verdicts = [
            node for node in nodes.values() if node["kind"] == "verdict"
        ]
        adverse = sum(
            node["status"] in {"fail", "warning"} for node in verdicts
        )
        unresolved = sum(bool(node["unresolved"]) for node in nodes.values())
        self.summary_var.set(
            f"{len(self._visible_nodes)}/{len(nodes)} nodes · "
            f"{len(verdicts)} verdicts · {adverse} adverse · "
            f"{unresolved} unresolved"
        )

        if self._selected_key not in self._visible_nodes:
            self._selected_key = None
            self._set_details("")
        self._draw_graph()

    def _draw_graph(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        self._canvas_to_key.clear()
        model = self._current_model()
        if model is None:
            return

        x_by_kind = {
            kind: 105 + index * 205
            for index, kind in enumerate(_KIND_ORDER)
        }
        positions: dict[str, tuple[float, float]] = {}
        for kind in _KIND_ORDER:
            members = sorted(
                (
                    node
                    for node in self._visible_nodes.values()
                    if node["kind"] == kind
                ),
                key=lambda value: value["label"].casefold(),
            )
            for index, node in enumerate(members):
                positions[node["key"]] = (
                    x_by_kind[kind],
                    60 + index * 90,
                )

        for source, target, relation in model["edges"]:
            if source not in positions or target not in positions:
                continue
            x0, y0 = positions[source]
            x1, y1 = positions[target]
            canvas.create_line(
                x0 + 78,
                y0,
                x1 - 78,
                y1,
                fill="#98a2b3",
                width=1,
                arrow="last",
                tags=("proofedge",),
            )

        for key, (x, y) in positions.items():
            node = self._visible_nodes[key]
            status = node["status"]
            outline = _STATUS_OUTLINE.get(status, "#526577")
            fill = _STATUS_FILL.get(
                status,
                _NODE_FILL.get(node["kind"], "#ffffff"),
            )
            if key == self._selected_key:
                outline = "#175cd3"
                width = 3
            else:
                width = 2
            rectangle = canvas.create_rectangle(
                x - 78,
                y - 28,
                x + 78,
                y + 28,
                fill=fill,
                outline=outline,
                width=width,
                tags=("proofnode", f"proofnode:{key}"),
            )
            text_id = canvas.create_text(
                x,
                y,
                text=node["label"][:48],
                width=144,
                justify="center",
                fill="#1d2939",
                tags=("proofnode", f"proofnode:{key}"),
            )
            self._canvas_to_key[rectangle] = key
            self._canvas_to_key[text_id] = key

        width = max((x for x, _ in positions.values()), default=600) + 130
        height = max((y for _, y in positions.values()), default=260) + 90
        canvas.configure(scrollregion=(0, 0, width, height))

    def _set_details(self, value: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", value)
        self.details.configure(state="disabled")

    def _select_key(self, key: str) -> None:
        node = self._visible_nodes.get(key)
        if node is None:
            return
        self._selected_key = key
        self._set_details(
            json.dumps(
                node["data"],
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
        )
        for iid, mapped in self._tree_to_key.items():
            if mapped == key:
                self.tree.selection_set(iid)
                self.tree.focus(iid)
                self.tree.see(iid)
                break
        self._draw_graph()

    def _on_tree_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        key = self._tree_to_key.get(selection[0])
        if key is not None:
            self._select_key(key)

    def _on_canvas_click(self, _event=None) -> None:
        current = self.canvas.find_withtag("current")
        if not current:
            return
        key = self._canvas_to_key.get(current[0])
        if key is not None:
            self._select_key(key)

    def selected_node(self) -> dict[str, Any] | None:
        if self._selected_key is None:
            return None
        return self._visible_nodes.get(self._selected_key)

    def _navigate_selected(self, _event=None):
        node = self.selected_node()
        if node is None or self._on_subject_navigate is None:
            return "break"
        for subject in node.get("subjects", ()):
            if self._on_subject_navigate(str(subject)):
                self._status_setter(
                    f"ProofGraph: opened engineering subject {subject}"
                )
                return "break"
        self._status_setter(
            "ProofGraph node has no mapped CleanroomX spatial subject"
        )
        return "break"
