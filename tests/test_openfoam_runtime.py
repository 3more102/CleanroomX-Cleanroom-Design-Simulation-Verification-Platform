"""Discovery and Bash contracts. Fake executables here are not CFD evidence."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from cleanroomx import openfoam_runtime as runtime

ROOT = Path(__file__).resolve().parents[1]


def installation(root, name, content="# fixture; must never be sourced during discovery\n"):
    path = root / name / "etc/bashrc"
    path.parent.mkdir(parents=True)
    path.write_text(content)
    return path


def discover(tmp_path, *, env=None):
    return runtime.discover_openfoam_environments(
        env={} if env is None else env, search_roots=[tmp_path], home=tmp_path / "user",
    )


def test_inventory_reports_other_versions_without_executing_or_selecting_them(tmp_path):
    marker = tmp_path / "sourced"
    installation(tmp_path, "openfoam14", f"touch '{marker}'\n")
    installation(tmp_path, "OpenFOAM-v2406")
    report = discover(tmp_path)
    assert report["selected_bashrc"] is None
    assert report["runtime_verified"] is False
    assert sorted(c["release_hint"] for c in report["environments"]) == ["14", "2406"]
    assert "v10" in report["selection_error"]
    assert not marker.exists()
    json.dumps(report, allow_nan=False)


def test_discovers_supported_source_install_with_spaces_independent_of_cwd(tmp_path, monkeypatch):
    base = tmp_path / "installation with spaces"
    path = installation(base, "OpenFOAM-10")
    monkeypatch.chdir(tmp_path)
    report = runtime.discover_openfoam_environments(env={}, search_roots=[base], home=tmp_path)
    assert report["selected_bashrc"] == str(path)
    assert report["environments"][0]["runtime_verified"] is False


def test_explicit_override_precedes_discovered_installations_and_accepts_custom_location(tmp_path):
    installation(tmp_path, "openfoam10")
    explicit = installation(tmp_path / "mounted D drive", "custom-runtime")
    report = discover(tmp_path, env={runtime.ENVIRONMENT_VARIABLE: str(explicit)})
    assert report["selected_bashrc"] == str(explicit)
    assert report["environments"][0]["origin"] == "explicit_override"


@pytest.mark.parametrize("override", ["missing/etc/bashrc", "/missing-cleanroomx-test/etc/bashrc"])
def test_invalid_explicit_override_never_silently_uses_another_runtime(tmp_path, override):
    installation(tmp_path, "openfoam10")
    report = discover(tmp_path, env={runtime.ENVIRONMENT_VARIABLE: override})
    assert report["selected_bashrc"] is None
    assert report["selection_error"]


def test_active_environment_custom_path_and_symlink_duplicates(tmp_path):
    actual = installation(tmp_path, "custom-runtime")
    report = discover(tmp_path, env={"WM_PROJECT_DIR": str(actual.parent.parent), "WM_PROJECT_VERSION": "10"})
    assert report["selected_bashrc"] == str(actual)
    assert len(report["environments"]) == 1


def test_discovery_is_one_level_deep_and_bounds_directory_inventory(tmp_path, monkeypatch):
    installation(tmp_path / "unrelated", "OpenFOAM-10")
    monkeypatch.setattr(runtime, "_MAX_ENTRIES_PER_ROOT", 1)
    (tmp_path / "another").mkdir()
    report = discover(tmp_path)
    assert report["environments"] == []
    assert "Inspection limit" in report["inspection_issues"][0]


def test_cli_json_inventory_is_distinct_from_verified_execution(tmp_path, monkeypatch, capsys):
    installation(tmp_path, "openfoam10")
    report = discover(tmp_path)
    monkeypatch.setattr(runtime, "discover_openfoam_environments", lambda: report)
    assert runtime.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["runtime_verified"] is False
    assert runtime.main(["--select"]) == 0
    assert capsys.readouterr().out.strip() == report["selected_bashrc"]
    report["selection_error"] = "No supported environment"
    assert runtime.main(["--select"]) == 2
    error = capsys.readouterr().err
    assert runtime.INSTALLATION_GUIDE in error


@pytest.mark.skipif(os.name == "nt" or not shutil.which("bash"), reason="Actual Bash required")
@pytest.mark.parametrize("release,expected", [("10", 0), ("14", 1)])
def test_wrapper_verifies_actual_executable_version_before_running_requested_command(tmp_path, release, expected):
    root = tmp_path / "runtime with spaces"
    binaries = root / "bin"
    binaries.mkdir(parents=True)
    for name in ("blockMesh", "checkMesh", "postProcess", "simpleFoam"):
        binary = binaries / name
        binary.write_text(f"#!/bin/sh\nprintf 'Using: OpenFOAM-{release} (fixture only)\\n'\n")
        binary.chmod(0o755)
    bashrc = installation(root, "OpenFOAM-10", f"export PATH='{binaries}':\"$PATH\"\n")
    marker = tmp_path / "command-ran"
    env = dict(os.environ, CLEANROOMX_OPENFOAM_BASHRC=str(bashrc))
    process = subprocess.run(
        ["bash", str(ROOT / "scripts/with_openfoam10.sh"), sys.executable, "-c",
         "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('ran')", str(marker)],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )
    assert process.returncode == expected, process.stderr
    assert marker.exists() is (expected == 0)
    if expected:
        assert "refusing a different runtime" in process.stderr
