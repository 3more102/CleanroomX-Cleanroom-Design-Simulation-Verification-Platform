from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable


@dataclass(frozen=True)
class SearchRecord:
    id: str
    kind: str
    label: str
    location: str = ""
    status: str = ""
    detail: str = ""
    keywords: tuple[str, ...] = ()
    payload: Any = None

    def search_text(self) -> str:
        return " ".join(
            (
                self.kind,
                self.label,
                self.location,
                self.status,
                self.detail,
                *self.keywords,
            )
        ).casefold()


def filter_search_records(
    records: list[SearchRecord] | tuple[SearchRecord, ...],
    query: str,
    kind: str = "All",
) -> list[SearchRecord]:
    terms = [part for part in str(query).strip().casefold().split() if part]
    kind_filter = str(kind or "All").strip().casefold()
    visible: list[SearchRecord] = []
    for record in records:
        if kind_filter not in {"", "all"} and record.kind.casefold() != kind_filter:
            continue
        haystack = record.search_text()
        if all(term in haystack for term in terms):
            visible.append(record)
    return visible


class EngineeringSearch(tk.Toplevel):
    """Cross-domain search over already-validated CleanroomX GUI projections."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        records: list[SearchRecord] | tuple[SearchRecord, ...],
        navigate: Callable[[SearchRecord], None],
        on_close: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self.title("CleanroomX Engineering Search")
        self.geometry("1040x620")
        self.minsize(760, 440)
        self.transient(parent)
        self._records = list(records)
        self._navigate = navigate
        self._on_close = on_close
        self._iid_to_record: dict[str, SearchRecord] = {}

        self.query_var = tk.StringVar()
        self.kind_var = tk.StringVar(value="All")
        self.count_var = tk.StringVar()

        header = ttk.Frame(self, padding=(12, 10, 12, 6))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="ENGINEERING SEARCH",
            style="CX.Section.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            text="Objects · analyses · requirements · diagnostics · evidence",
        ).pack(side="right")

        filters = ttk.Frame(self, padding=(12, 0, 12, 6))
        filters.pack(fill="x")
        ttk.Label(filters, text="Search").pack(side="left")
        self.search_entry = ttk.Entry(
            filters,
            textvariable=self.query_var,
            width=40,
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(6, 10))

        kinds = sorted(
            {record.kind for record in self._records if record.kind},
            key=str.casefold,
        )
        ttk.Label(filters, text="Type").pack(side="left")
        self.kind_combo = ttk.Combobox(
            filters,
            textvariable=self.kind_var,
            values=("All", *kinds),
            state="readonly",
            width=18,
        )
        self.kind_combo.pack(side="left", padx=(6, 8))
        ttk.Button(filters, text="Clear", command=self._clear).pack(side="left")
        ttk.Label(filters, textvariable=self.count_var).pack(side="right", padx=(10, 0))

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        list_frame = ttk.Frame(body)
        body.add(list_frame, weight=3)
        self.tree = ttk.Treeview(
            list_frame,
            columns=("type", "location", "status"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Result")
        self.tree.heading("type", text="Type")
        self.tree.heading("location", text="Location / Source")
        self.tree.heading("status", text="Status")
        self.tree.column("#0", width=390, minwidth=240)
        self.tree.column("type", width=130, stretch=False)
        self.tree.column("location", width=320, minwidth=180)
        self.tree.column("status", width=120, stretch=False)
        yscroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        detail_frame = ttk.Frame(body)
        body.add(detail_frame, weight=1)
        self.detail = tk.Text(detail_frame, height=8, wrap="word", state="disabled")
        detail_scroll = ttk.Scrollbar(
            detail_frame,
            orient="vertical",
            command=self.detail.yview,
        )
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

        buttons = ttk.Frame(self, padding=(12, 0, 12, 10))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Close", command=self._close).pack(side="right")
        self.open_button = ttk.Button(
            buttons,
            text="Open",
            style="CX.Primary.TButton",
            command=self._open_selected,
        )
        self.open_button.pack(side="right", padx=(0, 6))

        self.query_var.trace_add("write", lambda *_: self._refresh())
        self.kind_var.trace_add("write", lambda *_: self._refresh())
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_detail())
        self.tree.bind("<Double-1>", self._open_selected)
        self.tree.bind("<Return>", self._open_selected)
        self.bind("<Escape>", lambda _event: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._refresh()
        self.search_entry.focus_set()

    def _clear(self) -> None:
        self.query_var.set("")
        self.kind_var.set("All")
        self.search_entry.focus_set()

    def _visible_records(self) -> list[SearchRecord]:
        return filter_search_records(
            self._records,
            self.query_var.get(),
            self.kind_var.get(),
        )

    def _refresh(self) -> None:
        previous = self.tree.selection()
        previous_record_id = None
        if previous:
            record = self._iid_to_record.get(previous[0])
            previous_record_id = record.id if record is not None else None

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._iid_to_record.clear()

        visible = self._visible_records()
        target = None
        for index, record in enumerate(visible):
            iid = f"search:{index}"
            self._iid_to_record[iid] = record
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=record.label,
                values=(record.kind, record.location, record.status),
            )
            if record.id == previous_record_id:
                target = iid

        self.count_var.set(f"{len(visible)} of {len(self._records)}")
        children = self.tree.get_children()
        if target is None and children:
            target = children[0]
        if target is not None:
            self.tree.selection_set(target)
            self.tree.focus(target)
            self.tree.see(target)
        self.open_button.configure(state="normal" if children else "disabled")
        self._show_detail()

    def _selected_record(self) -> SearchRecord | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._iid_to_record.get(selection[0])

    def _show_detail(self) -> None:
        record = self._selected_record()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if record is None:
            if self._records and not self._visible_records():
                self.detail.insert("1.0", "No engineering records match the active filters.")
            else:
                self.detail.insert("1.0", "No searchable engineering records are available.")
        else:
            lines = [
                f"{record.kind.upper()}",
                record.label,
            ]
            if record.location:
                lines.append(f"Location / Source: {record.location}")
            if record.status:
                lines.append(f"Status: {record.status}")
            if record.detail:
                lines.extend(("", record.detail))
            self.detail.insert("1.0", "\n".join(lines))
        self.detail.configure(state="disabled")

    def _open_selected(self, _event=None):
        record = self._selected_record()
        if record is None:
            return "break"
        self._navigate(record)
        self._close()
        return "break"

    def _close(self) -> None:
        if self._on_close is not None:
            self._on_close()
        self.destroy()
