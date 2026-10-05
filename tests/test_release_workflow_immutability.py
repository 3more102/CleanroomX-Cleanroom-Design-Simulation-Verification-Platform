from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

HISTORICAL_RELEASES = {
    ".github/workflows/publish-v0100-release.yml": (
        "v0.100.0",
        "30c43983d87d6e6de2fe81c6f38610c238b1a5f4",
    ),
    ".github/workflows/publish-v0101-release.yml": (
        "v0.101.0",
        "1ca79b66c2e87c7ab45745ee98a5f60efa444cf5",
    ),
    ".github/workflows/publish-v0102-release.yml": (
        "v0.102.0",
        "37a83dcce3489397647f27faf41a7c79680aa576",
    ),
    ".github/workflows/publish-v01021-release.yml": (
        "v0.102.1",
        "dbcaec8c8a74820b7e9fb3e4b88fba8ebfac6dc5",
    ),
}


def test_historical_release_workflows_are_manual_and_sha_pinned():
    for relative_path, (tag, target_sha) in HISTORICAL_RELEASES.items():
        workflow = (ROOT / relative_path).read_text(encoding="utf-8")

        assert "workflow_dispatch:" in workflow
        assert "workflow_run:" not in workflow
        assert "github.event.workflow_run" not in workflow
        assert f"TAG: {tag}" in workflow
        assert f"TARGET_SHA: {target_sha}" in workflow
