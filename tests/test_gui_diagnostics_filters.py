from cleanroomx.gui_panels import filter_diagnostic_issues


ISSUES = [
    {
        "sequence": 1,
        "severity": "error",
        "category": "spatial",
        "rule": "spatial.room_overlap",
        "message": "Rooms overlap",
        "element": {"type": "spatial_element", "id": "R-101", "name": "Prep"},
        "details": {"level": "L1"},
    },
    {
        "sequence": 2,
        "severity": "warning",
        "category": "airflow",
        "rule": "airflow.balance",
        "message": "Supply and extract differ",
        "element": {"type": "spatial_element", "id": "R-202", "name": "Fill"},
        "details": {"delta_m3_h": 120.0},
    },
    {
        "sequence": 3,
        "severity": "info",
        "category": "verification",
        "rule": "verification.currency",
        "message": "Result is stale",
        "element": {"type": "analysis", "id": "ACH-1", "name": "ACH Study"},
        "suggested_action": "Run verification again",
    },
]


def test_diagnostic_filter_combines_severity_domain_and_rule():
    assert [
        issue["sequence"]
        for issue in filter_diagnostic_issues(
            ISSUES,
            severity="Warning",
            category="airflow",
            rule="airflow.balance",
        )
    ] == [2]

    assert filter_diagnostic_issues(
        ISSUES,
        severity="Warning",
        category="spatial",
    ) == []


def test_diagnostic_search_requires_all_tokens_across_engineering_context():
    assert [
        issue["sequence"]
        for issue in filter_diagnostic_issues(ISSUES, query="prep l1")
    ] == [1]
    assert [
        issue["sequence"]
        for issue in filter_diagnostic_issues(ISSUES, query="ACH stale")
    ] == [3]
    assert [
        issue["sequence"]
        for issue in filter_diagnostic_issues(ISSUES, query="120 airflow")
    ] == [2]


def test_diagnostic_filter_preserves_issue_objects_and_order():
    visible = filter_diagnostic_issues(ISSUES, category="All", query="")
    assert visible == ISSUES
    assert visible[0] is ISSUES[0]
