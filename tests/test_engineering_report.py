from __future__ import annotations

import copy
from hashlib import sha256
import json
import re

import pytest

from cleanroomx.application import run_analysis
from cleanroomx.engineering_report import (
    ENGINEERING_REPORT_SCHEMA,
    EngineeringReportFreshnessError,
    build_engineering_report_payload,
    engineering_report_html,
    engineering_report_markdown,
    verify_engineering_report_payload,
)


def _room_payload() -> dict:
    return {
        "name": "Process <A>",
        "length_m": 6.0,
        "width_m": 5.0,
        "height_m": 3.0,
        "supply_airflow_m3_h": 2700.0,
        "min_ach": 25.0,
        "observed_pressure_pa": 30.0,
    }


def _run():
    payload = _room_payload()
    return payload, run_analysis("room_verification", payload)


def _embedded_payload(document: str) -> dict:
    match = re.search(
        r'<script id="cleanroomx-report-evidence" type="application/json">\n(.*?)\n</script>',
        document,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_engineering_report_is_deterministic_self_contained_and_verifiable():
    input_payload, run = _run()

    first = engineering_report_html(
        run,
        project_name="Facility",
        project_description="Review package",
        analysis_id="room-a",
        analysis_name="Room A",
        analysis_kind="room_verification",
        input_payload=input_payload,
        generated_at_utc="2026-09-25T12:00:00Z",
    )
    second = engineering_report_html(
        run,
        project_name="Facility",
        project_description="Review package",
        analysis_id="room-a",
        analysis_name="Room A",
        analysis_kind="room_verification",
        input_payload=copy.deepcopy(input_payload),
        generated_at_utc="2026-09-25T12:00:00Z",
    )

    assert first == second
    assert first.startswith("<!doctype html>\n")
    assert "http://" not in first
    assert "https://" not in first
    assert "<script src=" not in first
    embedded = _embedded_payload(first)
    assert embedded["schema"] == ENGINEERING_REPORT_SCHEMA
    assert embedded["analysis"]["input_sha256"] == (
        run.diagnostics["application_execution_provenance"]["input_sha256"]
    )
    assert verify_engineering_report_payload(embedded) is True


def test_engineering_report_rejects_stale_analysis_input():
    input_payload, run = _run()
    changed = copy.deepcopy(input_payload)
    changed["supply_airflow_m3_h"] += 1.0

    with pytest.raises(EngineeringReportFreshnessError, match="no longer matches"):
        engineering_report_html(
            run,
            project_name="Facility",
            project_description="",
            analysis_id="room-a",
            analysis_name="Room A",
            analysis_kind="room_verification",
            input_payload=changed,
        )


def test_engineering_report_payload_detects_tampering():
    input_payload, run = _run()
    payload = build_engineering_report_payload(
        run,
        project_name="Facility",
        project_description="",
        analysis_id="room-a",
        analysis_name="Room A",
        analysis_kind="room_verification",
        input_payload=input_payload,
    )
    assert verify_engineering_report_payload(payload) is True

    payload["result"]["ach_1_h"] = 999
    assert verify_engineering_report_payload(payload) is False


def test_engineering_report_payload_rejects_rehashed_input_identity_mismatch():
    input_payload, run = _run()
    payload = build_engineering_report_payload(
        run,
        project_name="Facility",
        project_description="",
        analysis_id="room-a",
        analysis_name="Room A",
        analysis_kind="room_verification",
        input_payload=input_payload,
    )

    payload["input"]["supply_airflow_m3_h"] += 1.0
    unsigned = copy.deepcopy(payload)
    unsigned.pop("integrity")
    payload["integrity"]["sha256"] = sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert verify_engineering_report_payload(payload) is False


def test_engineering_report_escapes_html_in_human_and_machine_sections():
    input_payload, run = _run()
    injected = '</script><script>alert("x")</script>'

    document = engineering_report_html(
        run,
        project_name=injected,
        project_description="<b>unsafe</b>",
        analysis_id="room-a",
        analysis_name="<img src=x onerror=alert(1)>",
        analysis_kind="room_verification",
        input_payload=input_payload,
    )

    assert injected not in document
    assert "<img src=x onerror=alert(1)>" not in document
    assert "&lt;img src=x onerror=alert(1)&gt;" in document
    embedded = _embedded_payload(document)
    assert embedded["project"]["name"] == injected


def test_engineering_report_payload_rejects_non_json_project_description_type():
    input_payload, run = _run()

    with pytest.raises(TypeError, match="project_description"):
        build_engineering_report_payload(
            run,
            project_name="Facility",
            project_description=None,
            analysis_id="room-a",
            analysis_name="Room A",
            analysis_kind="room_verification",
            input_payload=input_payload,
        )


def test_engineering_report_preserves_release2_identity_timestamp_and_limitations():
    input_payload, run = _run()
    payload = build_engineering_report_payload(
        run,
        project_name="Facility",
        project_description="Review package",
        analysis_id="room-a",
        analysis_name="Room A",
        analysis_kind="room_verification",
        input_payload=input_payload,
        generated_at_utc="2026-09-25T12:34:56Z",
    )

    assert payload["generated_at_utc"] == "2026-09-25T12:34:56Z"
    assert len(payload["project"]["state_sha256"]) == 64
    assert payload["analysis"]["run_sha256"] == run.to_dict()["integrity"]["sha256"]
    assert payload["plot"] == run.to_dict()["plot"]
    assert payload["limitations"]
    assert verify_engineering_report_payload(payload) is True


def test_unified_markdown_report_uses_verified_report_payload():
    input_payload, run = _run()
    document = engineering_report_markdown(
        run,
        project_name="Facility",
        project_description="Review package",
        analysis_id="room-a",
        analysis_name="Room A",
        analysis_kind="room_verification",
        input_payload=input_payload,
        generated_at_utc="2026-09-25T12:34:56Z",
    )

    assert document.startswith("# Room A — CleanroomX Engineering Report\n")
    assert "Generated UTC: 2026-09-25T12:34:56Z" in document
    assert "Run SHA-256:" in document
    assert "Project state SHA-256:" in document
    assert "## Limitations" in document
    assert "## Traceability evidence" in document

def test_unified_markdown_report_escapes_metadata_and_limitations():
    input_payload, run = _run()

    document = engineering_report_markdown(
        run,
        project_name="Facility | table\n# forged-project <script>alert(1)</script>",
        project_description="",
        analysis_id="room-a\n- forged-id",
        analysis_name="Room *unsafe*\n# forged-analysis <img>",
        analysis_kind="room_verification",
        input_payload=input_payload,
        generated_at_utc="2026-09-25T12:34:56Z",
        limitations=[
            "Review | only\n# forged-limitation <script>alert(2)</script>"
        ],
    )

    assert (
        "# Room \\*unsafe\\*<br># forged-analysis &lt;img&gt; "
        "— CleanroomX Engineering Report"
    ) in document
    assert (
        "- Project: Facility \\| table<br># forged-project "
        "&lt;script&gt;alert(1)&lt;/script&gt;"
    ) in document
    assert "- Analysis ID: room-a<br>- forged-id" in document
    assert (
        "- Review \\| only<br># forged-limitation "
        "&lt;script&gt;alert(2)&lt;/script&gt;"
    ) in document
    assert "\n# forged-project" not in document
    assert "\n# forged-analysis" not in document
    assert "\n- forged-id" not in document
    assert "\n# forged-limitation" not in document
    assert "<script>" not in document
    assert "<img>" not in document

