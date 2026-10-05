from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
import tkinter as tk
from tkinter import ttk

from .gui_proofgraph import proofgraph_projection


@dataclass(frozen=True)
class SearchEntry:
    """One navigable engineering entity exposed by global search."""

    key: str
    category: str
    label: str
    detail: str = ""
    target_type: str = ""
    target_id: str = ""
    keywords: tuple[str, ...] = ()
    payload: Any = None


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _search_haystack(entry: SearchEntry) -> str:
    return " ".join(
        (
            entry.label,
            entry.category,
            entry.detail,
            entry.target_type,
            entry.target_id,
            *entry.keywords,
        )
    ).casefold()


def filter_search_entries(
    entries: Iterable[SearchEntry],
    query: str,
    *,
    category: str = "All",
) -> list[SearchEntry]:
    """Return deterministic relevance-ranked engineering search matches."""
    category_token = _text(category).casefold()
    tokens = [token for token in _text(query).casefold().split() if token]
    ranked: list[tuple[int, int, SearchEntry]] = []

    for index, entry in enumerate(entries):
        if (
            category_token not in {"", "all"}
            and entry.category.casefold() != category_token
        ):
            continue
        haystack = _search_haystack(entry)
        if any(token not in haystack for token in tokens):
            continue

        label = entry.label.casefold()
        detail = entry.detail.casefold()
        score = 0
        for token in tokens:
            if label == token:
                score += 100
            elif label.startswith(token):
                score += 45
            elif token in label:
                score += 25
            elif token in detail:
                score += 10
            else:
                score += 4
        ranked.append((-score, index, entry))

    ranked.sort(key=lambda item: (item[0], item[1], item[2].label.casefold()))
    return [entry for _score, _index, entry in ranked]


def _append_unique(
    entries: list[SearchEntry],
    seen: set[str],
    entry: SearchEntry,
) -> None:
    if not entry.key or entry.key in seen:
        return
    seen.add(entry.key)
    entries.append(entry)


def build_engineering_search_entries(
    *,
    project: Any,
    spatial_layout: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
    requirement_snapshot: dict[str, Any] | None = None,
    proofgraph_documents: Iterable[dict[str, Any]] = (),
) -> list[SearchEntry]:
    """Build a read-only index strictly from canonical in-memory project data."""
    entries: list[SearchEntry] = []
    seen: set[str] = set()

    project_name = _text(getattr(project, "name", "")) or "Untitled project"
    _append_unique(
        entries,
        seen,
        SearchEntry(
            key="project",
            category="Project",
            label=project_name,
            detail=_text(getattr(project, "description", "")),
            target_type="project",
            keywords=("project", "model"),
        ),
    )

    analyses = getattr(project, "analyses", ())
    if isinstance(analyses, (list, tuple)):
        for analysis in analyses:
            analysis_id = _text(getattr(analysis, "id", ""))
            if not analysis_id:
                continue
            kind = _text(getattr(analysis, "kind", ""))
            _append_unique(
                entries,
                seen,
                SearchEntry(
                    key=f"analysis:{analysis_id}",
                    category="Analysis",
                    label=_text(getattr(analysis, "name", "")) or analysis_id,
                    detail=kind,
                    target_type="analysis",
                    target_id=analysis_id,
                    keywords=(kind, "simulation", "solver", "input", "result"),
                ),
            )

    layout = spatial_layout if isinstance(spatial_layout, dict) else {}
    for collection_name, category, target_type in (
        ("rooms", "Room", "room"),
        ("devices", "Device", "device"),
    ):
        collection = layout.get(collection_name, [])
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            item_id = _text(item.get("id"))
            if not item_id:
                continue
            kind = _text(item.get("type"))
            level = _text(item.get("level") or item.get("floor") or item.get("storey"))
            detail = " · ".join(part for part in (kind, level, item_id) if part)
            _append_unique(
                entries,
                seen,
                SearchEntry(
                    key=f"{target_type}:{item_id}",
                    category=category,
                    label=_text(item.get("name")) or item_id,
                    detail=detail,
                    target_type=target_type,
                    target_id=item_id,
                    keywords=(kind, level, item_id, "spatial", "model"),
                    payload=item,
                ),
            )

    result = diagnostics if isinstance(diagnostics, dict) else {}
    issues = result.get("issues", [])
    if isinstance(issues, list):
        for index, issue in enumerate(issues):
            if not isinstance(issue, dict):
                continue
            code = _text(issue.get("code") or issue.get("rule"))
            rule = _text(issue.get("rule"))
            message = _text(issue.get("message")) or "Diagnostic"
            severity = _text(issue.get("severity"))
            element = issue.get("element")
            element_id = _text(element.get("id")) if isinstance(element, dict) else ""
            _append_unique(
                entries,
                seen,
                SearchEntry(
                    key=f"diagnostic:{code or 'issue'}:{element_id}:{index}",
                    category="Diagnostic",
                    label=f"{code}: {message}" if code else message,
                    detail=" · ".join(
                        part
                        for part in (severity.upper(), rule, element_id)
                        if part
                    ),
                    target_type="diagnostic",
                    target_id=code,
                    keywords=(
                        severity,
                        rule,
                        element_id,
                        "warning",
                        "error",
                        "verification",
                    ),
                    payload=issue,
                ),
            )

    snapshot = requirement_snapshot if isinstance(requirement_snapshot, dict) else {}
    requirements = snapshot.get("requirements", [])
    if isinstance(requirements, list):
        for requirement in requirements:
            if not isinstance(requirement, dict):
                continue
            requirement_id = _text(requirement.get("id"))
            if not requirement_id:
                continue
            status = _text(requirement.get("status"))
            source = _text(requirement.get("source"))
            _append_unique(
                entries,
                seen,
                SearchEntry(
                    key=f"requirement:{requirement_id}",
                    category="Requirement",
                    label=_text(requirement.get("title")) or requirement_id,
                    detail=" · ".join(
                        part
                        for part in (requirement_id, status, source)
                        if part
                    ),
                    target_type="requirement",
                    target_id=requirement_id,
                    keywords=(status, source, "compliance", "traceability"),
                    payload=requirement,
                ),
            )

    mappings = snapshot.get("mappings", [])
    if isinstance(mappings, list):
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            mapping_id = _text(mapping.get("id"))
            if not mapping_id:
                continue
            requirement_id = _text(mapping.get("requirement_id"))
            requirement_title = _text(mapping.get("requirement_title"))
            property_name = _text(mapping.get("property_name"))
            analysis_id = _text(mapping.get("analysis_id"))
            subject_ref = _text(mapping.get("subject_ref")) or "project"
            status = _text(mapping.get("status"))
            reference_state = _text(mapping.get("reference_state"))
            label = " → ".join(
                part
                for part in (
                    requirement_title or requirement_id,
                    property_name,
                )
                if part
            ) or mapping_id
            _append_unique(
                entries,
                seen,
                SearchEntry(
                    key=f"mapping:{mapping_id}",
                    category="Evidence Mapping",
                    label=label,
                    detail=" · ".join(
                        part
                        for part in (
                            mapping_id,
                            status,
                            reference_state,
                            subject_ref,
                            analysis_id,
                        )
                        if part
                    ),
                    target_type="mapping",
                    target_id=mapping_id,
                    keywords=(
                        requirement_id,
                        requirement_title,
                        property_name,
                        analysis_id,
                        subject_ref,
                        status,
                        reference_state,
                        "evidence",
                        "mapping",
                        "traceability",
                    ),
                    payload=mapping,
                ),
            )

    for document_index, document in enumerate(proofgraph_documents):
        if not isinstance(document, dict):
            continue
        graph_id = (
            _text(document.get("id") or document.get("graph_sha256"))
            or str(document_index)
        )
        # Persisted verification history stores canonical ProofGraph documents,
        # while older callers/tests may supply the GUI projection shape directly.
        # Route canonical documents through the same validated projection boundary
        # used by the Evidence workspace so search never invents graph semantics.
        nodes = document.get("nodes")
        if isinstance(nodes, list):
            projected_nodes = nodes
        else:
            projected_nodes = proofgraph_projection(document).get("nodes", [])
        for node_index, node in enumerate(projected_nodes):
            if not isinstance(node, dict):
                continue
            node_id = _text(node.get("id") or node.get("key"))
            node_key = _text(node.get("key"))
            label = _text(node.get("label") or node.get("title") or node_id)
            if not label:
                continue
            node_type = _text(node.get("type"))
            status = _text(node.get("status"))
            payload = dict(node)
            payload["_proofgraph_id"] = graph_id
            if node_key:
                payload["_proofgraph_key"] = node_key
            _append_unique(
                entries,
                seen,
                SearchEntry(
                    key=f"proof:{graph_id}:{node_key or node_id or node_index}",
                    category="Evidence",
                    label=label,
                    detail=" · ".join(
                        part for part in (node_type, status, node_id) if part
                    ),
                    target_type="evidence",
                    target_id=node_id,
                    keywords=(
                        node_type,
                        status,
                        node_id,
                        "proofgraph",
                        "evidence",
                        "provenance",
                    ),
                    payload=payload,
                ),
            )

    return entries


class GlobalEngineeringSearch(tk.Toplevel):
    """Keyboard-first search across the currently loaded engineering project."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        entries: list[SearchEntry],
        on_activate: Callable[[SearchEntry], None],
        on_close: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("CleanroomX Global Engineering Search")
        self.geometry("920x590")
        self.minsize(650, 400)
        self.transient(parent.winfo_toplevel())
        self._entries = list(entries)
        self._on_activate = on_activate
        self._on_close = on_close
        self._query_var = tk.StringVar()
        self._category_var = tk.StringVar(value="All")
        self._iid_to_entry: dict[str, SearchEntry] = {}
        self._filtered: list[SearchEntry] = []

        shell = ttk.Frame(self, padding=12)
        shell.pack(fill="both", expand=True)
        header = ttk.Frame(shell, style="CX.PanelHeader.TFrame", padding=(10, 8))
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(
            header,
            text="GLOBAL ENGINEERING SEARCH",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            text="PROJECT · MODEL · ANALYSIS · VERIFICATION · EVIDENCE",
        ).pack(side="right")

        controls = ttk.Frame(shell, padding=(8, 6))
        controls.pack(fill="x", pady=(0, 8))
        ttk.Label(
            controls,
            text="Search",
            style="CX.Section.TLabel",
        ).pack(side="left", padx=(0, 6))
        self.search = ttk.Entry(controls, textvariable=self._query_var)
        self.search.pack(side="left", fill="x", expand=True)
        ttk.Label(controls, text="Area").pack(side="left", padx=(10, 5))
        categories = ["All", *sorted({entry.category for entry in self._entries})]
        self.category = ttk.Combobox(
            controls,
            textvariable=self._category_var,
            values=categories,
            state="readonly",
            width=15,
        )
        self.category.pack(side="left")

        body = ttk.Frame(shell)
        body.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            body,
            columns=("category", "detail"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Engineering entity")
        self.tree.heading("category", text="Area")
        self.tree.heading("detail", text="Engineering context")
        self.tree.column("#0", width=360, minwidth=220)
        self.tree.column("category", width=130, minwidth=100, stretch=False)
        self.tree.column("detail", width=390, minwidth=180)
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        footer = ttk.Frame(shell, padding=(8, 5))
        footer.pack(fill="x", pady=(8, 0))
        self.summary = ttk.Label(footer, text="")
        self.summary.pack(side="left")
        ttk.Label(
            footer,
            text="Enter: navigate · ↑↓: select · Esc: close",
        ).pack(side="right")

        self._query_var.trace_add("write", lambda *_: self._refresh())
        self._category_var.trace_add("write", lambda *_: self._refresh())
        self.search.bind("<Down>", self._focus_first)
        self.search.bind("<Return>", self._activate_first)
        self.tree.bind("<Return>", self._activate_selected)
        self.tree.bind("<Double-1>", self._activate_selected)
        self.bind("<Escape>", self._close)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._refresh()
        self.after_idle(self.search.focus_set)

    def _refresh(self) -> None:
        self._filtered = filter_search_entries(
            self._entries,
            self._query_var.get(),
            category=self._category_var.get(),
        )
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._iid_to_entry.clear()

        for index, entry in enumerate(self._filtered):
            iid = f"result-{index}"
            self._iid_to_entry[iid] = entry
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=entry.label,
                values=(entry.category, entry.detail or "—"),
            )

        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])

        count = len(self._filtered)
        total = len(self._entries)
        self.summary.configure(
            text=f"{count} MATCH{'ES' if count != 1 else ''} · "
            f"{total} INDEXED ENTITIES"
        )

    def _focus_first(self, _event=None):
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self.tree.focus_set()
        return "break"

    def _activate_first(self, _event=None):
        children = self.tree.get_children()
        if not children:
            return "break"
        self.tree.selection_set(children[0])
        self.tree.focus(children[0])
        return self._activate_selected()

    def _activate_selected(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return "break"
        entry = self._iid_to_entry.get(selection[0])
        if entry is None:
            return "break"
        self._close()
        self._on_activate(entry)
        return "break"

    def _close(self, _event=None):
        if self.winfo_exists():
            self.destroy()
        if self._on_close is not None:
            self._on_close()
        return "break"
