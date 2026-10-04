from __future__ import annotations

import ast
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"

# These installed commands intentionally use command-specific error handling rather
# than the shared @cli_error_boundary decorator. Their behavior is covered by
# dedicated command tests. Keeping this list explicit makes a newly installed
# console command fail the policy test until its boundary strategy is reviewed.
COMMAND_SPECIFIC_BOUNDARY_MODULES = frozenset(
    {
        "cleanroomx.assurance_snapshot_cli",
        "cleanroomx.bim_ifc_cli",
        "cleanroomx.cli",
        "cleanroomx.gui",
        "cleanroomx.project_batch",
        "cleanroomx.project_bundle_cli",
        "cleanroomx.project_diagnostics_cli",
        "cleanroomx.project_dossier_cli",
        "cleanroomx.project_requirements_traceability_cli",
        "cleanroomx.project_verify_cli",
        "cleanroomx.verification_history_cli",
    }
)


def _configured_console_modules() -> list[tuple[str, str, Path]]:
    metadata = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    scripts = metadata["project"].get("scripts", {})
    configured: list[tuple[str, str, Path]] = []

    for command, target in sorted(scripts.items()):
        module_name, separator, object_path = str(target).partition(":")
        assert separator == ":", command
        assert object_path == "main", (
            f"{command} must target a reviewed main() boundary, got {target!r}"
        )
        assert module_name.startswith("cleanroomx."), command

        module_path = (
            ROOT
            / "src"
            / Path(*module_name.split(".")).with_suffix(".py")
        )
        assert module_path.is_file(), command
        configured.append((str(command), module_name, module_path))

    return configured


def _decorator_name(decorator: ast.expr) -> str | None:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _main_uses_shared_error_boundary(tree: ast.Module) -> bool:
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "main":
            continue
        return any(
            _decorator_name(decorator) == "cli_error_boundary"
            for decorator in node.decorator_list
        )
    return False


def test_all_installed_console_commands_have_reviewed_error_boundary_policy() -> None:
    configured = _configured_console_modules()
    assert configured

    unclassified: list[str] = []
    for command, module_name, module_path in configured:
        tree = ast.parse(
            module_path.read_text(encoding="utf-8"),
            filename=str(module_path),
        )
        if _main_uses_shared_error_boundary(tree):
            continue
        if module_name in COMMAND_SPECIFIC_BOUNDARY_MODULES:
            continue
        unclassified.append(f"{command} -> {module_name}:main")

    assert not unclassified, (
        "new console commands must use @cli_error_boundary or be explicitly "
        "reviewed as command-specific boundaries: "
        + ", ".join(unclassified)
    )


def test_command_specific_boundary_allowlist_only_names_installed_commands() -> None:
    configured_modules = {
        module_name
        for _command, module_name, _module_path in _configured_console_modules()
    }

    stale = sorted(COMMAND_SPECIFIC_BOUNDARY_MODULES - configured_modules)
    assert not stale, (
        "command-specific boundary allowlist contains non-installed modules: "
        + ", ".join(stale)
    )
