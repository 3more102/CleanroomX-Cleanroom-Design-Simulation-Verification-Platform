from __future__ import annotations

import json

from cleanroomx.gui_state import (
    GUI_LAYOUT_STATE_VERSION,
    load_gui_layout_state,
    normalize_gui_layout_state,
    save_gui_layout_state,
)


def test_gui_layout_state_missing_or_malformed_falls_back_safely(tmp_path):
    path = tmp_path / "gui-layout.json"
    state = load_gui_layout_state(path)
    assert state == {
        "version": GUI_LAYOUT_STATE_VERSION,
        "navigator_visible": True,
        "output_visible": True,
        "inspector_visible": True,
        "theme": "light",
        "recent_projects": [],
        "navigator_fraction": 0.20,
        "output_fraction": 0.72,
        "inspector_fraction": 0.78,
    }

    path.write_text("{broken", encoding="utf-8")
    assert load_gui_layout_state(path) == state


def test_gui_layout_state_normalization_rejects_bad_types_and_bounds():
    state = normalize_gui_layout_state(
        {
            "version": 999,
            "navigator_visible": False,
            "output_visible": "no",
            "inspector_visible": True,
            "theme": "neon",
            "recent_projects": [
                "alpha.cleanroomx.json",
                "",
                12,
                "bad" + chr(0) + "path",
                "alpha.cleanroomx.json",
                "beta.cleanroomx.json",
            ],
            "navigator_fraction": 0.31,
            "output_fraction": 2.0,
            "inspector_fraction": float("nan"),
            "unexpected": "discard me",
        }
    )

    assert state["version"] == GUI_LAYOUT_STATE_VERSION
    assert state["navigator_visible"] is False
    assert state["output_visible"] is True
    assert state["inspector_visible"] is True
    assert state["theme"] == "light"
    assert state["recent_projects"] == [
        "alpha.cleanroomx.json",
        "beta.cleanroomx.json",
    ]
    assert state["navigator_fraction"] == 0.31
    assert state["output_fraction"] == 0.72
    assert state["inspector_fraction"] == 0.78
    assert "unexpected" not in state


def test_gui_layout_state_round_trip_is_normalized_and_atomic(tmp_path):
    path = tmp_path / "settings" / "gui-layout.json"
    saved = save_gui_layout_state(
        path,
        {
            "navigator_visible": False,
            "output_visible": True,
            "inspector_visible": False,
            "theme": "dark",
            "recent_projects": [
                "/projects/clean-a.cleanroomx.json",
                "/projects/clean-b.cleanroomx.json",
            ],
            "navigator_fraction": 0.25,
            "output_fraction": 0.67,
            "inspector_fraction": 0.81,
        },
    )

    assert saved == path
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == GUI_LAYOUT_STATE_VERSION
    assert payload["navigator_visible"] is False
    assert payload["inspector_visible"] is False
    assert payload["theme"] == "dark"
    assert payload["recent_projects"] == [
        "/projects/clean-a.cleanroomx.json",
        "/projects/clean-b.cleanroomx.json",
    ]
    assert load_gui_layout_state(path) == payload


def test_gui_layout_state_limits_recent_projects_to_eight():
    state = normalize_gui_layout_state(
        {
            "recent_projects": [
                f"/projects/project-{index}.cleanroomx.json"
                for index in range(12)
            ]
        }
    )
    assert len(state["recent_projects"]) == 8
    assert state["recent_projects"][0].endswith("project-0.cleanroomx.json")
    assert state["recent_projects"][-1].endswith("project-7.cleanroomx.json")
