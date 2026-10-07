from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Iterable
import tkinter as tk
from tkinter import ttk

from .gui_windowing import fit_window_to_display


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

    matches: list[tuple[int, PaletteCommand]] = []
    phrase = " ".join(tokens)
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
            label = " ".join(command.label.casefold().split())
            if label == phrase:
                rank = 0
            elif label.startswith(phrase):
                rank = 1
            elif all(token in label for token in tokens):
                rank = 2
            else:
                rank = 3
            matches.append((rank, command))
    # Stable sorting keeps configured command order within the same rank.
    matches.sort(key=lambda item: item[0])
    return [command for _rank, command in matches]


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
        self.title("CleanroomX Command Palette")
        fit_window_to_display(
            self,
            preferred_width=680,
            preferred_height=430,
            minimum_width=520,
            minimum_height=320,
        )
        self.transient(parent.winfo_toplevel())
        self._commands = list(commands)
        self._filtered: list[PaletteCommand] = []
        self._on_close = on_close
        self._query_var = tk.StringVar()
        self._iid_to_command: dict[str, PaletteCommand] = {}

        shell = ttk.Frame(self, padding=12)
        shell.pack(fill="both", expand=True)
        ttk.Label(
            shell,
            text="COMMAND PALETTE",
            style="CX.Section.TLabel",
        ).pack(anchor="w")
        self.search = ttk.Entry(shell, textvariable=self._query_var)
        self.search.pack(fill="x", pady=(6, 8))

        body = ttk.Frame(shell)
        body.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            body,
            columns=("category", "shortcut"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Command")
        self.tree.heading("category", text="Category")
        self.tree.heading("shortcut", text="Shortcut")
        self.tree.column("#0", width=330, minwidth=220)
        self.tree.column("category", width=145, minwidth=100)
        self.tree.column("shortcut", width=120, minwidth=90, stretch=False)
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        footer = ttk.Frame(shell)
        footer.pack(fill="x", pady=(8, 0))
        self._summary = ttk.Label(footer, text="")
        self._summary.pack(side="left")
        ttk.Label(
            footer,
            text="Enter run  •  Esc close",
        ).pack(side="right")

        self._query_var.trace_add("write", lambda *_: self._refresh())
        self.search.bind("<Down>", self._focus_first_result)
        self.search.bind("<Return>", self._invoke_first)
        self.tree.bind("<Return>", self._invoke_selected)
        self.tree.bind("<Up>", self._return_to_search)
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

        for index, command in enumerate(self._filtered):
            iid = f"command-{index}"
            self._iid_to_command[iid] = command
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=command.label,
                values=(command.category, command.shortcut or "—"),
            )
        if self._filtered:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
        self._summary.configure(
            text=(
                f"{len(self._filtered)} command{'s' if len(self._filtered) != 1 else ''}"
                if self._filtered else "No matching commands. Try a workflow name."
            )
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

    def _return_to_search(self, _event=None):
        children = self.tree.get_children()
        if not children or self.tree.focus() == children[0]:
            self.search.focus_set()
            return "break"
        return None

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
