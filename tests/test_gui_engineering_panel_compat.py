from __future__ import annotations

from cleanroomx.gui import CleanroomXApp


def test_engineering_panel_refresh_is_optional_for_partial_app_fixture():
    app = CleanroomXApp.__new__(CleanroomXApp)

    assert app._refresh_engineering_panels() is None
    assert app._schedule_project_diagnostics_refresh() is None
