from cleanroomx.application import AnalysisRun
from cleanroomx.gui import analysis_run_overview
from cleanroomx.gui_theme import status_style_name, theme_palette


def test_dark_theme_uses_industrial_cleanroomx_palette():
    palette = theme_palette("dark")

    assert palette["background"] == "#0B1220"
    assert palette["surface"] == "#111B2E"
    assert palette["panel"] == "#17243A"
    assert palette["elevated"] == "#1D2C45"
    assert palette["border"] == "#263750"
    assert palette["divider_strong"] == "#334A68"
    assert palette["accent"] == "#22D3EE"
    assert palette["success"] == "#22C55E"
    assert palette["warning"] == "#F59E0B"
    assert palette["error"] == "#EF4444"
    assert palette["simulation"] == "#A78BFA"
    assert palette["canvas_2d"] == "#0C1626"
    assert palette["canvas_3d"] == "#08111F"


def test_status_style_name_is_consistent_for_engineering_states():
    assert status_style_name("PASS") == "CX.Pass.TLabel"
    assert status_style_name("verified") == "CX.Verified.TLabel"
    assert status_style_name("FAIL") == "CX.Error.TLabel"
    assert status_style_name("warning") == "CX.Warning.TLabel"
    assert status_style_name("RUNNING") == "CX.Info.TLabel"
    assert status_style_name("STALE") == "CX.Stale.TLabel"
    assert status_style_name("UNVERIFIED") == "CX.Simulation.TLabel"
    assert status_style_name("not checked") == "CX.MutedBadge.TLabel"



def test_analysis_run_overview_separates_configured_and_calculated_values():
    run = AnalysisRun(
        kind="room_verification",
        title="Room verification",
        status="PASS",
        input_snapshot={"room": "CR-104", "required_pressure_pa": 12.5},
        result={"calculated_pressure_pa": 14.2, "status": "PASS"},
        markdown="# report",
        diagnostics={"summary": {"status": "PASS"}},
        plot=None,
    )

    text = analysis_run_overview(run)

    assert "CONFIGURED INPUTS" in text
    assert "required pressure pa: 12.5 Pa" in text
    assert "CALCULATED RESULTS" in text
    assert "calculated pressure pa: 14.2 Pa" in text
    assert "Status reported by backend: PASS" in text
