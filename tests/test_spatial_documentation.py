from __future__ import annotations

from pathlib import Path


DOC = Path(__file__).resolve().parents[1] / "docs" / "LAYOUT_2D_3D.md"


def test_spatial_documentation_has_no_escaped_newline_artifacts() -> None:
    text = DOC.read_text(encoding="utf-8")
    spatial_model = text.split("## Spatial model", 1)[1].split("## 2D editor", 1)[0]

    assert "\\n" not in spatial_model, (
        "spatial-model prose contains a literal escaped newline; use a real line break "
        "so operator documentation renders correctly"
    )
