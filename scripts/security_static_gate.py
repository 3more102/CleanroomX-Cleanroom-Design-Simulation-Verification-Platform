from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (REPOSITORY_ROOT / "src", REPOSITORY_ROOT / "scripts")
SELF = Path(__file__).resolve()

# These APIs are intentionally prohibited in production source and release scripts.
# The gate is conservative: if a future use is truly necessary, it must be reviewed
# and the policy changed explicitly rather than bypassed locally.
PROHIBITED_CALLS = {
    "os.system": "shell command execution through os.system",
    "os.popen": "shell command execution through os.popen",
    "tempfile.mktemp": "race-prone temporary path creation",
    "pickle.load": "unsafe deserialization",
    "pickle.loads": "unsafe deserialization",
    "marshal.load": "unsafe deserialization",
    "marshal.loads": "unsafe deserialization",
    "yaml.load": "potentially unsafe YAML deserialization",
    "yaml.unsafe_load": "unsafe YAML deserialization",
}


@dataclass(frozen=True, order=True)
class Violation:
    path: str
    line: int
    column: int
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}:{self.column}: {self.message}"


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
    return None


def _aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                local = item.asname or item.name.split(".", 1)[0]
                aliases[local] = item.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                if item.name == "*":
                    continue
                local = item.asname or item.name
                aliases[local] = f"{node.module}.{item.name}"
    return aliases


def _normalize_name(name: str | None, aliases: dict[str, str]) -> str | None:
    if not name:
        return None
    head, dot, tail = name.partition(".")
    replacement = aliases.get(head)
    if replacement is None:
        return name
    return replacement + (dot + tail if dot else "")


def _literal_true(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _scan_file(path: Path) -> list[Violation]:
    relative = path.relative_to(REPOSITORY_ROOT).as_posix()
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
    except (OSError, UnicodeError, SyntaxError) as exc:
        return [Violation(relative, 1, 0, f"security scan could not parse file: {exc}")]

    aliases = _aliases(tree)
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        raw_name = _dotted_name(node.func)
        name = _normalize_name(raw_name, aliases)

        # Built-in eval/exec remain prohibited even if referenced directly.
        if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            violations.append(
                Violation(
                    relative,
                    node.lineno,
                    node.col_offset,
                    f"prohibited dynamic code execution: {node.func.id}()",
                )
            )
            continue

        if name in PROHIBITED_CALLS:
            violations.append(
                Violation(
                    relative,
                    node.lineno,
                    node.col_offset,
                    f"prohibited API {name}: {PROHIBITED_CALLS[name]}",
                )
            )
            continue

        # Archive extraction must remain the current verified, staged,
        # member-by-member implementation. Direct ZipFile extraction helpers can
        # reintroduce traversal/link handling hazards.
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"extract", "extractall"}:
            violations.append(
                Violation(
                    relative,
                    node.lineno,
                    node.col_offset,
                    f"prohibited archive extraction helper: .{node.func.attr}()",
                )
            )
            continue

        if name and name.startswith("subprocess."):
            for keyword in node.keywords:
                if keyword.arg == "shell" and _literal_true(keyword.value):
                    violations.append(
                        Violation(
                            relative,
                            node.lineno,
                            node.col_offset,
                            "prohibited subprocess shell=True",
                        )
                    )
                    break

    return violations


def _python_files() -> Iterable[Path]:
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if path.resolve() == SELF:
                continue
            yield path


def main() -> int:
    violations = sorted(
        violation
        for path in _python_files()
        for violation in _scan_file(path)
    )
    if violations:
        print("CleanroomX security static gate: FAIL", file=sys.stderr)
        for violation in violations:
            print(violation.render(), file=sys.stderr)
        return 1

    print("CleanroomX security static gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
