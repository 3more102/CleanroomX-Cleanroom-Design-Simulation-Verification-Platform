from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
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


def _subsequence_gap(needle: str, haystack: str) -> int | None:
    """Return the minimum gap cost for an ordered fuzzy match, or None."""
    if not needle:
        return 0

    # Keep every possible end position for the current prefix. A greedy
    # left-most match can miss a much tighter later subsequence (for example,
    # "aa" inside "analysis"), which in turn makes palette ranking surprising.
    costs = {
        index: 0
        for index, character in enumerate(haystack)
        if character == needle[0]
    }
    if not costs:
        return None

    for character in needle[1:]:
        next_costs: dict[int, int] = {}
        for index, candidate in enumerate(haystack):
            if candidate != character:
                continue
            best: int | None = None
            for previous_index, previous_cost in costs.items():
                if previous_index >= index:
                    continue
                cost = previous_cost + index - previous_index - 1
                if best is None or cost < best:
                    best = cost
            if best is not None:
                next_costs[index] = best
        if not next_costs:
            return None
        costs = next_costs

    return min(costs.values())


def _command_match_score(command: PaletteCommand, token: str) -> int | None:
    label = command.label.casefold()
    category = command.category.casefold()
    shortcut = command.shortcut.casefold()
    keywords = tuple(keyword.casefold() for keyword in command.keywords)
    label_words = label.split()

    if token == label:
        return 140
    if label.startswith(token):
        return 125
    if any(word == token for word in label_words):
        return 118
    if any(word.startswith(token) for word in label_words):
        return 108
    if token in label:
        return 96

    if shortcut:
        if token == shortcut:
            return 92
        if token in shortcut:
            return 88

    if token in keywords:
        return 84
    if any(keyword.startswith(token) for keyword in keywords):
        return 78
    if any(token in keyword for keyword in keywords):
        return 72

    if token == category:
        return 66
    if category.startswith(token):
        return 60
    if token in category:
        return 54

    # Low-priority fuzzy fallback keeps terse IDE-style queries useful without
    # allowing weak matches to outrank real substring/prefix matches.
    if len(token) >= 2:
        compact_label = "".join(character for character in label if character.isalnum())
        gap = _subsequence_gap(token, compact_label)
        if gap is not None:
            return max(20, 42 - min(gap, 22))
    return None


def filter_commands(
    commands: Iterable[PaletteCommand],
    query: str,
) -> list[PaletteCommand]:
    """Return deterministic, relevance-ranked command-palette matches."""
    normalized_query = str(query or "").strip().casefold()
    tokens = [token for token in normalized_query.split() if token]
    items = list(commands)
    if not tokens:
        return items

    scored: list[tuple[int, int, PaletteCommand]] = []
    for index, command in enumerate(items):
        token_scores: list[int] = []
        for token in tokens:
            score = _command_match_score(command, token)
            if score is None:
                break
            token_scores.append(score)
        else:
            total = sum(token_scores)
            label = command.label.casefold()
            if normalized_query and normalized_query in label:
                total += 24
            scored.append((total, index, command))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [command for _score, _index, command in scored]


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
        self.geometry("680x430")
        self.minsize(520, 320)
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
            text="Enter run  •  ↑/↓ navigate  •  Esc clear / close",
        ).pack(side="right")

        self._query_var.trace_add("write", lambda *_: self._refresh())
        self.search.bind("<Down>", self._focus_first_result)
        self.search.bind("<Up>", self._focus_last_result)
        self.search.bind("<Return>", self._invoke_first)
        self.tree.bind("<Return>", self._invoke_selected)
        self.tree.bind("<Double-1>", self._invoke_selected)
        self.bind("<Escape>", self._escape)
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
                f"{len(self._filtered)} command"
                f"{'s' if len(self._filtered) != 1 else ''}"
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

    def _focus_last_result(self, _event=None):
        children = self.tree.get_children()
        if children:
            last = children[-1]
            self.tree.selection_set(last)
            self.tree.focus(last)
            self.tree.see(last)
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

    def _escape(self, _event=None):
        if self._query_var.get():
            self._query_var.set("")
            self.search.focus_set()
            return "break"
        return self._close()

    def _close(self, _event=None):
        if self.winfo_exists():
            self.destroy()
        if self._on_close is not None:
            self._on_close()
        return "break"
