from __future__ import annotations

from cleanroomx.gui_search import SearchRecord, filter_search_records


def test_filter_search_records_matches_multiple_terms_and_type():
    records = [
        SearchRecord(
            id="room:r1",
            kind="Room",
            label="ISO 7 Process",
            location="Level 1",
            status="ISO 7",
            keywords=("R-001", "process"),
        ),
        SearchRecord(
            id="analysis:a1",
            kind="Analysis",
            label="Room Verification",
            location="room_verification",
            status="Active",
            keywords=("verification",),
        ),
    ]

    assert [item.id for item in filter_search_records(records, "iso process")] == [
        "room:r1"
    ]
    assert [item.id for item in filter_search_records(records, "verification")] == [
        "analysis:a1"
    ]
    assert filter_search_records(records, "", kind="Room") == [records[0]]
    assert filter_search_records(records, "missing") == []


def test_search_record_search_text_includes_navigation_context():
    record = SearchRecord(
        id="diagnostic:1",
        kind="Diagnostic",
        label="Room overlap",
        location="Process",
        status="error",
        detail="Rule: spatial.room_overlap",
        keywords=("geometry", "room-01"),
    )
    text = record.search_text()
    for expected in (
        "diagnostic",
        "room overlap",
        "process",
        "error",
        "spatial.room_overlap",
        "geometry",
        "room-01",
    ):
        assert expected in text
