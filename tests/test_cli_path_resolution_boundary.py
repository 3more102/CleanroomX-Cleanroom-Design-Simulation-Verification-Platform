from __future__ import annotations

import cleanroomx.bim_ifc_cli as bim_ifc_cli
import cleanroomx.cli_output as cli_output
import cleanroomx.project_batch as project_batch
import cleanroomx.project_diagnostics_cli as project_diagnostics_cli
import cleanroomx.project_dossier_cli as project_dossier_cli
import cleanroomx.project_requirements_traceability_cli as project_requirements_traceability_cli
import cleanroomx.project_verify_cli as project_verify_cli
import cleanroomx.verification_history_cli as verification_history_cli
import pytest


@pytest.mark.parametrize(
    "error",
    [
        OSError("path unavailable"),
        RuntimeError("symlink loop"),
    ],
    ids=["oserror", "runtimeerror"],
)
def test_resolve_cli_path_normalizes_filesystem_path_failures(
    monkeypatch,
    error,
) -> None:
    class BrokenPath:
        def expanduser(self):
            return self

        def resolve(self, *, strict: bool):
            assert strict is False
            raise error

    monkeypatch.setattr(cli_output, "Path", lambda _value: BrokenPath())

    with pytest.raises(
        cli_output.CliInputError,
        match="could not resolve project path: loop",
    ):
        cli_output.resolve_cli_path("loop", label="project")


@pytest.mark.parametrize(
    "failure_point",
    ["expanduser", "resolve"],
)
def test_project_diagnostics_protected_path_runtime_error_is_clean(
    failure_point,
) -> None:
    class BrokenProtectedPath:
        def expanduser(self):
            if failure_point == "expanduser":
                raise RuntimeError("home resolution failed")
            return self

        def resolve(self, *, strict: bool):
            assert strict is False
            raise RuntimeError("symlink loop")

    with pytest.raises(
        OSError,
        match="could not verify diagnostics output path",
    ):
        project_diagnostics_cli._paths_alias(
            BrokenProtectedPath(),
            "report.json",
        )


@pytest.mark.parametrize(
    ("module", "argv", "command"),
    [
        (
            project_batch,
            ["loop.cleanroomx.json"],
            "cleanroomx-project-run",
        ),
        (
            project_diagnostics_cli,
            ["loop.cleanroomx.json"],
            "cleanroomx-project-check",
        ),
        (
            project_dossier_cli,
            ["loop.cleanroomx.json"],
            "cleanroomx-project-dossier",
        ),
        (
            project_verify_cli,
            ["status", "loop.cleanroomx.json", "analysis-a"],
            "cleanroomx-project-verify",
        ),
        (
            project_requirements_traceability_cli,
            ["loop.cleanroomx.json"],
            "cleanroomx-project-traceability",
        ),
        (
            verification_history_cli,
            ["list", "loop.cleanroomx.json"],
            "cleanroomx-verification-history",
        ),
        (
            bim_ifc_cli,
            ["plan", "loop.cleanroomx.json", "model.ifc"],
            "cleanroomx-ifc",
        ),
    ],
    ids=[
        "project-run",
        "project-check",
        "project-dossier",
        "project-verify",
        "project-traceability",
        "verification-history",
        "ifc",
    ],
)
def test_project_level_cli_path_resolution_errors_are_clean(
    monkeypatch,
    capsys,
    module,
    argv,
    command,
) -> None:
    def fail_resolve(_path, *, label="input"):
        raise cli_output.CliInputError(
            f"could not resolve {label} path: loop.cleanroomx.json"
        )

    monkeypatch.setattr(module, "resolve_cli_path", fail_resolve)

    assert module.main(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(f"{command}: error: could not resolve ")
    assert "Traceback" not in captured.err
