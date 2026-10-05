from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import tkinter as tk
from tkinter import ttk


@dataclass(frozen=True)
class EngineeringSearchItem:
    """One read-only navigation target in the global engineering index."""

    category: str
    title: str
    context: str
    state: str
    target_kind: str
    target_id: str
    keywords: tuple[str, ...] = ()
    payload: Any = field(default=None, compare=False, repr=False)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def build_engineering_search_index(
    *,
    analyses: Iterable[Any] = (),
    spatial_layout: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
    traceability: dict[str, Any] | None = None,
    evidence_records: Iterable[dict[str, Any]] = (),
) -> tuple[EngineeringSearchItem, ...]:
    """Build a deterministic navigation index from existing canonical project state.

    No engineering values are calculated here. The index only exposes identities,
    labels, statuses, and relationships already present in the supplied sources.
    """
    items: list[EngineeringSearchItem] = []

    for analysis in analyses:
        analysis_id = _text(getattr(analysis, "id", ""))
        if not analysis_id:
            continue
        name = _text(getattr(analysis, "name", "")) or analysis_id
        kind = _text(getattr(analysis, "kind", "")) or "analysis"
        items.append(
            EngineeringSearchItem(
                category="Analysis",
                title=name,
                context=f"{kind} · {analysis_id}",
                state="configured",
                target_kind="analysis",
                target_id=analysis_id,
                keywords=(kind, analysis_id),
                payload=analysis,
            )
        )

    layout = spatial_layout if isinstance(spatial_layout, dict) else {}
    for collection, singular, category in (
        ("rooms", "room", "Room"),
        ("devices", "device", "Device"),
    ):
        rows = layout.get(collection)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            item_id = _text(row.get("id"))
            if not item_id:
                continue
            title = _text(row.get("name")) or item_id
            subtype = _text(row.get("type") or row.get("device_type"))
            room_id = _text(row.get("room_id"))
            context_bits = [item_id]
            if subtype:
                context_bits.insert(0, subtype)
            if room_id:
                context_bits.append(f"room {room_id}")
            items.append(
                EngineeringSearchItem(
                    category=category,
                    title=title,
                    context=" · ".join(context_bits),
                    state="model",
                    target_kind=singular,
                    target_id=item_id,
                    keywords=tuple(
                        value
                        for value in (subtype, room_id, _text(row.get("level")))
                        if value
                    ),
                    payload=row,
                )
            )

    diagnostic_data = diagnostics if isinstance(diagnostics, dict) else {}
    issues = diagnostic_data.get("issues")
    if isinstance(issues, list):
        for index, issue in enumerate(issues, start=1):
            if not isinstance(issue, dict):
                continue
            rule = _text(issue.get("rule")) or "diagnostic"
            element = issue.get("element")
            element = element if isinstance(element, dict) else {}
            element_name = (
                _text(element.get("name"))
                or _text(element.get("id"))
                or _text(element.get("type"))
                or "Project"
            )
            sequence = _text(issue.get("sequence")) or str(index)
            severity = _text(issue.get("severity")) or "info"
            message = _text(issue.get("message"))
            items.append(
                EngineeringSearchItem(
                    category="Diagnostic",
                    title=rule,
                    context=f"{element_name} · {message}" if message else element_name,
                    state=severity,
                    target_kind="diagnostic",
                    target_id=sequence,
                    keywords=(
                        _text(issue.get("category")),
                        element_name,
                        _text(issue.get("suggested_action")),
                    ),
                    payload=issue,
                )
            )

    trace = traceability if isinstance(traceability, dict) else {}
    requirements = trace.get("requirements")
    if isinstance(requirements, list):
        for requirement in requirements:
            if not isinstance(requirement, dict):
                continue
            requirement_id = _text(requirement.get("id"))
            if not requirement_id:
                continue
            title = _text(requirement.get("title")) or requirement_id
            requirement_set = requirement.get("set")
            requirement_set = requirement_set if isinstance(requirement_set, dict) else {}
            discipline = _text(requirement.get("discipline"))
            category = _text(requirement.get("category"))
            source = _text(requirement.get("source"))
            state = " · ".join(
                value
                for value in (
                    _text(requirement.get("status")),
                    _text(requirement.get("applicability")),
                )
                if value
            ) or "configured"
            context = " · ".join(
                value
                for value in (
                    _text(requirement_set.get("title")),
                    discipline,
                    category,
                    source,
                )
                if value
            )
            items.append(
                EngineeringSearchItem(
                    category="Requirement",
                    title=title,
                    context=context or requirement_id,
                    state=state,
                    target_kind="requirement",
                    target_id=requirement_id,
                    keywords=(
                        requirement_id,
                        _text(requirement.get("description")),
                        discipline,
                        category,
                        source,
                        _text(requirement.get("reference")),
                    ),
                    payload=requirement,
                )
            )

    for record in evidence_records:
        if not isinstance(record, dict):
            continue
        sequence = record.get("sequence")
        record_id = _text(sequence)
        if not record_id:
            continue
        analysis_name = (
            _text(record.get("analysis_name"))
            or _text(record.get("analysis_id"))
            or "Analysis"
        )
        verification = record.get("verification")
        verification = verification if isinstance(verification, dict) else {}
        status = _text(verification.get("status")) or "unknown"
        completed = _text(record.get("completed_at_utc"))
        items.append(
            EngineeringSearchItem(
                category="Evidence",
                title=f"Record #{record_id} · {analysis_name}",
                context=completed or _text(record.get("analysis_id")),
                state=status,
                target_kind="evidence",
                target_id=record_id,
                keywords=(
                    analysis_name,
                    _text(record.get("analysis_id")),
                    _text(record.get("verification_identity_sha256")),
                    _text(record.get("record_sha256")),
                ),
                payload=record,
            )
        )

    return tuple(
        sorted(
            items,
            key=lambda item: (
                item.category.casefold(),
                item.title.casefold(),
                item.target_id.casefold(),
            ),
        )
    )


def filter_engineering_search_items(
    items: Iterable[EngineeringSearchItem],
    query: str,
    *,
    category: str = "All",
) -> list[EngineeringSearchItem]:
    tokens = tuple(
        token
        for token in _text(query).casefold().split()
        if token
    )
    category_key = _text(category).casefold()
    matches: list[tuple[int, EngineeringSearchItem]] = []
    normalized_query = " ".join(tokens)

    for item in items:
        if category_key and category_key != "all" and item.category.casefold() != category_key:
            continue
        haystack = " ".join(
            (
                item.title,
                item.context,
                item.state,
                item.category,
                item.target_id,
                *item.keywords,
            )
        ).casefold()
        if tokens and not all(token in haystack for token in tokens):
            continue

        title = item.title.casefold()
        target_id = item.target_id.casefold()
        if normalized_query and (title == normalized_query or target_id == normalized_query):
            rank = 0
        elif normalized_query and (
            title.startswith(normalized_query) or target_id.startswith(normalized_query)
        ):
            rank = 1
        elif tokens and all(token in title for token in tokens):
            rank = 2
        else:
            rank = 3
        matches.append((rank, item))

    matches.sort(
        key=lambda pair: (
            pair[0],
            pair[1].category.casefold(),
            pair[1].title.casefold(),
            pair[1].target_id.casefold(),
        )
    )
    return [item for _rank, item in matches]


class GlobalEngineeringSearch(tk.Toplevel):
    """Search and navigate canonical project entities without mutating project state."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        items: Iterable[EngineeringSearchItem],
        on_open: Callable[[EngineeringSearchItem], None],
        on_close: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("CleanroomX Global Engineering Search")
        self.geometry("980x620")
        self.minsize(700, 420)
        self.transient(parent.winfo_toplevel())

        self._items = tuple(items)
        self._filtered: list[EngineeringSearchItem] = []
        self._iid_to_item: dict[str, EngineeringSearchItem] = {}
        self._on_open = on_open
        self._on_close = on_close

        self.query_var = tk.StringVar()
        self.category_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="")
        self.detail_var = tk.StringVar(value="Select a result to inspect its navigation target.")

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
            text="PROJECT ENTITIES · DIAGNOSTICS · REQUIREMENTS · EVIDENCE",
            style="CX.Status.Info.TLabel",
        ).pack(side="right")

        search_host = ttk.Frame(shell, style="CX.SubtlePanel.TFrame", padding=(8, 6))
        search_host.pack(fill="x", pady=(0, 8))
        ttk.Label(search_host, text="Search", style="CX.Section.TLabel").pack(
            side="left", padx=(0, 6)
        )
        self.search = ttk.Entry(search_host, textvariable=self.query_var)
        self.search.pack(side="left", fill="x", expand=True)
        ttk.Label(search_host, text="Type", style="CX.Section.TLabel").pack(
            side="left", padx=(10, 5)
        )
        categories = ("All",) + tuple(
            sorted({item.category for item in self._items}, key=str.casefold)
        )
        self.category_combo = ttk.Combobox(
            search_host,
            textvariable=self.category_var,
            values=categories,
            state="readonly",
            width=16,
        )
        self.category_combo.pack(side="left")

        body = ttk.Panedwindow(shell, orient="vertical")
        body.pack(fill="both", expand=True)

        table_host = ttk.Frame(body, style="CX.Panel.TFrame")
        detail_host = ttk.Frame(body, style="CX.Panel.TFrame", padding=(10, 8))
        body.add(table_host, weight=4)
        body.add(detail_host, weight=1)

        self.tree = ttk.Treeview(
            table_host,
            columns=("type", "context", "state"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.heading("context", text="Engineering context")
        self.tree.heading("state", text="State")
        self.tree.column("#0", width=290, minwidth=180)
        self.tree.column("type", width=120, minwidth=90, stretch=False)
        self.tree.column("context", width=430, minwidth=220)
        self.tree.column("state", width=130, minwidth=90, stretch=False)
        yscroll = ttk.Scrollbar(table_host, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        ttk.Label(
            detail_host,
            text="SELECTION",
            style="CX.PanelSection.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            detail_host,
            textvariable=self.detail_var,
            style="CX.PanelSecondary.TLabel",
            justify="left",
            wraplength=880,
        ).pack(fill="x", pady=(5, 0))

        footer = ttk.Frame(shell, style="CX.Toolbar.TFrame", padding=(8, 5))
        footer.pack(fill="x", pady=(8, 0))
        ttk.Label(
            footer,
            textvariable=self.summary_var,
            style="CX.Status.Neutral.TLabel",
        ).pack(side="left")
        ttk.Label(
            footer,
            text="Enter / double-click  Open · ↓  Results · Esc  Close",
            style="CX.ToolbarMuted.TLabel",
        ).pack(side="right")

        self.query_var.trace_add("write", lambda *_: self._refresh())
        self.category_var.trace_add("write", lambda *_: self._refresh())
        self.search.bind("<Down>", self._focus_first)
        self.search.bind("<Return>", self._open_first)
        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)
        self.tree.bind("<Return>", self._open_selected)
        self.tree.bind("<Double-1>", self._open_selected)
        self.bind("<Escape>", self._close)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._refresh()
        self.after_idle(self.search.focus_set)

    def _refresh(self) -> None:
        self._filtered = filter_engineering_search_items(
            self._items,
            self.query_var.get(),
            category=self.category_var.get(),
        )
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._iid_to_item.clear()

        for index, item in enumerate(self._filtered):
            iid = f"search-{index}"
            self._iid_to_item[iid] = item
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=item.title,
                values=(
                    item.category,
                    item.context or "—",
                    item.state.upper().replace("_", " ") if item.state else "—",
                ),
            )

        count = len(self._filtered)
        total = len(self._items)
        self.summary_var.set(f"{count} / {total} RESULTS")
        children = self.tree.get_children()
        if children:
            first = children[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
        self._selection_changed()

    def selected_item(self) -> EngineeringSearchItem | None:
        selection = self.tree.selection()
        return self._iid_to_item.get(selection[0]) if selection else None

    def _selection_changed(self, _event=None) -> None:
        item = self.selected_item()
        if item is None:
            self.detail_var.set(
                "No result matches the current search and type filter."
                if self.query_var.get().strip()
                else "No project entities are currently indexed."
            )
            return
        self.detail_var.set(
            f"{item.category} · {item.title}\n"
            f"{item.context or 'No additional context'}\n"
            f"Target: {item.target_kind}:{item.target_id}"
        )

    def _focus_first(self, _event=None):
        children = self.tree.get_children()
        if children:
            first = children[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
            self.tree.focus_set()
        return "break"

    def _open_first(self, _event=None):
        children = self.tree.get_children()
        if not children:
            return "break"
        self.tree.selection_set(children[0])
        self.tree.focus(children[0])
        return self._open_selected()

    def _open_selected(self, _event=None):
        item = self.selected_item()
        if item is None:
            return "break"
        callback = self._on_open
        self._close()
        callback(item)
        return "break"

    def _close(self, _event=None):
        if self.winfo_exists():
            self.destroy()
        if self._on_close is not None:
            self._on_close()
        return "break"
