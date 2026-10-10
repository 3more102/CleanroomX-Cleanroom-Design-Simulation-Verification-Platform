"""Synthetic ASCII polyMesh connectivity fixtures, not real solver results."""
from __future__ import annotations

from pathlib import Path

import pytest

from cleanroomx.cfd_polymesh_audit import (
    audit_grid_family_polymesh, screen_ascii_polymesh,
)
from cleanroomx.cfd_grid_family import generate_grid_family, SCHEMA as FAMILY_SCHEMA
from cleanroomx.cfd_openfoam import SCHEMA as FOAM_SCHEMA


def _write_foam_list(root, name, cls, rows):
    header = (
        "/* Synthetic mesh, no physical verification */\n"
        "FoamFile\n{\n"
        "    version 2.0;\n    format ascii;\n"
        f"    class {cls};\n    location \"constant/polyMesh\";\n"
        f"    object {name};\n}}\n"
    )
    (root / name).write_text(
        header + f"{len(rows)}\n(\n" + "\n".join(rows) + "\n)\n",
        encoding="ascii",
    )


def _mesh_fixture(case_dir, *, cells=2):
    """Build one/two adjacent synthetic hexahedra with shared internal face."""
    mesh_dir = case_dir / "constant/polyMesh"
    mesh_dir.mkdir(parents=True)
    points = [
        (x, y, z) for x in range(cells + 1)
        for z in range(2) for y in range(2)
    ]
    mapping = {point: i for i, point in enumerate(points)}
    faces = {}
    for cell in range(cells):
        def point(x, y, z):
            return mapping[(x, y, z)]
        a, b, c, d = (
            point(cell, 0, 0), point(cell+1, 0, 0),
            point(cell+1, 1, 0), point(cell, 1, 0)
        )
        e, f, g, h = (
            point(cell, 0, 1), point(cell+1, 0, 1),
            point(cell+1, 1, 1), point(cell, 1, 1)
        )
        for indices in (
            (a, d, c, b), (e, f, g, h), (a, b, f, e),
            (b, c, g, f), (c, d, h, g), (d, a, e, h),
        ):
            identity = frozenset(indices)
            if identity not in faces:
                faces[identity] = (indices, [cell])
            else:
                faces[identity][1].append(cell)
    # The internal face (if any) comes first; all boundary faces follow.
    internal = [entry for entry in faces.values() if len(entry[1]) == 2]
    external = [entry for entry in faces.values() if len(entry[1]) == 1]
    # Partition boundaries in fixed inlet/outlet/walls order.
    inlet = [v for v in external if all(points[i][2] == 0 for i in v[0])]
    outlet = [v for v in external if all(points[i][2] == 1 for i in v[0])]
    walls = [v for v in external if v not in inlet and v not in outlet]
    ordered = internal + inlet + outlet + walls
    _write_foam_list(
        mesh_dir, "points", "vectorField",
        ["(" + " ".join(str(n) for n in pt) + ")" for pt in points],
    )
    _write_foam_list(
        mesh_dir, "faces", "faceList",
        [f"4(" + " ".join(str(i) for i in face) + ")"
         for face, _ in ordered],
    )
    _write_foam_list(
        mesh_dir, "owner", "labelList",
        [str(min(owners)) for _, owners in ordered],
    )
    _write_foam_list(
        mesh_dir, "neighbour", "labelList",
        [str(max(owners)) for _, owners in internal],
    )
    boundary = [
        ("inlet", len(inlet), len(internal)),
        ("outlet", len(outlet), len(internal) + len(inlet)),
        ("walls", len(walls), len(internal) + len(inlet) + len(outlet)),
    ]
    header = (
        "FoamFile\n{\n    version 2.0;\n    format ascii;\n"
        "    class polyBoundaryMesh;\n    location \"constant/polyMesh\";\n"
        "    object boundary;\n}\n"
    )
    patches = "\n".join(
        f"{name}\n{{\n    type {'wall' if name == 'walls' else 'patch'};\n"
        f"    nFaces {num};\n    startFace {start};\n}}"
        for name, num, start in boundary
    )
    (mesh_dir / "boundary").write_text(
        header + f"3\n(\n{patches}\n)\n", encoding="ascii",
    )
    return mesh_dir


@pytest.mark.parametrize("cells", [1, 2])
def test_synthetic_hex_polymesh_connectivity_is_structurally_screened(tmp_path, cells):
    case = tmp_path / "case"
    mesh_dir = _mesh_fixture(case, cells=cells)
    result = screen_ascii_polymesh(case, expected_cells=cells)
    assert result["cells"] == cells
    assert result["points"] == (cells + 1) * 4
    assert result["internal_faces"] == cells - 1
    assert result["faces"] == 5 * cells + 1
    assert result["engineering_review"] == "BLOCKED"


@pytest.mark.parametrize("tamper", [
    "wrong_cell_count", "owner_truncated", "wrong_vertex", "duplicate_face",
    "binary", "missing_neighbour", "boundary_gap", "point_duplicate",
    "same_owner_neighbour", "unclosed_cell",
])
def test_synthetic_polymesh_structural_tampering_fails_closed(tmp_path, tamper):
    case = tmp_path / "case"
    mesh = _mesh_fixture(case, cells=2)
    expected = 2
    if tamper == "wrong_cell_count":
        expected = 3
    elif tamper == "owner_truncated":
        path = mesh / "owner"
        path.write_text(path.read_text().replace("11\n(", "10\n(", 1))
    elif tamper == "wrong_vertex":
        path = mesh / "faces"
        path.write_text(path.read_text().replace("4(", "4(999 ", 1))
    elif tamper == "duplicate_face":
        path = mesh / "faces"
        lines = path.read_text().splitlines(keepends=True)
        idx = [i for i, line in enumerate(lines) if line.startswith("4(")]
        lines[idx[1]] = lines[idx[0]]
        path.write_text("".join(lines))
    elif tamper == "binary":
        path = mesh / "points"
        path.write_text(path.read_text().replace("format ascii", "format binary"))
    elif tamper == "missing_neighbour":
        (mesh / "neighbour").unlink()
    elif tamper == "boundary_gap":
        path = mesh / "boundary"
        path.write_text(path.read_text().replace("startFace 1;", "startFace 5;", 1))
    elif tamper == "point_duplicate":
        path = mesh / "points"
        lines = path.read_text().splitlines(keepends=True)
        idx = [i for i, line in enumerate(lines) if line.startswith("(") and ")" in line]
        lines[idx[1]] = lines[idx[0]]
        path.write_text("".join(lines))
    elif tamper == "same_owner_neighbour":
        path = mesh / "neighbour"
        path.write_text(path.read_text().replace("\n1\n)", "\n0\n)", 1))
    else:
        path = mesh / "faces"
        lines = path.read_text().splitlines(keepends=True)
        idx = [i for i, line in enumerate(lines) if line.startswith("4(")]
        lines[idx[1]] = lines[idx[1]].replace("4(", "3(", 1)
        path.write_text("".join(lines))
    with pytest.raises(ValueError):
        screen_ascii_polymesh(case, expected_cells=expected)


def test_grid_mesh_audit_missing_solver_meshes_fails_without_validation(tmp_path):
    spec = {
        "schema_version": FAMILY_SCHEMA,
        "base_case": {
            "schema_version": FOAM_SCHEMA, "name": "synthetic",
            "room_m": [1, 1, 1], "mesh_cells": [6, 6, 6],
            "supply_flow_m3_s": 0.1, "kinematic_viscosity_m2_s": 1.5e-5,
            "max_iterations": 12, "output_interval": 6,
        },
        "mesh_levels": {
            "coarse": [6, 6, 6],
            "medium": [7, 7, 7],
            "fine": [8, 8, 8],
        },
    }
    family = tmp_path / "family"
    generate_grid_family(spec, family)
    result = audit_grid_family_polymesh(family)
    assert result["status"] == "mesh_structure_unverified"
    assert len(result["findings"]) >= 9
    assert "execution_receipt_not_integrity_verified" in result["findings"]
    assert result["physical_validation"] == "not_performed"
    assert result["engineering_review"] == "BLOCKED"


def test_mesh_cli_fails_closed_without_actual_solver_results(tmp_path, monkeypatch, capsys):
    """A generated-only nine-case family must not yield a green mesh verdict."""
    import sys
    from cleanroomx.cfd_pipeline_cli import main

    spec = {
        "schema_version": FAMILY_SCHEMA,
        "base_case": {
            "schema_version": FOAM_SCHEMA, "name": "synthetic CLI fixture",
            "room_m": [1, 1, 1], "mesh_cells": [6, 6, 6],
            "supply_flow_m3_s": 0.1, "kinematic_viscosity_m2_s": 1.5e-5,
            "max_iterations": 12, "output_interval": 6,
        },
        "mesh_levels": {
            "coarse": [6, 6, 6], "medium": [7, 7, 7], "fine": [8, 8, 8],
        },
    }
    family = tmp_path / "grid_family"
    generate_grid_family(spec, family)
    monkeypatch.setattr(sys, "argv", ["cleanroomx-cfd-pipeline", "grid-mesh-audit", str(family)])
    assert main() == 3
    stdout = capsys.readouterr().out
    assert '"mesh_structure_unverified"' in stdout
    assert '"BLOCKED"' in stdout
