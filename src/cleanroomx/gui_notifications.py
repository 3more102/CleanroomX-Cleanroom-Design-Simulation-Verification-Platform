from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import tkinter as tk
from tkinter import ttk

from .gui_theme import status_style_name


_LEVELS = {"success", "info", "warning", "error"}


def normalize_notification_level(value: Any) -> str:
    token = str(value or "").strip().lower()
    aliases = {
        "pass": "success",
        "passed": "success",
        "ok": "success",
        "informational": "info",
        "warn": "warning",
        "fail": "error",
        "failed": "error",
    }
    token = aliases.get(token, token)
    return token if token in _LEVELS else "info"


def notification_style_name(value: Any) -> str:
    level = normalize_notification_level(value)
    return status_style_name(
        {
            "success": "success",
            "info": "info",
            "warning": "warning",
            "error": "error",
        }[level]
    )


def default_notification_timeout_ms(value: Any) -> int | None:
    level = normalize_notification_level(value)
    if level == "success":
        return 4500
    if level == "info":
        return 6000
    return None


@dataclass(frozen=True)
class NotificationRecord:
    sequence: int
    level: str
    message: str
    detail: str = ""
    persistent: bool = False


class NotificationCenter(ttk.Frame):
    """Non-modal in-app notification banner for workstation feedback.

    Important failures and destructive confirmations remain the controller's
    responsibility. This surface is for success/information and optional
    persistent warnings that should not interrupt engineering work.
    """

    def __init__(self, master: tk.Misc, *, anchor: tk.Misc | None = None):
        super().__init__(
            master,
            style="CX.SubtlePanel.TFrame",
            padding=(8, 5),
        )
        self._anchor = anchor
        self._sequence = 0
        self._history: list[NotificationRecord] = []
        self._dismiss_after_id: str | None = None
        self.level_var = tk.StringVar(value="INFO")
        self.message_var = tk.StringVar(value="")
        self.detail_var = tk.StringVar(value="")
        self._build()
        self.bind("<Configure>", self._on_configure, add="+")

    @property
    def history(self) -> tuple[NotificationRecord, ...]:
        return tuple(self._history)

    @property
    def visible(self) -> bool:
        try:
            return bool(self.winfo_manager())
        except tk.TclError:
            return False

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.level_label = ttk.Label(
            self,
            textvariable=self.level_var,
            style="CX.Status.Info.TLabel",
            anchor="center",
        )
        self.level_label.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 8))

        self.message_label = ttk.Label(
            self,
            textvariable=self.message_var,
            anchor="w",
            justify="left",
        )
        self.message_label.grid(row=0, column=1, sticky="ew")

        self.detail_label = ttk.Label(
            self,
            textvariable=self.detail_var,
            anchor="w",
            justify="left",
            style="CX.ToolbarMuted.TLabel",
        )
        self.detail_label.grid(row=1, column=1, sticky="ew", pady=(2, 0))
        self.detail_label.grid_remove()

        self.close_button = ttk.Button(
            self,
            text="×",
            width=3,
            style="CX.Compact.TButton",
            command=self.dismiss,
            takefocus=True,
        )
        self.close_button.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(8, 0))

    def notify(
        self,
        message: str,
        *,
        level: str = "info",
        detail: str = "",
        persistent: bool | None = None,
        timeout_ms: int | None = None,
    ) -> NotificationRecord:
        clean_message = str(message or "").strip()
        if not clean_message:
            raise ValueError("notification message must not be empty")

        normalized = normalize_notification_level(level)
        if persistent is None:
            persistent = normalized in {"warning", "error"}

        self._sequence += 1
        record = NotificationRecord(
            sequence=self._sequence,
            level=normalized,
            message=clean_message,
            detail=str(detail or "").strip(),
            persistent=bool(persistent),
        )
        self._history.append(record)
        del self._history[:-50]

        self._cancel_dismiss()
        self.level_var.set(normalized.upper())
        self.message_var.set(record.message)
        self.detail_var.set(record.detail)
        self.level_label.configure(style=notification_style_name(normalized))
        if record.detail:
            self.detail_label.grid()
        else:
            self.detail_label.grid_remove()
        self._show()

        effective_timeout = timeout_ms
        if effective_timeout is None and not record.persistent:
            effective_timeout = default_notification_timeout_ms(normalized)
        if effective_timeout is not None and effective_timeout > 0:
            self._dismiss_after_id = self.after(
                int(effective_timeout),
                self.dismiss,
            )
        return record

    def dismiss(self) -> None:
        self._cancel_dismiss()
        try:
            self.pack_forget()
        except tk.TclError:
            pass

    def _show(self) -> None:
        if self.visible:
            return
        options = {
            "fill": "x",
            "padx": 10,
            "pady": (0, 4),
        }
        if self._anchor is not None:
            options["after"] = self._anchor
        self.pack(**options)

    def _cancel_dismiss(self) -> None:
        if self._dismiss_after_id is None:
            return
        try:
            self.after_cancel(self._dismiss_after_id)
        except tk.TclError:
            pass
        self._dismiss_after_id = None

    def _on_configure(self, _event=None) -> None:
        width = max(260, self.winfo_width() - 180)
        try:
            self.message_label.configure(wraplength=width)
            self.detail_label.configure(wraplength=width)
        except tk.TclError:
            pass
