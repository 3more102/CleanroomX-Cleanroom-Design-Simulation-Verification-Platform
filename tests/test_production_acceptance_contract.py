from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(relative: str) -> str:
    path = ROOT / relative
    assert path.is_file(), f"required production artifact is missing: {relative}"
    return path.read_text(encoding="utf-8")


def test_required_production_workflows_are_least_privilege_and_credentialless() -> None:
    for relative in (
        ".github/workflows/ci.yml",
        ".github/workflows/security.yml",
        ".github/workflows/production-acceptance.yml",
        ".github/workflows/windows-installer.yml",
        ".github/workflows/windows-standalone.yml",
    ):
        workflow = _text(relative)
        assert "pull_request:" in workflow
        assert "permissions:\n  contents: read" in workflow
        assert "persist-credentials: false" in workflow


def test_ci_contract_retains_supported_matrix_golden_validation_and_performance() -> None:
    workflow = _text(".github/workflows/ci.yml")

    assert 'python-version: ["3.11", "3.12", "3.13"]' in workflow
    assert 'python -m pip install "pip==26.2.1"' in workflow
    assert "runs-on: windows-2025" in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert "windows-latest" not in workflow
    assert "ubuntu-latest" not in workflow
    assert "Run complete test suite with skip reasons" in workflow
    assert "Run complete test suite with real Tk and skip reasons" in workflow
    assert "tests/test_golden_reference_project.py" in workflow
    assert "scripts/benchmark_spatial_validation.py" in workflow
    assert "scripts/benchmark_project_bundle.py" in workflow
    assert "Build wheel and verify installed application" in workflow
    assert "Run desktop GUI smoke from installed wheel" in workflow
    assert "cleanroomx-proofgraph-diff --help" in workflow
    assert "tests/test_proofgraph_change_impact_cli.py" in workflow


def test_security_contract_retains_static_hostile_input_and_fault_injection_gates() -> None:
    workflow = _text(".github/workflows/security.yml")

    assert "schedule:" in workflow
    assert 'python -m pip install "pip==26.2.1"' in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert "ubuntu-latest" not in workflow
    assert "scripts/security_static_gate.py" in workflow
    assert "tests/test_project_bundle.py" in workflow
    assert "tests/test_plugins.py" in workflow
    assert "tests/test_recovery_artifact_ingestion.py" in workflow
    assert "tests/test_bim_ifc_root_failures.py" in workflow
    assert "tests/test_fault_injection_persistence.py" in workflow
    assert "tests/test_security_static_gate.py" in workflow


def test_windows_release_contract_retains_standalone_hash_and_installer_lifecycle() -> None:
    standalone = _text(".github/workflows/windows-standalone.yml")
    installer = _text(".github/workflows/windows-installer.yml")

    assert "runs-on: windows-2025" in standalone
    assert "build_windows_standalone.ps1" in standalone
    assert "Get-FileHash -Algorithm SHA256" in standalone
    assert "if-no-files-found: error" in standalone

    assert "runs-on: windows-2025" in installer
    assert "build_windows_installer.ps1" in installer
    assert "test_windows_installer_lifecycle.ps1" in installer
    assert "if-no-files-found: error" in installer


def test_engineering_acceptance_contract_retains_independent_golden_references() -> None:
    single_room = _text("tests/test_golden_reference_project.py")
    facility = _text("tests/test_golden_facility_reference.py")

    assert "test_golden_reference_project_has_known_ach_and_full_traceability" in single_room
    assert "test_golden_reference_project_save_reopen_is_reproducible" in single_room
    assert "test_golden_facility_known_ach_and_pressure_cascade" in facility
    assert "test_golden_facility_airflow_consistency_and_report_are_repeatable" in facility


def test_production_acceptance_document_preserves_external_validation_boundary() -> None:
    document = _text("docs/PRODUCTION_ACCEPTANCE.md")

    for phrase in (
        "exact tested commit SHA",
        "Python 3.11, 3.12, and 3.13",
        "Windows Installer Lifecycle",
        "Security",
        "golden",
        "commissioning/TAB",
        "regulatory certification",
    ):
        assert phrase in document


def test_named_production_acceptance_workflow_is_self_validating() -> None:
    workflow = _text(".github/workflows/production-acceptance.yml")

    assert "pull_request:" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert 'python -m pip install "pip==26.2.1"' in workflow
    assert "scripts/production_acceptance.py" in workflow
    assert "tests/test_production_acceptance.py" in workflow
    assert "tests/test_production_acceptance_contract.py" in workflow
    assert "tests/test_proofgraph_change_impact.py" in workflow
    assert "tests/test_proofgraph_change_impact_cli.py" in workflow
    assert "scripts/benchmark_spatial_validation.py" in workflow
    assert "scripts/benchmark_project_bundle.py" in workflow
    assert "actions/upload-artifact@" in workflow
