from __future__ import annotations

import json

from cleanroomx.gui_state import (
    GUI_LAYOUT_STATE_VERSION,
    GUI_WORKSPACE_PROFILES,
    clamp_window_size_to_display,
    load_gui_layout_state,
    normalize_gui_layout_state,
    save_gui_layout_state,
)


def test_gui_layout_state_missing_or_malformed_falls_back_safely(tmp_path):
    path = tmp_path / "gui-layout.json"
    state = load_gui_layout_state(path)

    assert state["version"] == GUI_LAYOUT_STATE_VERSION
    assert state["navigator_visible"] is True
    assert state["output_visible"] is True
    assert state["inspector_visible"] is True
    assert state["theme"] == "light"
    assert state["recent_projects"] == []
    assert state["navigator_favorites"] == {}
    assert state["window_width"] == 1440
    assert state["window_height"] == 900
    assert state["navigator_fraction"] == 0.20
    assert state["output_fraction"] == 0.72
    assert state["inspector_fraction"] == 0.78
    assert state["active_workspace"] == "start"
    assert tuple(state["workspace_layouts"]) == GUI_WORKSPACE_PROFILES
    assert state["workspace_layouts"]["start"]["navigator_visible"] is False
    assert state["workspace_layouts"]["start"]["output_visible"] is False
    assert state["workspace_layouts"]["start"]["inspector_visible"] is False
    assert state["workspace_layouts"]["design"]["output_visible"] is False
    assert state["workspace_layouts"]["simulation"]["inspector_visible"] is False
    assert state["workspace_layouts"]["verification"]["output_fraction"] == 0.58
    assert state["workspace_layouts"]["reporting"]["navigator_visible"] is False

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
            "window_width": 640,
            "window_height": "broken",
            "navigator_fraction": 0.31,
            "output_fraction": 2.0,
            "inspector_fraction": float("nan"),
            "active_workspace": "unknown",
            "workspace_layouts": {
                "verification": {
                    "navigator_visible": False,
                    "output_visible": "bad",
                    "inspector_visible": False,
                    "navigator_fraction": 0.27,
                    "output_fraction": 4.0,
                    "inspector_fraction": 0.69,
                },
                "unknown": {"navigator_visible": False},
            },
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
    assert state["window_width"] == 1440
    assert state["window_height"] == 900
    assert state["navigator_fraction"] == 0.31
    assert state["output_fraction"] == 0.72
    assert state["inspector_fraction"] == 0.78
    assert state["active_workspace"] == "start"
    assert tuple(state["workspace_layouts"]) == GUI_WORKSPACE_PROFILES
    verification = state["workspace_layouts"]["verification"]
    assert verification["navigator_visible"] is False
    assert verification["output_visible"] is True
    assert verification["inspector_visible"] is False
    assert verification["navigator_fraction"] == 0.27
    assert verification["output_fraction"] == 0.58
    assert verification["inspector_fraction"] == 0.69
    assert "unknown" not in state["workspace_layouts"]
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
            "window_width": 1680,
            "window_height": 1050,
            "navigator_fraction": 0.25,
            "output_fraction": 0.67,
            "inspector_fraction": 0.81,
            "active_workspace": "evidence",
            "workspace_layouts": {
                "evidence": {
                    "navigator_visible": False,
                    "output_visible": True,
                    "inspector_visible": False,
                    "navigator_fraction": 0.24,
                    "output_fraction": 0.61,
                    "inspector_fraction": 0.79,
                }
            },
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
    assert payload["window_width"] == 1680
    assert payload["window_height"] == 1050
    assert payload["active_workspace"] == "evidence"
    assert payload["workspace_layouts"]["evidence"]["navigator_visible"] is False
    assert payload["workspace_layouts"]["evidence"]["output_fraction"] == 0.61
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


def test_window_size_clamps_to_current_display():
    assert clamp_window_size_to_display(3000, 1800, 1366, 768) == (1366, 768)
    assert clamp_window_size_to_display(1220, 760, 1920, 1080) == (1220, 760)



def test_gui_layout_state_migrates_legacy_global_layout_into_start_workspace():
    state = normalize_gui_layout_state(
        {
            "version": 4,
            "navigator_visible": False,
            "output_visible": True,
            "inspector_visible": False,
            "navigator_fraction": 0.29,
            "output_fraction": 0.64,
            "inspector_fraction": 0.83,
        }
    )

    start = state["workspace_layouts"]["start"]
    assert start == {
        "navigator_visible": False,
        "output_visible": True,
        "inspector_visible": False,
        "navigator_fraction": 0.29,
        "output_fraction": 0.64,
        "inspector_fraction": 0.83,
    }
    assert state["active_workspace"] == "start"


def test_gui_layout_state_keeps_workspace_layouts_independent():
    state = normalize_gui_layout_state(
        {
            "active_workspace": "verification",
            "workspace_layouts": {
                "design": {
                    "navigator_visible": True,
                    "output_visible": False,
                    "inspector_visible": True,
                    "navigator_fraction": 0.19,
                    "output_fraction": 0.75,
                    "inspector_fraction": 0.80,
                },
                "verification": {
                    "navigator_visible": False,
                    "output_visible": True,
                    "inspector_visible": False,
                    "navigator_fraction": 0.28,
                    "output_fraction": 0.62,
                    "inspector_fraction": 0.71,
                },
            },
        }
    )

    assert state["active_workspace"] == "verification"
    assert state["workspace_layouts"]["design"]["navigator_visible"] is True
    assert state["workspace_layouts"]["design"]["output_visible"] is False
    assert state["workspace_layouts"]["verification"]["navigator_visible"] is False
    assert state["workspace_layouts"]["verification"]["output_visible"] is True
    assert state["workspace_layouts"]["verification"]["output_fraction"] == 0.62


def test_gui_layout_state_limits_and_sanitizes_navigator_favorites():
    state = normalize_gui_layout_state(
        {
            "navigator_favorites": {
                f"/projects/project-{project}.cleanroomx.json": [
                    f"room:room-{item}" for item in range(30)
                ]
                + ["room:room-0", "", "bad" + chr(0) + "id"]
                for project in range(20)
            }
        }
    )

    assert len(state["navigator_favorites"]) == 16
    first = state["navigator_favorites"][
        "/projects/project-0.cleanroomx.json"
    ]
    assert len(first) == 24
    assert first[0] == "room:room-0"
    assert first[-1] == "room:room-23"
    assert len(first) == len(set(first))


def test_gui_layout_state_rejects_invalid_navigator_favorite_containers():
    state = normalize_gui_layout_state(
        {
            "navigator_favorites": {
                "": ["room:a"],
                "/valid/project.cleanroomx.json": "not-a-list",
                "/valid/second.cleanroomx.json": ["", 7, "device:fan-1"],
            }
        }
    )

    assert state["navigator_favorites"] == {
        "/valid/second.cleanroomx.json": ["device:fan-1"]
    }
