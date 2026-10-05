from __future__ import annotations

from collections.abc import Callable
from typing import Any


def bind_dialog_keyboard(
    window: Any,
    *,
    default_action: Callable[[], Any] | None = None,
    cancel_action: Callable[[], Any] | None = None,
) -> None:
    """Apply consistent close/default keyboard behavior to workstation dialogs."""
    cancel = cancel_action or window.destroy

    def on_cancel(_event=None):
        cancel()
        return "break"

    window.bind("<Escape>", on_cancel, add="+")
    try:
        window.protocol("WM_DELETE_WINDOW", cancel)
    except (AttributeError, TypeError):
        pass

    if default_action is None:
        return

    def on_default(_event=None):
        default_action()
        return "break"

    window.bind("<Return>", on_default, add="+")
