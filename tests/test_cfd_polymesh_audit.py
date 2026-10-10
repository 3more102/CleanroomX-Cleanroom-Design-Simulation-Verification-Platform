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


def _mesh_fixture(case_dir, *, cells=2, disconnected=False, inlet_top=False, outlet_side=False):
    """Build synthetic adjacent or disconnected hex cells (never physical evidence)."""
    mesh_dir = case_dir / "constant/polyMesh"
    mesh_dir.mkdir(parents=True)
    points = (
        [(3*cell + x, y, z) for cell in range(cells)
         for x in range(2) for z in range(2) for y in range(2)]
        if disconnected else
        [(x, y, z) for x in range(cells + 1)
         for z in range(2) for y in range(2)]
    )
    mapping = {point: i for i, point in enumerate(points)}
    faces = {}
    for cell in range(cells):
        def point(x, y, z):
            if disconnected:
                return mapping[(3*cell + x-cell, y, z)]
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
    inlet_z = 1 if inlet_top else 0
    outlet_z = 0 if inlet_top else 1
    inlet = [v for v in external if all(points[i][2] == inlet_z for i in v[0])]
    if outlet_side:
        x_coords = [p[0] for p in points]
        x_low, x_high = min(x_coords), max(x_coords)
        outlet = [
            v for v in external if
            all(points[i][0] == x_low for i in v[0]) or
            all(points[i][0] == x_high for i in v[0])
        ]
    else:
        outlet = [v for v in external if all(points[i][2] == outlet_z for i in v[0])]
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
    "same_owner_neighbour", "unclosed_cell", "wrong_patch_type",
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
    elif tamper == "wrong_patch_type":
        path = mesh / "boundary"
        path.write_text(path.read_text().replace(
            "inlet\n{\n    type patch;", "inlet\n{\n    type wall;", 1
        ))
    else:
        path = mesh / "faces"
        lines = path.read_text().splitlines(keepends=True)
        idx = [i for i, line in enumerate(lines) if line.startswith("4(")]
        lines[idx[1]] = lines[idx[1]].replace("4(", "3(", 1)
        path.write_text("".join(lines))
    with pytest.raises(ValueError):
        screen_ascii_polymesh(case, expected_cells=expected)



@pytest.mark.parametrize("mutation", [
    "inverted_internal_face", "inverted_boundary_face",
    "nonplanar_quadrilateral", "collinear_face",
])
def test_poly_mesh_geometry_rejects_invalid_winding_or_face_area(
    tmp_path, mutation
):
    """The earlier face-count/edge checks alone cannot detect these defects."""
    case = tmp_path / "case"
    mesh = _mesh_fixture(case, cells=2)
    if mutation.startswith("inverted_"):
        path = mesh / "faces"
        lines = path.read_text(encoding="ascii").splitlines(keepends=True)
        indices = [i for i, line in enumerate(lines) if line.startswith("4(")]
        target = indices[0 if mutation == "inverted_internal_face" else 1]
        payload = lines[target].strip()
        labels = payload[2:-1].split()
        assert len(labels) == 4
        lines[target] = "4(" + " ".join(reversed(labels)) + ")\n"
        path.write_text("".join(lines), encoding="ascii")
        expected_error = "winding"
    else:
        path = mesh / "points"
        lines = path.read_text(encoding="ascii").splitlines(keepends=True)
        indices = [i for i, line in enumerate(lines)
                   if line.startswith("(") and ")" in line]
        if mutation == "nonplanar_quadrilateral":
            # Raise the far upper corner: quadrilateral becomes nonplanar,
            # while remaining finite/unique with identical cell connectivity.
            lines[indices[-1]] = "(2 1 1.3)\n"
            expected_error = "Nonplanar"
        else:
            # Collapse the first internal x=1 face onto a line while
            # retaining four distinct points; it is checked first.
            for k, index in enumerate(indices[4:8]):
                lines[index] = f"(1 {k/4} 0)\n"
            expected_error = "degenerate"
        path.write_text("".join(lines), encoding="ascii")
    with pytest.raises(ValueError, match=expected_error):
        screen_ascii_polymesh(case, expected_cells=2)


@pytest.mark.parametrize("cells", [2, 3])
def test_disconnected_hex_regions_fail_even_with_closed_well_oriented_cells(
    tmp_path, cells
):
    """Disconnected hex domains must not pass as one cleanroom fluid region."""
    case = tmp_path / "case"
    _mesh_fixture(case, cells=cells, disconnected=True)
    with pytest.raises(ValueError, match="Disconnected"):
        screen_ascii_polymesh(case, expected_cells=cells)



@pytest.mark.parametrize("configuration,outlet_side", [
    (1, True), (2, True), (3, False),
])
def test_generated_patch_locations_match_configuration(
    tmp_path, configuration, outlet_side
):
    case = tmp_path / "case"
    _mesh_fixture(case, cells=2, inlet_top=True, outlet_side=outlet_side)
    screened = screen_ascii_polymesh(
        case, expected_cells=2, configuration=configuration,
    )
    assert screened["engineering_review"] == "BLOCKED"


@pytest.mark.parametrize("inlet_top,outlet_side,configuration", [
    (False, False, 3), (True, False, 1),
    (True, True, 3),
])
def test_generated_patch_location_mismatch_is_blocked(
    tmp_path, inlet_top, outlet_side, configuration
):
    case = tmp_path / "case"
    _mesh_fixture(case, cells=2, inlet_top=inlet_top, outlet_side=outlet_side)
    with pytest.raises(ValueError, match="expected room boundary plane"):
        screen_ascii_polymesh(
            case, expected_cells=2, configuration=configuration,
        )


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


@pytest.mark.parametrize("tamper", ["scale", "translate"])
def test_source_bound_room_extent_rejects_scaled_or_shifted_hex_mesh(
    tmp_path, tamper
):
    """Independently valid hexahedra must retain source room dimensions."""
    case = tmp_path / "case"
    mesh = _mesh_fixture(case, cells=2)
    expected = ((0.0, 2.0), (0.0, 1.0), (0.0, 1.0))
    assert screen_ascii_polymesh(
        case, expected_cells=2, expected_bounds=expected
    )["engineering_review"] == "BLOCKED"
    points_file = mesh / "points"
    lines = points_file.read_text(encoding="ascii").splitlines()
    updated = []
    for line in lines:
        row = line.strip()
        if row.startswith("(") and row.endswith(")") and len(row[1:-1].split()) == 3:
            coords = [float(value) for value in row[1:-1].split()]
            if tamper == "scale":
                coords = [2 * value for value in coords]
            else:
                coords = [value + 3 for value in coords]
            updated.append("(" + " ".join(f"{value:g}" for value in coords) + ")")
        else:
            updated.append(line)
    points_file.write_text("\n".join(updated) + "\n", encoding="ascii")
    # The mesh remains structurally valid without a source-bound extent.
    assert screen_ascii_polymesh(case, expected_cells=2)["cells"] == 2
    with pytest.raises(ValueError, match="room extent disagrees"):
        screen_ascii_polymesh(case, expected_cells=2, expected_bounds=expected)


def test_source_bound_vertex_lattice_rejects_internal_plane_shift(tmp_path):
    """A changed interior plane can preserve all bounds and valid hex faces."""
    case = tmp_path / "case"
    mesh = _mesh_fixture(case, cells=2)
    bounds = ((0.0, 2.0), (0.0, 1.0), (0.0, 1.0))
    lattice = tuple(
        (float(x), float(y), float(z))
        for x in range(3) for y in range(2) for z in range(2)
    )
    assert screen_ascii_polymesh(
        case, expected_cells=2,
        expected_bounds=bounds, expected_vertices=lattice,
    )["cells"] == 2
    # Move all four interior x=1 vertices to x=.7 without touching the
    # room extrema, face planarity, or per-cell topological connectivity.
    path = mesh / "points"
    old = path.read_text(encoding="ascii")
    changed = "\n".join(
        "(0.7 " + line[3:] if line.startswith("(1 ") else line
        for line in old.splitlines()
    ) + "\n"
    assert changed != old
    path.write_text(changed, encoding="ascii")
    assert screen_ascii_polymesh(
        case, expected_cells=2, expected_bounds=bounds,
    )["cells"] == 2
    with pytest.raises(ValueError, match="source lattice"):
        screen_ascii_polymesh(
            case, expected_cells=2,
            expected_bounds=bounds, expected_vertices=lattice,
        )


def test_source_lattice_accepts_reordered_points_and_bounded_roundoff(tmp_path):
    """Vertex matching is set-based, not dependent on OpenFOAM point IDs."""
    from cleanroomx.cfd_polymesh_geometry import validate_generated_vertex_positions
    lattice = tuple((float(x), float(y), float(z))
                    for x in range(3) for y in range(2) for z in range(2))
    perturbed = [(x + (1e-8 if x == 1 else 0.0), y, z)
                 for x, y, z in reversed(lattice)]
    validate_generated_vertex_positions(
        perturbed, lattice,
        bounds_m=((0.0, 2.0), (0.0, 1.0), (0.0, 1.0)),
    )
