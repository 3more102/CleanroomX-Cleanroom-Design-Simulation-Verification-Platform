from cleanroomx.gui_reporting import (
    REPORT_CURRENT_ANALYSIS,
    REPORT_PROJECT_DIAGNOSTICS,
    REPORT_PROJECT_DOSSIER,
    REPORT_TYPES,
    ReportPreview,
    normalize_report_preview,
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
