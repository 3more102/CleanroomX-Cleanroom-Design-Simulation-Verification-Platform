from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk


@dataclass(frozen=True)
class EngineeringSearchItem:
    id: str
    label: str
    category: str
    context: str
    callback: Callable[[], None]
    keywords: tuple[str, ...] = ()


def filter_engineering_items(
    items: Iterable[EngineeringSearchItem],
    query: str,
) -> list[EngineeringSearchItem]:
    """Return deterministic token matches without invoking navigation callbacks."""
    tokens = [
        token
        for token in str(query or "").strip().casefold().split()
        if token
    ]
    candidates = list(items)
    if not tokens:
        return candidates
    matches: list[EngineeringSearchItem] = []
    for item in candidates:
        haystack = " ".join(
            (
                item.label,
                item.category,
                item.context,
                *item.keywords,
            )
        ).casefold()
        if all(token in haystack for token in tokens):
            matches.append(item)
    return matches


class GlobalEngineeringSearch(tk.Toplevel):
    """Fast cross-workspace navigation over existing CleanroomX entities."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        items: list[EngineeringSearchItem],
        on_close: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("CleanroomX Global Engineering Search")
        self.geometry("820x520")
        self.minsize(600, 360)
        self.transient(parent.winfo_toplevel())
        self._items = list(items)
        self._filtered: list[EngineeringSearchItem] = []
        self._on_close = on_close
        self._query_var = tk.StringVar()
        self._iid_to_item: dict[str, EngineeringSearchItem] = {}

        shell = ttk.Frame(self, padding=12)
        shell.pack(fill="both", expand=True)
        ttk.Label(
            shell,
            text="GLOBAL ENGINEERING SEARCH",
            style="CX.Section.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            shell,
            text=(
                "Search model objects, analyses, diagnostics, requirements, "
                "and persisted ProofGraph evidence."
            ),
            style="CX.Section.TLabel",
        ).pack(anchor="w", pady=(2, 6))
        self.search = ttk.Entry(shell, textvariable=self._query_var)
        self.search.pack(fill="x", pady=(0, 8))

        body = ttk.Frame(shell)
        body.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            body,
            columns=("category", "context"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Engineering item")
        self.tree.heading("category", text="Category")
        self.tree.heading("context", text="Context")
        self.tree.column("#0", width=330, minwidth=220)
        self.tree.column("category", width=150, minwidth=100, stretch=False)
        self.tree.column("context", width=280, minwidth=180)
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        footer = ttk.Frame(shell)
        footer.pack(fill="x", pady=(8, 0))
        self._summary = ttk.Label(footer, text="")
        self._summary.pack(side="left")
        ttk.Label(footer, text="Enter open  •  Esc close").pack(side="right")

        self._query_var.trace_add("write", lambda *_: self._refresh())
        self.search.bind("<Down>", self._focus_first_result)
        self.search.bind("<Return>", self._invoke_first)
        self.tree.bind("<Return>", self._invoke_selected)
        self.tree.bind("<Double-1>", self._invoke_selected)
        self.bind("<Escape>", self._close)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._refresh()
        self.after_idle(self.search.focus_set)

    def _refresh(self) -> None:
        self._filtered = filter_engineering_items(
            self._items,
            self._query_var.get(),
        )
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._iid_to_item.clear()
        for index, item in enumerate(self._filtered):
            iid = f"engineering-search-{index}"
            self._iid_to_item[iid] = item
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=item.label,
                values=(item.category, item.context or "—"),
            )
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
        count = len(self._filtered)
        self._summary.configure(
            text=f"{count} result{'s' if count != 1 else ''}"
        )

    def _focus_first_result(self, _event=None):
        children = self.tree.get_children()
        if children:
            first = children[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
            self.tree.focus_set()
        return "break"

    def _invoke_first(self, _event=None):
        children = self.tree.get_children()
        if not children:
            return "break"
        self.tree.selection_set(children[0])
        self.tree.focus(children[0])
        return self._invoke_selected()

    def _invoke_selected(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return "break"
        item = self._iid_to_item.get(selection[0])
        if item is None:
            return "break"
        callback = item.callback
        self._close()
        callback()
        return "break"

    def _close(self, _event=None):
        if self.winfo_exists():
            self.destroy()
        if self._on_close is not None:
            self._on_close()
        return "break"
