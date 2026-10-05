from __future__ import annotations

import ast
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render_solution_manual_pdf.py"


def test_solution_manual_pdf_has_no_silent_broad_exception_handlers() -> None:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    violations: list[int] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not isinstance(node.type, ast.Name) or node.type.id != "Exception":
            continue
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            violations.append(node.lineno)

    assert violations == [], (
        "solution-manual PDF generation must not silently swallow broad exceptions; "
        f"silent handlers at lines {violations}"
    )
