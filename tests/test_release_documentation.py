from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_current_operational_docs_do_not_present_v01021_as_the_active_build() -> None:
    architecture = _read("ARCHITECTURE.md")
    security = _read("SECURITY.md")
    migrations = _read("MIGRATIONS.md")

    assert "CleanroomX v0.102.1 (Release 2" not in architecture
    assert "CleanroomX v0.102.1 is a local Python" not in security
    assert "CleanroomX v0.102.1 writes desktop projects using:" not in migrations
    assert "immutable stable-release baseline remains v0.102.1" in architecture
    assert "immutable stable-release baseline remains v0.102.1" in security


def test_release_documentation_has_no_known_literal_newline_artifacts() -> None:
    architecture = _read("ARCHITECTURE.md")
    spatial = _read("docs/LAYOUT_2D_3D.md")

    assert r"atomic output.\n10. **Verification/provenance**" not in architecture
    assert r"optional\n`analysis_room_name`" not in spatial
    assert r"does not\ninfer regulatory" not in spatial


def test_branch_protection_doc_matches_required_ci_dependencies() -> None:
    workflow = _read(".github/workflows/ci.yml")
    documentation = _read("docs/MAIN_BRANCH_PROTECTION.md")

    for dependency in ("test", "windows-launcher-smoke", "native-bim-smoke"):
        assert f"- {dependency}" in workflow
    assert "all three production CI surfaces" in documentation
    assert "native IfcOpenShell ingestion smoke job" in documentation


def test_architecture_points_active_identity_to_project_metadata() -> None:
    architecture = _read("ARCHITECTURE.md")
    with (ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]

    assert version != "0.102.1"
    assert "active package identity is defined by `pyproject.toml`" in architecture
