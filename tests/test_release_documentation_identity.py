from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_INIT = ROOT / "src" / "cleanroomx" / "__init__.py"
ARCHITECTURE = ROOT / "ARCHITECTURE.md"


def _package_version() -> str:
    tree = ast.parse(PACKAGE_INIT.read_text(encoding="utf-8"), filename=str(PACKAGE_INIT))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == "__version__":
            value = ast.literal_eval(node.value)
            assert isinstance(value, str)
            return value
    raise AssertionError("cleanroomx.__version__ is not declared in package __init__.py")


def test_architecture_release_scope_names_current_package_version() -> None:
    version = _package_version()
    architecture = ARCHITECTURE.read_text(encoding="utf-8")
    release_scope = architecture.split("## Release 3 design foundation", 1)[0]

    assert f"CleanroomX v{version}" in release_scope

