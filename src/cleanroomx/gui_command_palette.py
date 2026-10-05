from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Iterable
import tkinter as tk
from tkinter import ttk


@dataclass(frozen=True)
class PaletteCommand:
    id: str
    label: str
    category: str
    callback: Callable[[], None]
    shortcut: str = ""
    keywords: tuple[str, ...] = ()


def filter_commands(
    commands: Iterable[PaletteCommand],
    query: str,
) -> list[PaletteCommand]:
    """Return deterministic command-palette matches without executing commands."""
    tokens = [
        token
        for token in str(query or "").strip().casefold().split()
        if token
    ]
    items = list(commands)
    if not tokens:
        return items

    matches: list[PaletteCommand] = []
    for command in items:
        haystack = " ".join(
            (
                command.label,
                command.category,
                command.shortcut,
                *command.keywords,
            )
        ).casefold()
        if all(token in haystack for token in tokens):
            matches.append(command)
    return matches


class CommandPalette(tk.Toplevel):
    """Searchable dispatcher over existing application/controller commands."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        commands: list[PaletteCommand],
        on_close: Callable[[], None] | None = None,
    ):
        super().__init__(parent)
        self.title("CleanroomX Commands")
        self.geometry("720x470")
        self.minsize(560, 340)
        self.transient(parent.winfo_toplevel())
        self._commands = list(commands)
        self._filtered: list[PaletteCommand] = []
        self._on_close = on_close
        self._query_var = tk.StringVar()
        self._iid_to_command: dict[str, PaletteCommand] = {}

        shell = ttk.Frame(self, padding=12)
        shell.pack(fill="both", expand=True)

        header = ttk.Frame(shell, style="CX.PanelHeader.TFrame", padding=(10, 8))
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(
            header,
            text="COMMAND PALETTE",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            text="GLOBAL WORKSTATION ACTIONS",
            style="CX.Status.Info.TLabel",
        ).pack(side="right")

        search_host = ttk.Frame(shell, style="CX.SubtlePanel.TFrame", padding=(8, 6))
        search_host.pack(fill="x", pady=(0, 8))
        ttk.Label(
            search_host,
            text="Search",
            style="CX.Section.TLabel",
        ).pack(side="left", padx=(0, 8))
        self.search = ttk.Entry(search_host, textvariable=self._query_var)
        self.search.pack(side="left", fill="x", expand=True)
        ttk.Label(
            search_host,
            text="name · category · shortcut · keyword",
            style="CX.Muted.TLabel",
        ).pack(side="right", padx=(10, 0))

        body = ttk.Frame(shell, style="CX.Panel.TFrame")
        body.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            body,
            columns=("category", "shortcut"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Command")
        self.tree.heading("category", text="Engineering Area")
        self.tree.heading("shortcut", text="Shortcut")
        self.tree.column("#0", width=360, minwidth=220)
        self.tree.column("category", width=170, minwidth=110)
        self.tree.column("shortcut", width=130, minwidth=90, stretch=False)
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        footer = ttk.Frame(shell, style="CX.Toolbar.TFrame", padding=(8, 5))
        footer.pack(fill="x", pady=(8, 0))
        self._summary = ttk.Label(
            footer,
            text="",
            style="CX.Status.Neutral.TLabel",
        )
        self._summary.pack(side="left")
        self._empty_hint = ttk.Label(
            footer,
            text="",
            style="CX.ToolbarMuted.TLabel",
        )
        self._empty_hint.pack(side="left", padx=(8, 0))
        ttk.Label(
            footer,
            text="Enter  Run  ·  ↓  Results  ·  Esc  Close",
            style="CX.ToolbarMuted.TLabel",
        ).pack(side="right")

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
        self._filtered = filter_commands(self._commands, self._query_var.get())
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._iid_to_command.clear()

        previous_category = None
        for index, command in enumerate(self._filtered):
            iid = f"command-{index}"
            self._iid_to_command[iid] = command
            category = command.category or "General"
            category_changed = category != previous_category
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=command.label,
                values=(category, command.shortcut or "—"),
                tags=("category_break",) if category_changed and index else (),
            )
            previous_category = category

        if self._filtered:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
            self._empty_hint.configure(text="")
        else:
            query = self._query_var.get().strip()
            self._empty_hint.configure(
                text=(
                    f'No command matches "{query}".'
                    if query
                    else "No commands are registered."
                )
            )

        count = len(self._filtered)
        self._summary.configure(
            text=f"{count} COMMAND{'S' if count != 1 else ''}"
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
        command = self._iid_to_command.get(selection[0])
        if command is None:
            return "break"
        callback = command.callback
        self._close()
        callback()
        return "break"

    def _close(self, _event=None):
        if self.winfo_exists():
            self.destroy()
        if self._on_close is not None:
            self._on_close()
        return "break"
