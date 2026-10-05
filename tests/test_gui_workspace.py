from cleanroomx.gui_workspace import workspace_profile_keys, workspace_profile_spec


def test_workspace_profiles_cover_engineering_workflows():
    assert workspace_profile_keys() == (
        "design",
        "simulation",
        "verification",
        "evidence",
        "reporting",
    )
    assert workspace_profile_spec("design").primary_view == "design"
    assert workspace_profile_spec("simulation").output_view == "analysis"
    assert workspace_profile_spec("verification").output_view == "problems"
    assert workspace_profile_spec("evidence").primary_view == "proofgraph"
    assert workspace_profile_spec("reporting").output_view == "report"


def test_workspace_profile_defaults_invalid_values_to_design():
    profile = workspace_profile_spec("not-a-workspace")
    assert profile.key == "design"
    assert profile.navigator_visible is True
    assert profile.inspector_visible is True
