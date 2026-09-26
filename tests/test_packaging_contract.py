from __future__ import annotations

import importlib
import inspect
from pathlib import Path
import tomllib

import cleanroomx
import pytest


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def _project_metadata() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _console_scripts() -> list[tuple[str, str]]:
    scripts = _project_metadata()["project"].get("scripts", {})
    return sorted((str(name), str(target)) for name, target in scripts.items())


def _resolve_entry_point(target: str):
    module_name, separator, object_path = target.partition(":")
    assert separator and module_name and object_path, (
        f"console-script target must use 'module:object' syntax: {target!r}"
    )

    module = importlib.import_module(module_name)
    resolved = module
    for attribute in object_path.split("."):
        assert attribute, f"empty attribute component in console-script target: {target!r}"
        resolved = getattr(resolved, attribute)
    return resolved


def test_console_script_registry_is_not_empty() -> None:
    scripts = _console_scripts()
    assert scripts, "pyproject.toml must expose at least one project console script"


@pytest.mark.parametrize(("script_name", "target"), _console_scripts())
def test_console_script_targets_resolve_to_zero_argument_callables(
    script_name: str,
    target: str,
) -> None:
    resolved = _resolve_entry_point(target)

    assert callable(resolved), (
        f"console script {script_name!r} resolves to non-callable {target!r}"
    )

    try:
        inspect.signature(resolved).bind()
    except (TypeError, ValueError) as exc:
        pytest.fail(
            f"console script {script_name!r} target {target!r} cannot be invoked "
            f"with zero Python arguments: {exc}"
        )


def test_runtime_version_matches_project_metadata() -> None:
    project_version = str(_project_metadata()["project"]["version"])
    assert cleanroomx.__version__ == project_version
