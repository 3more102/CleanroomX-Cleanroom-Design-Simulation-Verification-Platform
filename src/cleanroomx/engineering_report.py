from __future__ import annotations

import copy
from hashlib import sha256
import hmac
from html import escape
import json
from typing import Any

from . import __version__
from .application import AnalysisRun, analysis_run_matches_input


ENGINEERING_REPORT_SCHEMA = "cleanroomx.engineering-report"
ENGINEERING_REPORT_SCHEMA_VERSION = 1
ENGINEERING_REPORT_CANONICALIZATION = "json-sort-keys-compact-utf8-v1"


class EngineeringReportFreshnessError(ValueError):
    """Raised when a report is requested for a run that no longer matches its input."""


def _strict_json_clone(value: Any) -> Any:
    text = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return json.loads(text)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def build_engineering_report_payload(
    run: AnalysisRun,
    *,
    project_name: str,
    project_description: str,
    analysis_id: str,
    analysis_name: str,
    analysis_kind: str,
    input_payload: dict,
) -> dict[str, Any]:
    """Build deterministic report evidence from one exact completed analysis run.

    The report is intentionally presentation-only: it never invokes an engineering
    solver. Freshness is checked against the same canonical input identity used by
    the desktop result cache before any report evidence is assembled.
    """
    for field_name, value in (
        ("project_name", project_name),
        ("analysis_id", analysis_id),
        ("analysis_name", analysis_name),
        ("analysis_kind", analysis_kind),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must be a non-empty string")
    if not isinstance(project_description, str):
        raise TypeError("project_description must be a string")
    if not isinstance(input_payload, dict):
        raise TypeError("input_payload must be a JSON object")
    if run.kind != analysis_kind or not analysis_run_matches_input(
        run, analysis_kind, input_payload
    ):
        raise EngineeringReportFreshnessError(
            "analysis result no longer matches the requested analysis input; "
            "run the analysis again before exporting a portable report"
        )

    provenance = run.diagnostics.get("application_execution_provenance", {})
    input_sha256 = provenance.get("input_sha256")
    if not isinstance(input_sha256, str) or len(input_sha256) != 64:
        raise EngineeringReportFreshnessError(
            "analysis result is missing a valid canonical input identity"
        )

    core = {
        "schema": ENGINEERING_REPORT_SCHEMA,
        "schema_version": ENGINEERING_REPORT_SCHEMA_VERSION,
        "application_version": __version__,
        "project": {
            "name": project_name.strip(),
            "description": project_description,
        },
        "analysis": {
            "id": analysis_id.strip(),
            "name": analysis_name.strip(),
            "kind": analysis_kind.strip(),
            "status": str(run.status),
            "input_sha256": input_sha256,
        },
        "input": _strict_json_clone(input_payload),
        "result": _strict_json_clone(run.result),
        "diagnostics": _strict_json_clone(run.diagnostics),
        "backend_report_markdown": str(run.markdown),
    }
    digest = sha256(_canonical_bytes(core)).hexdigest()
    return {
        **core,
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": ENGINEERING_REPORT_CANONICALIZATION,
            "scope": "report payload excluding integrity",
            "sha256": digest,
        },
    }


def verify_engineering_report_payload(payload: dict[str, Any]) -> bool:
    """Verify deterministic report-payload integrity without trusting presentation HTML."""
    if not isinstance(payload, dict):
        return False
    if payload.get("schema") != ENGINEERING_REPORT_SCHEMA:
        return False
    if payload.get("schema_version") != ENGINEERING_REPORT_SCHEMA_VERSION:
        return False
    if not isinstance(payload.get("application_version"), str):
        return False
    project = payload.get("project")
    analysis = payload.get("analysis")
    if not isinstance(project, dict) or not isinstance(analysis, dict):
        return False
    if not isinstance(project.get("name"), str) or not project["name"]:
        return False
    if not isinstance(project.get("description"), str):
        return False
    for key in ("id", "name", "kind", "status"):
        if not isinstance(analysis.get(key), str) or not analysis[key]:
            return False
    input_sha256 = analysis.get("input_sha256")
    if not isinstance(input_sha256, str) or len(input_sha256) != 64:
        return False
    if not isinstance(payload.get("input"), dict):
        return False
    if not isinstance(payload.get("result"), dict):
        return False
    if not isinstance(payload.get("diagnostics"), dict):
        return False
    if not isinstance(payload.get("backend_report_markdown"), str):
        return False
    integrity = payload.get("integrity")
    if not isinstance(integrity, dict):
        return False
    if integrity.get("algorithm") != "sha256":
        return False
    if integrity.get("canonicalization") != ENGINEERING_REPORT_CANONICALIZATION:
        return False
    if integrity.get("scope") != "report payload excluding integrity":
        return False
    expected = integrity.get("sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        return False

    core = copy.deepcopy(payload)
    core.pop("integrity", None)
    try:
        actual = sha256(_canonical_bytes(core)).hexdigest()
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(expected, actual)


def _pretty_json(value: Any) -> str:
    return json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )


def _embedded_json(value: Any) -> str:
    """Serialize JSON for a non-executable script element without HTML breakout."""
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def render_engineering_report_html(payload: dict[str, Any]) -> str:
    """Render a deterministic, self-contained, print-friendly HTML document."""
    if not verify_engineering_report_payload(payload):
        raise ValueError("engineering report payload failed integrity verification")

    project = payload["project"]
    analysis = payload["analysis"]
    integrity = payload["integrity"]
    title = f"{analysis['name']} — CleanroomX Engineering Report"

    styles = """
:root { color-scheme: light; font-family: Arial, Helvetica, sans-serif; }
* { box-sizing: border-box; }
body { margin: 0; background: #f4f6f8; color: #18202a; line-height: 1.45; }
main { max-width: 1100px; margin: 0 auto; padding: 32px; }
header, section { background: white; border: 1px solid #d9dee5; border-radius: 8px; padding: 22px; margin-bottom: 18px; }
h1 { margin: 0 0 6px; font-size: 28px; }
h2 { margin-top: 0; font-size: 20px; }
.subtitle { margin: 0; color: #4b5563; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin-top: 18px; }
.card { border: 1px solid #e2e6eb; border-radius: 6px; padding: 12px; }
.label { display: block; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #667085; }
.value { display: block; margin-top: 4px; overflow-wrap: anywhere; }
code, pre { font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; border: 1px solid #e2e6eb; border-radius: 6px; background: #f8fafc; padding: 14px; overflow-x: auto; }
details { margin-top: 12px; }
summary { cursor: pointer; font-weight: 700; }
.note { border-left: 4px solid #667085; padding-left: 12px; color: #475467; }
footer { color: #667085; font-size: 12px; padding: 4px 2px 24px; }
@media print {
  body { background: white; }
  main { max-width: none; padding: 0; }
  header, section { border-color: #b8bec7; break-inside: avoid; }
  details { display: block; }
}
""".strip()

    input_text = escape(_pretty_json(payload["input"]))
    result_text = escape(_pretty_json(payload["result"]))
    diagnostics_text = escape(_pretty_json(payload["diagnostics"]))
    markdown_text = escape(payload["backend_report_markdown"])
    machine_json = _embedded_json(payload)
    description_html = (
        f'  <p>{escape(project["description"])}</p>\n'
        if project["description"]
        else ""
    )

    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{escape(title)}</title>\n"
        f"  <style>{styles}</style>\n"
        "</head>\n"
        "<body>\n"
        "<main>\n"
        "<header>\n"
        f"  <h1>{escape(analysis['name'])}</h1>\n"
        f"  <p class=\"subtitle\">{escape(project['name'])} · CleanroomX {escape(payload['application_version'])}</p>\n"
        f"{description_html}"
        '  <div class="grid">\n'
        f'    <div class="card"><span class="label">Status</span><span class="value">{escape(analysis["status"])}</span></div>\n'
        f'    <div class="card"><span class="label">Workflow</span><span class="value">{escape(analysis["kind"])}</span></div>\n'
        f'    <div class="card"><span class="label">Analysis ID</span><span class="value">{escape(analysis["id"])}</span></div>\n'
        f'    <div class="card"><span class="label">Input SHA-256</span><span class="value"><code>{escape(analysis["input_sha256"])}</code></span></div>\n'
        "  </div>\n"
        "</header>\n"
        "<section>\n"
        "  <h2>Engineering report</h2>\n"
        f"  <pre>{markdown_text}</pre>\n"
        "</section>\n"
        "<section>\n"
        "  <h2>Traceability evidence</h2>\n"
        f'  <p class="note">Evidence SHA-256: <code>{escape(integrity["sha256"])}</code>. '
        "This digest covers the canonical report payload excluding the integrity object itself; "
        "it is integrity evidence, not a digital signature or certification.</p>\n"
        "  <details open><summary>Submitted analysis input</summary>\n"
        f"    <pre>{input_text}</pre>\n"
        "  </details>\n"
        "  <details><summary>Normalized engineering result</summary>\n"
        f"    <pre>{result_text}</pre>\n"
        "  </details>\n"
        "  <details><summary>Diagnostics and execution provenance</summary>\n"
        f"    <pre>{diagnostics_text}</pre>\n"
        "  </details>\n"
        "</section>\n"
        "<footer>Self-contained CleanroomX engineering evidence. No external scripts, stylesheets, or network resources are required.</footer>\n"
        "</main>\n"
        '<script id="cleanroomx-report-evidence" type="application/json">\n'
        f"{machine_json}\n"
        "</script>\n"
        "</body>\n"
        "</html>\n"
    )


def engineering_report_html(
    run: AnalysisRun,
    *,
    project_name: str,
    project_description: str,
    analysis_id: str,
    analysis_name: str,
    analysis_kind: str,
    input_payload: dict,
) -> str:
    """Build and render one verified portable engineering report."""
    payload = build_engineering_report_payload(
        run,
        project_name=project_name,
        project_description=project_description,
        analysis_id=analysis_id,
        analysis_name=analysis_name,
        analysis_kind=analysis_kind,
        input_payload=input_payload,
    )
    return render_engineering_report_html(payload)
