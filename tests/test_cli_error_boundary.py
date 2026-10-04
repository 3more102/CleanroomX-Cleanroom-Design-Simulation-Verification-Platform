from __future__ import annotations

import ast
from pathlib import Path
import sys
import tomllib

import cleanroomx.bim_ifc_cli as bim_ifc_cli
import cleanroomx.cli_output as cli_output
import cleanroomx.project_diagnostics_cli as project_diagnostics_cli
import cleanroomx.project_dossier_cli as project_dossier_cli
import cleanroomx.project_requirements_traceability_cli as project_requirements_traceability_cli
import cleanroomx.project_verify_cli as project_verify_cli
import cleanroomx.verification_history_cli as verification_history_cli
from cleanroomx.project import (
    ProjectFileBusyError,
    ProjectFileRevision,
    ProjectSaveDurabilityError,
    ProjectWriteConflictError,
)
import cleanroomx.fan_curve_cli as fan_curve_cli
import cleanroomx.hvac_cli as hvac_cli
import pytest


CUSTOM_INPUT_BOUNDARY_CLIS = frozenset(
    {"consistency_cli.py", "dossier_cli.py"}
)


def _discover_standalone_file_output_clis() -> tuple[Path, ...]:
    package_dir = Path(cli_output.__file__).resolve().parent
    discovered: list[Path] = []
    for path in sorted(package_dir.glob("*_cli.py")):
        source = path.read_text(encoding="utf-8")
        if "publish_cli_output(" in source:
            discovered.append(path)
    return tuple(discovered)


def test_cli_error_boundary_reports_value_error_without_traceback(capsys) -> None:
    @cli_output.cli_error_boundary("cleanroomx-test")
    def fail() -> int:
        raise ValueError("invalid engineering input")

    assert fail() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "cleanroomx-test: error: invalid engineering input\n"
    assert "Traceback" not in captured.err


def test_cli_error_boundary_reports_oserror_without_traceback(capsys) -> None:
    @cli_output.cli_error_boundary("cleanroomx-test")
    def fail() -> int:
        raise OSError("input source unavailable")

    assert fail() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "cleanroomx-test: error: input source unavailable\n"
    assert "Traceback" not in captured.err


def test_hvac_cli_loader_failure_is_clean(monkeypatch, capsys) -> None:
    def fail_load(_path):
        raise ValueError("malformed HVAC input")

    monkeypatch.setattr(hvac_cli, "load_hvac_project", fail_load)
    monkeypatch.setattr(sys, "argv", ["cleanroomx-hvac", "broken.json"])

    assert hvac_cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "cleanroomx-hvac: error: malformed HVAC input\n"
    assert "Traceback" not in captured.err


def test_fan_curve_cli_analysis_failure_is_clean(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        fan_curve_cli,
        "load_fan_operating_point_study",
        lambda _path: object(),
    )

    def fail_analysis(_study):
        raise ValueError("invalid fan study")

    monkeypatch.setattr(fan_curve_cli, "solve_fan_operating_point", fail_analysis)
    monkeypatch.setattr(sys, "argv", ["cleanroomx-fan-curve", "broken.json"])

    assert fan_curve_cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "cleanroomx-fan-curve: error: invalid fan study\n"
    assert "Traceback" not in captured.err



def test_cli_error_boundary_preserves_explicit_exit_code() -> None:
    @cli_output.cli_error_boundary("cleanroomx-test")
    def status() -> int:
        return 3

    assert status() == 3


def test_cli_error_boundary_does_not_hide_unexpected_runtime_error() -> None:
    @cli_output.cli_error_boundary("cleanroomx-test")
    def fail() -> int:
        raise RuntimeError("programming defect")

    with pytest.raises(RuntimeError, match="programming defect"):
        fail()


def test_fan_curve_cli_missing_required_field_is_clean(
    monkeypatch, tmp_path, capsys
) -> None:
    source = tmp_path / "broken-fan-study.json"
    source.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["cleanroomx-fan-curve", str(source)])

    assert fan_curve_cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "cleanroomx-fan-curve: error: invalid input structure: "
        "missing required field 'fan_curve'\n"
    )
    assert "Traceback" not in captured.err


def test_hvac_cli_wrong_root_shape_is_clean(monkeypatch, tmp_path, capsys) -> None:
    source = tmp_path / "broken-hvac.json"
    source.write_text("[]\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["cleanroomx-hvac", str(source)])

    assert hvac_cli.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(
        "cleanroomx-hvac: error: invalid input structure:"
    )
    assert "Traceback" not in captured.err

def test_all_standalone_file_output_clis_use_shared_error_boundary() -> None:
    candidates = _discover_standalone_file_output_clis()
    assert candidates
    for path in candidates:
        source = path.read_text(encoding="utf-8")
        assert "from .cli_output import cli_error_boundary" in source, path.name
        assert "@cli_error_boundary(" in source, path.name


def test_all_file_loader_clis_use_structural_input_boundary() -> None:
    candidates = _discover_standalone_file_output_clis()
    assert candidates
    for path in candidates:
        if path.name in CUSTOM_INPUT_BOUNDARY_CLIS:
            continue
        source = path.read_text(encoding="utf-8")
        assert "load_cli_input" in source, path.name
        assert "load_cli_input(" in source, path.name

@pytest.mark.parametrize(
    ("module", "attribute", "argv"),
    [
        (
            project_diagnostics_cli,
            "load_project_document_with_revision",
            ["broken.cleanroomx.json"],
        ),
        (
            project_dossier_cli,
            "load_project_document_with_revision",
            ["broken.cleanroomx.json"],
        ),
        (
            project_verify_cli,
            "load_project_document_with_revision",
            ["status", "broken.cleanroomx.json", "analysis-a"],
        ),
        (
            project_requirements_traceability_cli,
            "load_project_document_with_revision",
            ["broken.cleanroomx.json"],
        ),
        (
            verification_history_cli,
            "_load_stable_project",
            ["list", "broken.cleanroomx.json"],
        ),
        (
            bim_ifc_cli,
            "_load_current_project",
            ["plan", "broken.cleanroomx.json", "model.ifc"],
        ),
    ],
    ids=[
        "project-check",
        "project-dossier",
        "project-verify",
        "project-traceability",
        "verification-history",
        "ifc",
    ],
)
def test_project_level_cli_boundaries_do_not_hide_unexpected_runtime_errors(
    monkeypatch,
    module,
    attribute,
    argv,
) -> None:
    def fail(*_args, **_kwargs):
        raise RuntimeError("programming defect")

    monkeypatch.setattr(module, attribute, fail)
    with pytest.raises(RuntimeError, match="programming defect"):
        module.main(argv)

def _project_revision(path: str, digest: str) -> ProjectFileRevision:
    return ProjectFileRevision(
        path=path,
        exists=True,
        size=1,
        mtime_ns=1,
        sha256=digest,
    )


@pytest.mark.parametrize(
    "error",
    [
        ProjectFileBusyError("project.cleanroomx.json", "project.cleanroomx.json.lock"),
        ProjectWriteConflictError(
            "project.cleanroomx.json",
            _project_revision("project.cleanroomx.json", "a" * 64),
            _project_revision("project.cleanroomx.json", "b" * 64),
        ),
        ProjectSaveDurabilityError(
            "project.cleanroomx.json",
            _project_revision("project.cleanroomx.json", "c" * 64),
        ),
    ],
    ids=["busy", "write-conflict", "durability"],
)
@pytest.mark.parametrize(
    ("module", "attribute", "argv", "command"),
    [
        (
            project_verify_cli,
            "run_project_requirements_workflow",
            ["run", "project.cleanroomx.json", "analysis-a"],
            "cleanroomx-project-verify",
        ),
        (
            bim_ifc_cli,
            "_initial_import",
            ["import", "project.cleanroomx.json", "model.ifc"],
            "cleanroomx-ifc",
        ),
    ],
    ids=["project-verify", "ifc"],
)
def test_guarded_save_state_errors_remain_clean_cli_failures(
    monkeypatch,
    capsys,
    module,
    attribute,
    argv,
    command,
    error,
) -> None:
    def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(module, attribute, fail)

    assert module.main(argv) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(f"{command}: error: ")
    assert "Traceback" not in captured.err


def _configured_cli_entry_points() -> tuple[tuple[str, Path, str], ...]:
    """Resolve every installed console script to its configured entry function."""
    package_dir = Path(cli_output.__file__).resolve().parent
    repository_root = package_dir.parents[1]
    metadata = tomllib.loads(
        (repository_root / "pyproject.toml").read_text(encoding="utf-8")
    )

    entries: list[tuple[str, Path, str]] = []
    for command, entry_point in metadata["project"]["scripts"].items():
        module_name, separator, target = entry_point.partition(":")
        assert separator == ":", command
        assert module_name.startswith("cleanroomx."), command
        # The desktop launcher has its own UI error-reporting contract and
        # intentionally catches broad exceptions at the Tk entry boundary.
        # This guard covers command-line entry points only.
        if module_name == "cleanroomx.gui":
            continue
        module_path = (
            repository_root
            / "src"
            / Path(*module_name.split(".")).with_suffix(".py")
        )
        assert module_path.is_file(), command
        entries.append((command, module_path, target))
    return tuple(sorted(entries))


def _handled_exception_names(node: ast.expr | None) -> set[str]:
    if node is None:
        return {"<bare>"}
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    if isinstance(node, ast.Tuple):
        names: set[str] = set()
        for element in node.elts:
            names.update(_handled_exception_names(element))
        return names
    return set()


def _entry_function(tree: ast.Module, command: str, target: str) -> ast.FunctionDef:
    target_name = target.split(".", 1)[0]
    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == target_name
    ]
    assert len(matches) == 1, f"{command}: expected one top-level {target!r} entry"
    return matches[0]


def _entry_exception_handlers(function: ast.FunctionDef) -> tuple[ast.ExceptHandler, ...]:
    handlers: list[ast.ExceptHandler] = []

    class EntryBoundaryVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            return

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            return

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            return

        def visit_Lambda(self, node: ast.Lambda) -> None:
            return

        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
            handlers.append(node)
            self.generic_visit(node)

    visitor = EntryBoundaryVisitor()
    for statement in function.body:
        visitor.visit(statement)
    return tuple(handlers)


def test_all_configured_cli_entry_boundaries_do_not_catch_broad_runtime_errors() -> None:
    configured = _configured_cli_entry_points()
    assert configured

    forbidden = {"<bare>", "BaseException", "Exception", "RuntimeError"}
    violations: list[str] = []
    for command, path, target in configured:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        function = _entry_function(tree, command, target)
        for handler in _entry_exception_handlers(function):
            caught = _handled_exception_names(handler.type) & forbidden
            if caught:
                violations.append(
                    f"{command} ({path.name}:{handler.lineno}) catches "
                    f"{', '.join(sorted(caught))}"
                )

    assert not violations, (
        "configured CLI entry boundaries must not hide unexpected runtime defects behind broad catches:\n"
        + "\n".join(violations)
    )
