from __future__ import annotations

from cleanroomx.gui_dialog import bind_dialog_keyboard


class _FakeWindow:
    def __init__(self):
        self.bindings = {}
        self.protocols = {}
        self.destroyed = False

    def bind(self, event, callback, add=None):
        self.bindings[event] = (callback, add)

    def protocol(self, name, callback):
        self.protocols[name] = callback

    def destroy(self):
        self.destroyed = True


def test_dialog_keyboard_binds_escape_and_window_close() -> None:
    window = _FakeWindow()
    bind_dialog_keyboard(window)

    callback, add = window.bindings["<Escape>"]
    assert add == "+"
    assert callback() == "break"
    assert window.destroyed is True

    window.destroyed = False
    window.protocols["WM_DELETE_WINDOW"]()
    assert window.destroyed is True


def test_dialog_keyboard_invokes_explicit_default_action() -> None:
    window = _FakeWindow()
    called = []
    bind_dialog_keyboard(window, default_action=lambda: called.append("default"))

    callback, add = window.bindings["<Return>"]
    assert add == "+"
    assert callback() == "break"
    assert called == ["default"]


def test_dialog_keyboard_uses_explicit_cancel_action() -> None:
    window = _FakeWindow()
    called = []
    bind_dialog_keyboard(window, cancel_action=lambda: called.append("cancel"))

    callback, _add = window.bindings["<Escape>"]
    callback()
    window.protocols["WM_DELETE_WINDOW"]()
    assert called == ["cancel", "cancel"]
    assert window.destroyed is False
