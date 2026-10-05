from cleanroomx.gui_overview import engineering_overview_snapshot


def test_engineering_overview_snapshot_reports_clean_backend_state() -> None:
    snapshot = engineering_overview_snapshot(
        project_name="Pilot Suite",
        project_path="/tmp/pilot.cleanroomx.json",
        analysis_count=3,
        diagnostics={"summary": {"error_count": 0, "warning_count": 0}},
        verification_currency={
            "summary": {
                "configured_analysis_count": 3,
                "current_count": 3,
                "stale_count": 0,
                "not_verified_count": 0,
                "not_configured_count": 0,
                "dependency_freshness_unverifiable_count": 0,
            }
        },
        evidence_record_count=4,
        running=False,
        unsaved=False,
    )

    assert snapshot["overall"]["state"] == "pass"
    assert snapshot["overall"]["text"] == "Workspace ready"
    cards = {card["id"]: card for card in snapshot["cards"]}
    assert cards["diagnostics"]["state"] == "pass"
    assert cards["verification"]["value"] == "3/3 current"
    assert cards["evidence"]["value"] == "4"
    assert snapshot["actions"][0]["title"] == "No immediate workstation actions"


def test_engineering_overview_snapshot_surfaces_actionable_attention() -> None:
    snapshot = engineering_overview_snapshot(
        project_name="Production",
        project_path=None,
        analysis_count=5,
        diagnostics={"summary": {"error_count": 2, "warning_count": 3}},
        verification_currency={
            "summary": {
                "configured_analysis_count": 4,
                "current_count": 1,
                "stale_count": 1,
                "not_verified_count": 2,
                "not_configured_count": 1,
                "dependency_freshness_unverifiable_count": 1,
            }
        },
        evidence_record_count=0,
        running=True,
        unsaved=True,
    )

    assert snapshot["overall"]["state"] == "fail"
    cards = {card["id"]: card for card in snapshot["cards"]}
    assert cards["diagnostics"]["value"] == "2E · 3W"
    assert cards["verification"]["state"] == "warning"
    assert cards["execution"]["state"] == "running"
    assert cards["project"]["value"] == "Unsaved"

    targets = [action["target"] for action in snapshot["actions"]]
    assert targets.count("problems") == 2
    assert "verification" in targets
    assert "simulation" in targets
    assert "evidence" in targets
    assert "save" in targets


def test_engineering_overview_snapshot_does_not_turn_unavailable_data_into_zero() -> None:
    snapshot = engineering_overview_snapshot(
        project_name="Unknown State",
        project_path=None,
        analysis_count=0,
        diagnostics=None,
        verification_currency=None,
        evidence_record_count=None,
        running=False,
        unsaved=False,
    )

    assert snapshot["overall"]["state"] == "warning"
    cards = {card["id"]: card for card in snapshot["cards"]}
    assert cards["diagnostics"]["value"] == "Unavailable"
    assert cards["diagnostics"]["detail"] == "Diagnostics unavailable"
    assert cards["verification"]["value"] == "Unavailable"
    assert cards["verification"]["detail"] == "Verification currency unavailable"
    assert cards["evidence"]["value"] == "Unavailable"
    assert cards["evidence"]["detail"] == "Verification evidence history unavailable"
    titles = {action["title"] for action in snapshot["actions"]}
    assert "Project diagnostics unavailable" in titles
    assert "Verification currency unavailable" in titles
    assert "Verification evidence history unavailable" in titles
    assert "No retained verification evidence" not in titles



def test_engineering_overview_requires_attention_for_missing_persisted_evidence() -> None:
    snapshot = engineering_overview_snapshot(
        project_name="Evidence Gap",
        project_path="/tmp/evidence.cleanroomx.json",
        analysis_count=1,
        diagnostics={"summary": {"error_count": 0, "warning_count": 0}},
        verification_currency={
            "summary": {
                "configured_analysis_count": 1,
                "current_count": 1,
                "stale_count": 0,
                "not_verified_count": 0,
                "not_configured_count": 0,
                "dependency_freshness_unverifiable_count": 0,
            }
        },
        evidence_record_count=0,
        running=False,
        unsaved=False,
    )

    assert snapshot["overall"]["state"] == "warning"
    assert any(
        action["title"] == "No retained verification evidence"
        for action in snapshot["actions"]
    )


def test_engineering_overview_marks_unconfigured_verification_as_attention() -> None:
    snapshot = engineering_overview_snapshot(
        project_name="Coverage Gap",
        project_path="/tmp/coverage.cleanroomx.json",
        analysis_count=2,
        diagnostics={"summary": {"error_count": 0, "warning_count": 0}},
        verification_currency={
            "summary": {
                "configured_analysis_count": 1,
                "current_count": 1,
                "stale_count": 0,
                "not_verified_count": 0,
                "not_configured_count": 1,
                "dependency_freshness_unverifiable_count": 0,
            }
        },
        evidence_record_count=1,
        running=False,
        unsaved=False,
    )

    cards = {card["id"]: card for card in snapshot["cards"]}
    assert snapshot["overall"]["state"] == "warning"
    assert cards["verification"]["state"] == "warning"
    assert "1 unconfigured" in cards["verification"]["detail"]
