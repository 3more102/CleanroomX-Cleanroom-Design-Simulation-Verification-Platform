from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceProfile:
    """Presentation-only workstation layout for a major engineering workflow."""

    key: str
    label: str
    primary_view: str
    output_view: str | None
    navigator_visible: bool
    output_visible: bool
    inspector_visible: bool
    spatial_mode: str | None = None


_WORKSPACE_PROFILES = {
    "design": WorkspaceProfile(
        key="design",
        label="Design",
        primary_view="design",
        output_view=None,
        navigator_visible=True,
        output_visible=False,
        inspector_visible=True,
        spatial_mode="split",
    ),
    "simulation": WorkspaceProfile(
        key="simulation",
        label="Simulation",
        primary_view="simulation",
        output_view="analysis",
        navigator_visible=True,
        output_visible=True,
        inspector_visible=False,
    ),
    "verification": WorkspaceProfile(
        key="verification",
        label="Verification",
        primary_view="design",
        output_view="problems",
        navigator_visible=True,
        output_visible=True,
        inspector_visible=False,
        spatial_mode="2d",
    ),
    "evidence": WorkspaceProfile(
        key="evidence",
        label="Evidence",
        primary_view="proofgraph",
        output_view="evidence",
        navigator_visible=True,
        output_visible=True,
        inspector_visible=False,
    ),
    "reporting": WorkspaceProfile(
        key="reporting",
        label="Reporting",
        primary_view="reporting",
        output_view="report",
        navigator_visible=False,
        output_visible=True,
        inspector_visible=False,
    ),
}


def workspace_profile_keys() -> tuple[str, ...]:
    return tuple(_WORKSPACE_PROFILES)


def workspace_profile_spec(value: str) -> WorkspaceProfile:
    token = str(value or "").strip().lower()
    return _WORKSPACE_PROFILES.get(token, _WORKSPACE_PROFILES["design"])
