from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_gui_user_preferences(request, monkeypatch, tmp_path):
    """Keep GUI tests from reading or writing the developer's real preferences."""
    if "gui" not in request.node.path.name.lower():
        return

    import cleanroomx.gui as gui_module

    state_path = tmp_path / "cleanroomx-test-gui-layout.json"
    monkeypatch.setattr(
        gui_module,
        "default_gui_layout_state_path",
        lambda: state_path,
    )
