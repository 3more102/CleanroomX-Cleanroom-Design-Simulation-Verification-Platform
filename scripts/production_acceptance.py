from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tomllib
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "cleanroomx.production-acceptance"
SCHEMA_VERSION = 1
PINNED_ACTION_RE = re.compile(r"^\s*-?\s*uses:\s*[^@\s]+@([0-9a-f]{40})(?:\s|#|$)")


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _record(checks: list[dict[str, Any]], check_id: str, passed: bool, detail: str) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _required_files(checks: list[dict[str, Any]]) -> None:
    required = (
        "SECURITY.md",
        "TEST_EVIDENCE.md",
        "VALIDATION.txt",
        "docs/PERFORMANCE_GATES.md",
        "docs/STANDARDS.md",
        "docs/GOLDEN_REFERENCE_PROJECTS.md",
        "docs/PRODUCTION_ACCEPTANCE.md",
        "docs/PROOFGRAPH_CHANGE_IMPACT.md",
        "scripts/benchmark_spatial_validation.py",
        "scripts/benchmark_project_bundle.py",
        "scripts/security_static_gate.py",
        ".github/workflows/ci.yml",
        ".github/workflows/production-acceptance.yml",
        ".github/workflows/security.yml",
        ".github/workflows/windows-standalone.yml",
        ".github/workflows/windows-installer.yml",
        "tests/test_golden_reference_project.py",
        "tests/test_golden_facility_reference.py",
        "tests/test_fault_injection_persistence.py",
        "tests/test_production_acceptance.py",
        "tests/test_production_acceptance_contract.py",
        "tests/test_proofgraph_change_impact.py",
        "tests/test_proofgraph_change_impact_cli.py",
    )
    missing = [path for path in required if not (ROOT / path).is_file()]
    _record(
        checks,
        "required-release-evidence",
        not missing,
        "all required release evidence is present"
        if not missing
        else "missing: " + ", ".join(missing),
    )


def _version_and_demo_contract(checks: list[dict[str, Any]]) -> None:
    metadata = tomllib.loads(_read("pyproject.toml"))
    version = str(metadata["project"]["version"])
    release, marker, serial = version.partition(".dev")
    valid_dev = (
        marker == ".dev"
        and serial.isdigit()
        and len(release.split(".")) == 3
        and all(part.isdigit() for part in release.split("."))
    )
    _record(
        checks,
        "development-release-identity",
        valid_dev,
        f"repository version is {version!r}",
    )

    source_demo = json.loads(_read("examples/gui_demo.cleanroomx.json"))
    packaged_demo = json.loads(_read("src/cleanroomx/demo/gui_demo.cleanroomx.json"))
    demos_match = source_demo == packaged_demo
    _record(
        checks,
        "source-packaged-demo-byte-model",
        demos_match,
        "source and packaged GUI demo JSON models match"
        if demos_match
        else "source and packaged GUI demo JSON models differ",
    )
    demo_version = source_demo.get("application_version")
    _record(
        checks,
        "demo-release-identity",
        demo_version == version,
        f"demo application_version={demo_version!r}, project version={version!r}",
    )

    release_dependencies = metadata["project"].get("optional-dependencies", {}).get(
        "release", []
    )
    release_pinned = bool(release_dependencies) and all(
        isinstance(item, str) and "==" in item for item in release_dependencies
    )
    _record(
        checks,
        "release-dependencies-exactly-pinned",
        release_pinned,
        "release dependencies: " + ", ".join(map(str, release_dependencies)),
    )


def _workflow_contract(checks: list[dict[str, Any]]) -> None:
    workflow_dir = ROOT / ".github" / "workflows"
    workflow_paths = tuple(
        path.relative_to(ROOT).as_posix()
        for path in sorted((*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")))
    )
    unpinned: list[str] = []
    for path in workflow_paths:
        for line_number, line in enumerate(_read(path).splitlines(), 1):
            stripped = line.strip()
            if "uses:" not in stripped:
                continue
            if PINNED_ACTION_RE.match(line) is None:
                unpinned.append(f"{path}:{line_number}:{stripped}")
    _record(
        checks,
        "github-actions-immutable-pins",
        not unpinned,
        "all release workflows pin actions to 40-hex commits"
        if not unpinned
        else "unpinned actions: " + "; ".join(unpinned),
    )

    security = _read(".github/workflows/security.yml")
    security_contract = all(
        token in security
        for token in (
            "pull_request:",
            "schedule:",
            "permissions:",
            "contents: read",
            "security_static_gate.py",
            "test_project_bundle.py",
            "test_security_static_gate.py",
        )
    )
    _record(
        checks,
        "continuous-security-workflow",
        security_contract,
        "security workflow covers PR/scheduled hostile-input gates"
        if security_contract
        else "security workflow is missing a required trigger or hostile-input gate",
    )

    ci = _read(".github/workflows/ci.yml")
    matrix_ok = all(version in ci for version in ('"3.11"', '"3.12"', '"3.13"'))
    _record(
        checks,
        "supported-python-matrix",
        matrix_ok,
        "CI contains Python 3.11/3.12/3.13"
        if matrix_ok
        else "CI supported-version matrix is incomplete",
    )

    acceptance = _read(".github/workflows/production-acceptance.yml")
    proofgraph_acceptance_ok = all(
        token in acceptance
        for token in (
            "tests/test_proofgraph_change_impact.py",
            "tests/test_proofgraph_change_impact_cli.py",
        )
    )
    _record(
        checks,
        "proofgraph-change-impact-acceptance",
        proofgraph_acceptance_ok,
        "production acceptance explicitly exercises ProofGraph change-impact API and CLI"
        if proofgraph_acceptance_ok
        else "production acceptance is missing ProofGraph change-impact regression coverage",
    )


def _engineering_boundary(checks: list[dict[str, Any]]) -> None:
    readme = _read("README.md").lower()
    validation = _read("VALIDATION.txt").lower()
    boundary_terms = (
        "does **not**, by itself, establish cleanroom certification",
        "does not by itself establish cleanroom certification",
    )
    readme_ok = boundary_terms[0] in readme
    validation_ok = boundary_terms[1] in validation
    _record(
        checks,
        "engineering-claim-boundary",
        readme_ok and validation_ok,
        "README and validation evidence preserve certification/commissioning boundary"
        if readme_ok and validation_ok
        else "engineering claim boundary is missing from README or validation evidence",
    )

    standards = _read("docs/STANDARDS.md")
    source_policy_ok = (
        "does not infer a universal fixed ACH" in standards
        and "Copyrighted standards text is not bundled" in standards
    )
    _record(
        checks,
        "standards-source-policy",
        source_policy_ok,
        "standards policy keeps criteria explicit and proprietary text out of the repository"
        if source_policy_ok
        else "standards/source-policy guard text is incomplete",
    )


def build_report() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    _required_files(checks)
    _version_and_demo_contract(checks)
    _workflow_contract(checks)
    _engineering_boundary(checks)
    failures = [item for item in checks if not item["passed"]]
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "status": "pass" if not failures else "fail",
        "summary": {
            "check_count": len(checks),
            "pass_count": len(checks) - len(failures),
            "fail_count": len(failures),
        },
        "checks": checks,
        "boundary": (
            "This gate establishes repository release-readiness evidence only; it does "
            "not establish regulatory certification, commissioning/TAB acceptance, "
            "manufacturer approval, or independent CFD validation."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate CleanroomX production acceptance contracts.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    report = build_report()
    encoded = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
