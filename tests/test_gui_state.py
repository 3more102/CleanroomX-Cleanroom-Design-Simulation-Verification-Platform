from __future__ import annotations

import json

from cleanroomx.gui_state import (
    GUI_LAYOUT_STATE_VERSION,
    clamp_window_size_to_display,
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
        "theme": "dark",
        "density": "compact",
        "workspace_profile": "design",
        "saved_layouts": {},
        "recent_projects": [],
        "navigator_favorites": {},
        "window_width": 1440,
        "window_height": 900,
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
            "density": "huge",
            "workspace_profile": "unknown",
            "saved_layouts": {
                "Verification review": {
                    "navigator_visible": True,
                    "output_visible": True,
                    "inspector_visible": False,
                    "workspace_profile": "verification",
                    "navigator_fraction": 0.24,
                    "output_fraction": 0.66,
                    "inspector_fraction": 0.80,
                },
                "": {"workspace_profile": "design"},
            },
            "recent_projects": [
                "alpha.cleanroomx.json",
                "",
                12,
                "bad" + chr(0) + "path",
                "alpha.cleanroomx.json",
                "beta.cleanroomx.json",
            ],
            "navigator_favorites": {
                "/projects/alpha.cleanroomx.json": [
                    "nav-diagnostics",
                    "nav-diagnostics",
                    "",
                    42,
                    "room:room-a",
                ],
                "": ["nav-evidence"],
                "/projects/bad.cleanroomx.json": "not-a-list",
            },
            "window_width": 640,
            "window_height": "broken",
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
    assert state["density"] == "compact"
    assert state["workspace_profile"] == "design"
    assert tuple(state["saved_layouts"]) == ("Verification review",)
    assert state["saved_layouts"]["Verification review"]["workspace_profile"] == "verification"
    assert state["saved_layouts"]["Verification review"]["output_fraction"] == 0.66
    assert state["recent_projects"] == [
        "alpha.cleanroomx.json",
        "beta.cleanroomx.json",
    ]
    assert state["navigator_favorites"] == {
        "/projects/alpha.cleanroomx.json": ["nav-diagnostics", "room:room-a"]
    }
    assert state["window_width"] == 1440
    assert state["window_height"] == 900
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
            "density": "comfortable",
            "workspace_profile": "reporting",
            "saved_layouts": {
                "Release": {
                    "navigator_visible": False,
                    "output_visible": True,
                    "inspector_visible": False,
                    "workspace_profile": "reporting",
                    "navigator_fraction": 0.22,
                    "output_fraction": 0.64,
                    "inspector_fraction": 0.79,
                }
            },
            "recent_projects": [
                "/projects/clean-a.cleanroomx.json",
                "/projects/clean-b.cleanroomx.json",
            ],
            "navigator_favorites": {
                "/projects/clean-a.cleanroomx.json": [
                    "nav-diagnostics",
                    "room:room-a",
                ]
            },
            "window_width": 1680,
            "window_height": 1050,
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
    assert payload["density"] == "comfortable"
    assert payload["workspace_profile"] == "reporting"
    assert payload["saved_layouts"]["Release"]["navigator_visible"] is False
    assert payload["saved_layouts"]["Release"]["output_fraction"] == 0.64
    assert payload["recent_projects"] == [
        "/projects/clean-a.cleanroomx.json",
        "/projects/clean-b.cleanroomx.json",
    ]
    assert payload["navigator_favorites"] == {
        "/projects/clean-a.cleanroomx.json": ["nav-diagnostics", "room:room-a"]
    }
    assert payload["window_width"] == 1680
    assert payload["window_height"] == 1050
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



def test_gui_layout_state_limits_named_layouts_and_normalizes_names():
    state = normalize_gui_layout_state(
        {
            "saved_layouts": {
                f" Layout {index} ": {
                    "workspace_profile": "simulation",
                    "navigator_fraction": 0.25,
                    "output_fraction": 0.70,
                    "inspector_fraction": 0.75,
                }
                for index in range(12)
            }
        }
    )

    assert len(state["saved_layouts"]) == 8
    assert "Layout 0" in state["saved_layouts"]
    assert "Layout 7" in state["saved_layouts"]
    assert state["saved_layouts"]["Layout 0"]["workspace_profile"] == "simulation"


def test_gui_layout_state_limits_navigator_favorites():
    state = normalize_gui_layout_state(
        {
            "navigator_favorites": {
                f"/projects/project-{project}.cleanroomx.json": [
                    f"room:room-{item}" for item in range(30)
                ]
                for project in range(20)
            }
        }
    )

    assert len(state["navigator_favorites"]) == 16
    first = state["navigator_favorites"]["/projects/project-0.cleanroomx.json"]
    assert len(first) == 24
    assert first[0] == "room:room-0"
    assert first[-1] == "room:room-23"
