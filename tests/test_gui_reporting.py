from cleanroomx.gui_reporting import (
    REPORT_CURRENT_ANALYSIS,
    REPORT_PROJECT_DIAGNOSTICS,
    REPORT_PROJECT_DOSSIER,
    REPORT_TYPES,
    ReportPreview,
    normalize_report_preview,
    report_status_semantic,
)


def test_reporting_workspace_exposes_only_supported_authoritative_report_types():
    assert REPORT_TYPES == (
        (REPORT_PROJECT_DOSSIER, "Project Engineering Dossier"),
        (REPORT_PROJECT_DIAGNOSTICS, "Project Diagnostics Report"),
        (REPORT_CURRENT_ANALYSIS, "Current Analysis Report"),
    )


def test_invalid_report_provider_value_fails_closed():
    preview = normalize_report_preview(None, REPORT_PROJECT_DOSSIER)
    assert preview.available is False
    assert preview.status == "unavailable"
    assert preview.content == ""


def test_report_preview_keeps_source_and_availability_explicit():
    preview = ReportPreview(
        report_type=REPORT_PROJECT_DIAGNOSTICS,
        title="Project Diagnostics Report",
        content="# Diagnostics",
        available=True,
        status="ready",
        source="current project diagnostics",
    )
    assert preview.available is True
    assert preview.source == "current project diagnostics"


def test_report_status_semantics_do_not_turn_failures_green():
    assert report_status_semantic("error") == "error"
    assert report_status_semantic("FAIL") == "error"
    assert report_status_semantic("warning") == "warning"
    assert report_status_semantic("stale") == "warning"
    assert report_status_semantic("pass") == "pass"
    assert report_status_semantic("ready") == "pass"
    assert report_status_semantic("unknown") == "neutral"
