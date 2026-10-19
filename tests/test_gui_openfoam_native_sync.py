"""Native OpenFOAM synchronization GUI contract and path safety."""
import pytest
from cleanroomx.gui_openfoam import build_openfoam_sync_case_command


def test_native_sync_command_preserves_paths_with_spaces():
    command = build_openfoam_sync_case_command(
        "/tmp/solver case", "/tmp/result store", "case-01", python_executable="/python"
    )
    assert command == [
        "/python", "-m", "cleanroomx.cfd_pipeline_cli", "sync-case",
        "/tmp/solver case", "/tmp/result store", "--simulation-id", "case-01",
    ]


@pytest.mark.parametrize("simulation_id", ["", "../unsafe", "a" * 65, "bad id"])
def test_native_sync_rejects_unsafe_simulation_ids(simulation_id):
    with pytest.raises(ValueError, match="safe simulation ID"):
        build_openfoam_sync_case_command("case", "results", simulation_id)


@pytest.mark.parametrize("case,results", [("", "results"), ("case", "")])
def test_native_sync_requires_both_paths(case, results):
    with pytest.raises(ValueError, match="requires case and result"):
        build_openfoam_sync_case_command(case, results, "valid")


def test_native_sync_rejects_case_as_result_store(tmp_path):
    with pytest.raises(ValueError, match="must differ"):
        build_openfoam_sync_case_command(str(tmp_path), str(tmp_path / "."), "valid")
