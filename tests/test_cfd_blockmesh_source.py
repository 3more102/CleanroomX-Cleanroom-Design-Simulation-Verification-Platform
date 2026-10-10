"""Synthetic CleanroomX blockMesh source integrity tests; not real CFD."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cleanroomx.cfd_blockmesh_source import (
    _validate_generated_structured_grid,
    verify_generated_blockmesh_source,
)
from cleanroomx.cfd_grid_family import SCHEMA as FAMILY_SCHEMA, generate_grid_family
from cleanroomx.cfd_grid_runner import _verify_generated_inputs, run_grid_family
from cleanroomx.cfd_openfoam import SCHEMA, build_openfoam_files


@pytest.fixture
def generated_source(tmp_path):
    spec = {
        "schema_version": SCHEMA,
        "name": "SYNTHETIC parser fixture (not physical verification)",
        "room_m": [1.0, 1.5, 2.0],
        "mesh_cells": [6, 6, 6],
        "supply_flow_m3_s": 0.1,
        "kinematic_viscosity_m2_s": 1.5e-5,
        "max_iterations": 12,
        "output_interval": 6,
    }
    files, meta = build_openfoam_files(spec, 1)
    path = tmp_path / "blockMeshDict"
    path.write_text(files["system/blockMeshDict"], encoding="utf-8")
    return path, meta["mesh_cells"]


def test_actual_generated_ascii_source_matches_declared_hexahedra(generated_source):
    path, cells = generated_source
    result = verify_generated_blockmesh_source(path, expected_cells=cells)
    assert result["hex_block_count"] == cells
    assert result["vertex_count"] == 7 * 7 * 7
    assert result["bounds_m"] == ((0.0, 1.0), (0.0, 1.5), (0.0, 2.0))
    assert "vertices_m" not in result
    assert "hex_cells" not in result
    assert "boundary_faces" not in result
    captured = verify_generated_blockmesh_source(
        path, expected_cells=cells, capture_vertices=True,
    )
    assert len(captured["vertices_m"]) == result["vertex_count"]
    assert len(captured["hex_cells"]) == cells
    assert len(set(captured["hex_cells"])) == cells
    assert all(len(cell) == 8 and len(set(cell)) == 8
               for cell in captured["hex_cells"])
    assert set(captured["boundary_faces"]) == {"inlet", "outlet", "walls"}
    assert all(captured["boundary_faces"][patch]
               for patch in ("inlet", "outlet"))
    assert all(len(set(faces)) == len(faces)
               for faces in captured["boundary_faces"].values())
    assert len(set(captured["vertices_m"])) == 343
    assert min(v[0] for v in captured["vertices_m"]) == 0
    assert max(v[2] for v in captured["vertices_m"]) == 2


@pytest.mark.parametrize("mutation", [
    "declared_cell_count", "removed_block", "duplicate_block", "bad_vertex_index",
    "nonunit_subdivision", "unexpected_hex_declaration", "duplicate_vertices_section",
])
def test_generated_source_parser_rejects_invalid_block_structure(
    generated_source, mutation
):
    path, count = generated_source
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    block_indices = [
        index for index, line in enumerate(lines)
        if line.lstrip().startswith("hex ")
    ]
    assert len(block_indices) == count
    expected = count
    if mutation == "declared_cell_count":
        expected += 1
    elif mutation == "removed_block":
        del lines[block_indices[1]]
    elif mutation == "duplicate_block":
        lines[block_indices[1]] = lines[block_indices[0]]
    elif mutation == "bad_vertex_index":
        i = block_indices[0]
        lines[i] = lines[i].replace("hex (", "hex (999999 ", 1)
    elif mutation == "nonunit_subdivision":
        i = block_indices[0]
        lines[i] = lines[i].replace(
            ") (1 1 1) simpleGrading", ") (2 1 1) simpleGrading", 1
        )
    elif mutation == "unexpected_hex_declaration":
        lines[block_indices[1]] = "    hex (0 1 2 3 4 5 6 7) #codeStream\n"
    else:
        lines.append("vertices\n(\n    (0 0 0)\n);\n")
    path.write_text("".join(lines), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_generated_blockmesh_source(path, expected_cells=expected)


def test_self_rehashed_forged_block_dict_cannot_launch_solver(tmp_path, monkeypatch):
    spec = {
        "schema_version": FAMILY_SCHEMA,
        "base_case": {
            "schema_version": SCHEMA,
            "name": "SYNTHETIC manifest tamper fixture",
            "room_m": [1, 1, 1],
            "mesh_cells": [6, 6, 6],
            "supply_flow_m3_s": 0.1,
            "kinematic_viscosity_m2_s": 1.5e-5,
            "max_iterations": 12,
            "output_interval": 6,
        },
        "mesh_levels": {
            "coarse": [6, 6, 6],
            "medium": [7, 7, 7],
            "fine": [8, 8, 8],
        },
    }
    root = tmp_path / "family"
    generate_grid_family(spec, root)
    rel = "configuration_1/coarse/system/blockMeshDict"
    path = root / rel
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    one_block = next(index for index, line in enumerate(lines)
                     if line.lstrip().startswith("hex "))
    del lines[one_block]
    path.write_text("".join(lines), encoding="utf-8")
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def no_external_tools(_name):
        pytest.fail("CFD subprocess preflight attempted despite invalid mesh source")

    import cleanroomx.cfd_grid_runner as runner
    monkeypatch.setattr(runner.shutil, "which", no_external_tools)
    with pytest.raises(ValueError, match="hex count"):
        run_grid_family(root, timeout_seconds=60)
    assert not (root / ".grid_run_reserved").exists()
    assert not (root / "grid_run_evidence.json").exists()


@pytest.mark.parametrize("mutation", ["scaled", "duplicate", "missing"])
def test_generated_source_rejects_nonunit_convert_to_meters(
    generated_source, mutation
):
    path, cells = generated_source
    contents = path.read_text(encoding="utf-8")
    if mutation == "scaled":
        contents = contents.replace("convertToMeters 1;", "convertToMeters 100;", 1)
    elif mutation == "duplicate":
        contents += "\nconvertToMeters 1;\n"
    else:
        contents = contents.replace("convertToMeters 1;", "", 1)
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError, match="convertToMeters"):
        verify_generated_blockmesh_source(path, expected_cells=cells)


@pytest.mark.parametrize("tamper", ["wrong_patch_type", "missing_boundary_face"])
def test_generated_source_boundary_capture_rejects_tampered_faces(
    generated_source, tamper
):
    path, cells = generated_source
    source = path.read_text(encoding="utf-8")
    if tamper == "wrong_patch_type":
        source = source.replace(
            "inlet\n    {\n        type patch;",
            "inlet\n    {\n        type wall;",
            1,
        )
    else:
        lines = source.splitlines(keepends=True)
        start = lines.index("    inlet\n")
        face_line = next(
            index for index in range(start + 1, len(lines))
            if lines[index].startswith("            (")
        )
        del lines[face_line]
        source = "".join(lines)
    path.write_text(source, encoding="utf-8")
    # Preflight's default, non-capturing path must fail too: this is the
    # path grid-run / grid-verify use before external commands can start.
    with pytest.raises(ValueError, match="boundary"):
        verify_generated_blockmesh_source(path, expected_cells=cells)
    with pytest.raises(ValueError, match="boundary"):
        verify_generated_blockmesh_source(
            path, expected_cells=cells, capture_vertices=True,
        )


@pytest.mark.parametrize("tamper", ["wrong_patch_type", "missing_boundary_face"])
def test_rehashed_bad_boundary_fails_before_external_foam_process(
    tmp_path, monkeypatch, tamper
):
    """Synthetic preflight tampering: new SHA-256 cannot bypass topology gate."""
    spec = {
        "schema_version": FAMILY_SCHEMA,
        "base_case": {
            "schema_version": SCHEMA,
            "name": "SYNTHETIC boundary tamper, not actual CFD",
            "room_m": [1, 1, 1],
            "mesh_cells": [6, 6, 6],
            "supply_flow_m3_s": 0.1,
            "kinematic_viscosity_m2_s": 1.5e-5,
            "max_iterations": 12,
            "output_interval": 6,
        },
        "mesh_levels": {
            "coarse": [6, 6, 6],
            "medium": [7, 7, 7],
            "fine": [8, 8, 8],
        },
    }
    root = tmp_path / "family"
    generate_grid_family(spec, root)
    relative = "configuration_1/coarse/system/blockMeshDict"
    source_path = root / relative
    raw = source_path.read_text(encoding="utf-8")
    if tamper == "wrong_patch_type":
        raw = raw.replace(
            "inlet\n    {\n        type patch;",
            "inlet\n    {\n        type wall;",
            1,
        )
    else:
        lines = raw.splitlines(keepends=True)
        first = lines.index("    inlet\n")
        index = next(
            i for i in range(first + 1, len(lines))
            if lines[i].startswith("            (")
        )
        del lines[index]
        raw = "".join(lines)
    source_path.write_text(raw, encoding="utf-8")
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][relative] = hashlib.sha256(
        source_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8",
    )
    import cleanroomx.cfd_grid_runner as runner
    def external_call_forbidden(_name):
        pytest.fail("Malformed source boundary reached external tool discovery")
    monkeypatch.setattr(runner.shutil, "which", external_call_forbidden)
    with pytest.raises(ValueError, match="boundary"):
        run_grid_family(root, timeout_seconds=60)
    assert not (root / ".grid_run_reserved").exists()
    assert not (root / "grid_run_evidence.json").exists()


@pytest.mark.parametrize("tamper", [
    "include", "code_stream", "extra_directive", "changed_class",
    "duplicate_format", "nonempty_edges", "patch_merge",
])
def test_generated_source_rejects_noncanonical_outer_grammar(generated_source, tamper):
    """A rehashed manifest must not legitimize unknown OpenFOAM directives."""
    path, count = generated_source
    source = path.read_text(encoding="utf-8")
    if tamper == "include":
        source += '\n#include "externalDict"\n'
    elif tamper == "code_stream":
        source += '\n#codeStream { code "external"; }\n'
    elif tamper == "extra_directive":
        source += "\nfunctions { unexpected 1; }\n"
    elif tamper == "changed_class":
        source = source.replace("class dictionary;", "class volScalarField;", 1)
    elif tamper == "duplicate_format":
        source = source.replace("format ascii;", "format ascii;\n    format binary;", 1)
    elif tamper == "nonempty_edges":
        source = source.replace("edges ();", "edges ( arc (0 1) (0 0 0) );", 1)
    else:
        source = source.replace(
            "mergePatchPairs ();", "mergePatchPairs ((inlet outlet));", 1
        )
    path.write_text(source, encoding="utf-8")
    with pytest.raises(ValueError, match="Noncanonical generated blockMesh envelope"):
        verify_generated_blockmesh_source(path, expected_cells=count)


def test_rehashed_included_dict_fails_before_solver_discovery(tmp_path, monkeypatch):
    """Source-level directives fail even if local unsigned hashes were rewritten."""
    spec = {
        "schema_version": FAMILY_SCHEMA,
        "base_case": {
            "schema_version": SCHEMA,
            "name": "SYNTHETIC external directive preflight",
            "room_m": [1, 1, 1],
            "mesh_cells": [6, 6, 6],
            "supply_flow_m3_s": 0.1,
            "kinematic_viscosity_m2_s": 1.5e-5,
            "max_iterations": 12,
            "output_interval": 6,
        },
        "mesh_levels": {
            "coarse": [6, 6, 6],
            "medium": [7, 7, 7],
            "fine": [8, 8, 8],
        },
    }
    root = tmp_path / "family"
    generate_grid_family(spec, root)
    relative = "configuration_1/coarse/system/blockMeshDict"
    source_path = root / relative
    source_path.write_text(
        source_path.read_text(encoding="utf-8")
        + '\n#include "arbitraryDict"\n',
        encoding="utf-8",
    )
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][relative] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    import cleanroomx.cfd_grid_runner as runner
    def forbidden_discovery(_name):
        pytest.fail("Unapproved OpenFOAM directive reached solver discovery")
    monkeypatch.setattr(runner.shutil, "which", forbidden_discovery)
    with pytest.raises(ValueError, match="Noncanonical generated blockMesh envelope"):
        run_grid_family(root, timeout_seconds=60)
    assert not (root / ".grid_run_reserved").exists()
    assert not (root / "grid_run_evidence.json").exists()



def _rewrite_first_generated_inlet_face(source, *, reverse):
    """Change ordering without changing patch membership or face counts."""
    lines = source.splitlines(keepends=True)
    inlet = lines.index("    inlet\n")
    face_line = next(
        index for index in range(inlet + 1, len(lines))
        if lines[index].startswith("            (")
    )
    vertices = lines[face_line].strip()[1:-1].split()
    assert len(vertices) == 4
    if reverse:
        vertices = [vertices[0], vertices[3], vertices[2], vertices[1]]
    else:
        vertices = vertices[1:] + vertices[:1]
    lines[face_line] = "            (" + " ".join(vertices) + ")\n"
    return "".join(lines)


@pytest.mark.parametrize("tamper", [
    "inverted_lower_edge", "inverted_upper_edge", "skewed_corner",
])
def test_generated_source_rejects_inverted_or_twisted_hex_geometry(
    generated_source, tamper
):
    path, cells = generated_source
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if tamper == "skewed_corner":
        vertex = next(
            i for i, line in enumerate(lines) if line.strip() == "(0 0 0)"
        )
        lines[vertex] = lines[vertex].replace(
            "(0 0 0)", "(0.13 0.07 0)", 1
        )
    else:
        block = next(
            i for i, line in enumerate(lines)
            if line.lstrip().startswith("hex (")
        )
        prefix, rest = lines[block].split("hex (", 1)
        ids, suffix = rest.split(")", 1)
        values = ids.split()
        first, second = (0, 1) if tamper == "inverted_lower_edge" else (4, 5)
        values[first], values[second] = values[second], values[first]
        lines[block] = prefix + "hex (" + " ".join(values) + ")" + suffix
    path.write_text("".join(lines), encoding="utf-8")
    with pytest.raises(ValueError, match="Noncanonical generated hex geometry"):
        verify_generated_blockmesh_source(path, expected_cells=cells)


def test_generated_source_rejects_reversed_boundary_normal(generated_source):
    path, cells = generated_source
    path.write_text(_rewrite_first_generated_inlet_face(
        path.read_text(encoding="utf-8"), reverse=True,
    ), encoding="utf-8")
    with pytest.raises(ValueError, match="boundary face winding"):
        verify_generated_blockmesh_source(path, expected_cells=cells)
    with pytest.raises(ValueError, match="boundary face winding"):
        verify_generated_blockmesh_source(
            path, expected_cells=cells, capture_vertices=True,
        )


def test_generated_source_accepts_cyclic_boundary_face_rotation(generated_source):
    path, cells = generated_source
    path.write_text(_rewrite_first_generated_inlet_face(
        path.read_text(encoding="utf-8"), reverse=False,
    ), encoding="utf-8")
    verified = verify_generated_blockmesh_source(path, expected_cells=cells)
    assert verified["hex_block_count"] == cells


def test_rehashed_reversed_inlet_normal_never_reaches_openfoam(
    tmp_path, monkeypatch
):
    """Only a synthetic preflight guard; no OpenFOAM execution or measurements."""
    spec = {
        "schema_version": FAMILY_SCHEMA,
        "base_case": {
            "schema_version": SCHEMA,
            "name": "SYNTHETIC reversed inlet normal",
            "room_m": [1, 1, 1],
            "mesh_cells": [6, 6, 6],
            "supply_flow_m3_s": 0.1,
            "kinematic_viscosity_m2_s": 1.5e-5,
            "max_iterations": 12,
            "output_interval": 6,
        },
        "mesh_levels": {
            "coarse": [6, 6, 6],
            "medium": [7, 7, 7],
            "fine": [8, 8, 8],
        },
    }
    root = tmp_path / "family"
    generate_grid_family(spec, root)
    relative = "configuration_1/coarse/system/blockMeshDict"
    source_path = root / relative
    source_path.write_text(_rewrite_first_generated_inlet_face(
        source_path.read_text(encoding="utf-8"), reverse=True,
    ), encoding="utf-8")
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][relative] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    import cleanroomx.cfd_grid_runner as runner

    def forbidden_discovery(_name):
        pytest.fail("Invalid inlet face winding reached external solver discovery")

    monkeypatch.setattr(runner.shutil, "which", forbidden_discovery)
    with pytest.raises(ValueError, match="boundary face winding"):
        run_grid_family(root, timeout_seconds=60)
    assert not (root / ".grid_run_reserved").exists()
    assert not (root / "grid_run_evidence.json").exists()



def _rectilinear_two_row_fixture(x_coordinates, x_intervals):
    """Build minimal synthetic axis-aligned hexes without an OpenFOAM process."""
    points = [
        (float(x), float(y), float(z))
        for z in (0, 1)
        for y in (0, 1)
        for x in x_coordinates
    ]
    nx = len(x_coordinates)

    def vertex(i, j, k):
        return (k * 2 + j) * nx + i

    blocks = [
        (
            vertex(left, 0, 0), vertex(right, 0, 0),
            vertex(right, 1, 0), vertex(left, 1, 0),
            vertex(left, 0, 1), vertex(right, 0, 1),
            vertex(right, 1, 1), vertex(left, 1, 1),
        )
        for left, right in x_intervals
    ]
    return points, blocks


def test_generated_grid_accepts_complete_nonuniform_cartesian_tiling():
    points, blocks = _rectilinear_two_row_fixture(
        [0, 0.75, 2.5], [(0, 1), (1, 2)]
    )
    assert _validate_generated_structured_grid(points, blocks) is None


@pytest.mark.parametrize("intervals,diagnostic", [
    ([(0, 1), (2, 3)], "do not tile"),
    ([(0, 1), (0, 1), (2, 3)], "overlap"),
    ([(0, 2), (1, 2), (2, 3)], "skips"),
])
def test_generated_grid_rejects_holes_overlaps_and_skipped_planes(
    intervals, diagnostic
):
    points, blocks = _rectilinear_two_row_fixture([0, 1, 2, 4], intervals)
    with pytest.raises(ValueError, match=diagnostic):
        _validate_generated_structured_grid(points, blocks)


def test_generated_source_rejects_unreferenced_vertex(generated_source):
    """Every source vertex must be part of the complete structured grid."""
    path, count = generated_source
    source = path.read_text(encoding="utf-8")
    marker = ");\nblocks\n(\n"
    assert source.count(marker) == 1
    source = source.replace(marker, "    (99 99 99)\n" + marker, 1)
    path.write_text(source, encoding="utf-8")
    with pytest.raises(ValueError, match="complete Cartesian grid"):
        verify_generated_blockmesh_source(path, expected_cells=count)


def test_rehashed_unused_vertex_does_not_reach_solver_discovery(
    tmp_path, monkeypatch
):
    """Self-rehashed local source cannot bypass Cartesian completeness."""
    spec = {
        "schema_version": FAMILY_SCHEMA,
        "base_case": {
            "schema_version": SCHEMA,
            "name": "SYNTHETIC injected unused mesh point",
            "room_m": [1, 1, 1],
            "mesh_cells": [6, 6, 6],
            "supply_flow_m3_s": 0.1,
            "kinematic_viscosity_m2_s": 1.5e-5,
            "max_iterations": 12,
            "output_interval": 6,
        },
        "mesh_levels": {
            "coarse": [6, 6, 6],
            "medium": [7, 7, 7],
            "fine": [8, 8, 8],
        },
    }
    root = tmp_path / "family"
    generate_grid_family(spec, root)
    relative = "configuration_1/coarse/system/blockMeshDict"
    source_path = root / relative
    raw = source_path.read_text(encoding="utf-8")
    marker = ");\nblocks\n(\n"
    assert raw.count(marker) == 1
    source_path.write_text(
        raw.replace(marker, "    (99 99 99)\n" + marker, 1),
        encoding="utf-8",
    )
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][relative] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    import cleanroomx.cfd_grid_runner as runner

    def forbidden_discovery(_name):
        pytest.fail("An invalid Cartesian mesh reached external solver discovery")

    monkeypatch.setattr(runner.shutil, "which", forbidden_discovery)
    with pytest.raises(ValueError, match="complete Cartesian grid"):
        run_grid_family(root, timeout_seconds=60)
    assert not (root / ".grid_run_reserved").exists()
    assert not (root / "grid_run_evidence.json").exists()



def _swap_inlet_wall_face_membership(source: str) -> str:
    """Move one canonical face each way without changing geometry or normals."""
    rows = source.splitlines(keepends=True)
    inlet = rows.index("    inlet\n")
    walls = rows.index("    walls\n")
    inlet_face = next(
        index for index in range(inlet + 1, walls)
        if rows[index].startswith("            (")
    )
    wall_face = next(
        index for index in range(walls + 1, len(rows))
        if rows[index].startswith("            (")
    )
    rows[inlet_face], rows[wall_face] = rows[wall_face], rows[inlet_face]
    return "".join(rows)


@pytest.mark.parametrize("configuration", [1, 2, 3])
def test_source_rejects_patch_reassignment_with_intact_face_topology(
    tmp_path, configuration
):
    """A role-swap preserves face counts, vertex sets and face windings."""
    spec = {
        "schema_version": SCHEMA,
        "name": "SYNTHETIC expected ventilation layout",
        "room_m": [1.0, 1.5, 2.0],
        "mesh_cells": [6, 6, 6],
        "supply_flow_m3_s": 0.1,
        "kinematic_viscosity_m2_s": 1.5e-5,
        "max_iterations": 12,
        "output_interval": 6,
    }
    generated, metadata = build_openfoam_files(spec, configuration)
    path = tmp_path / "blockMeshDict"
    path.write_text(generated["system/blockMeshDict"], encoding="utf-8")
    cells = metadata["mesh_cells"]

    verified = verify_generated_blockmesh_source(
        path, expected_cells=cells, expected_configuration=configuration
    )
    assert verified["hex_block_count"] == cells
    assert verify_generated_blockmesh_source(
        path, expected_cells=cells, capture_vertices=True,
        expected_configuration=configuration
    )["boundary_faces"]

    path.write_text(_swap_inlet_wall_face_membership(
        path.read_text(encoding="utf-8")
    ), encoding="utf-8")
    # Generic source topology checks cannot determine the intended operating
    # configuration; case-bound verification must detect role reassignment.
    assert verify_generated_blockmesh_source(
        path, expected_cells=cells
    )["hex_block_count"] == cells
    with pytest.raises(ValueError, match="boundary patch membership"):
        verify_generated_blockmesh_source(
            path, expected_cells=cells, expected_configuration=configuration
        )
    with pytest.raises(ValueError, match="boundary patch membership"):
        verify_generated_blockmesh_source(
            path, expected_cells=cells, capture_vertices=True,
            expected_configuration=configuration
        )


@pytest.mark.parametrize("invalid_configuration", [True, 0, 4, "1", 1.0])
def test_source_rejects_invalid_expected_configuration(
    generated_source, invalid_configuration
):
    path, count = generated_source
    with pytest.raises(ValueError, match="Invalid expected generated mesh configuration"):
        verify_generated_blockmesh_source(
            path, expected_cells=count, expected_configuration=invalid_configuration
        )


def test_generated_source_rejects_wrong_ventilation_configuration(generated_source):
    path, cells = generated_source
    with pytest.raises(ValueError, match="boundary patch membership"):
        verify_generated_blockmesh_source(
            path, expected_cells=cells, expected_configuration=2
        )


def test_rehashed_wrong_patch_roles_fail_before_solver_discovery(
    tmp_path, monkeypatch
):
    """No claimed OpenFOAM run: tampered local manifest cannot authorize input."""
    spec = {
        "schema_version": FAMILY_SCHEMA,
        "base_case": {
            "schema_version": SCHEMA,
            "name": "SYNTHETIC swapped inlet and wall roles",
            "room_m": [1, 1, 1],
            "mesh_cells": [6, 6, 6],
            "supply_flow_m3_s": 0.1,
            "kinematic_viscosity_m2_s": 1.5e-5,
            "max_iterations": 12,
            "output_interval": 6,
        },
        "mesh_levels": {
            "coarse": [6, 6, 6],
            "medium": [7, 7, 7],
            "fine": [8, 8, 8],
        },
    }
    root = tmp_path / "family"
    generate_grid_family(spec, root)
    relative = "configuration_1/coarse/system/blockMeshDict"
    path = root / relative
    path.write_text(
        _swap_inlet_wall_face_membership(path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    import cleanroomx.cfd_grid_runner as runner

    def forbidden_discovery(_name):
        pytest.fail("Tampered boundary roles reached OpenFOAM discovery")

    monkeypatch.setattr(runner.shutil, "which", forbidden_discovery)
    with pytest.raises(ValueError, match="boundary patch membership"):
        run_grid_family(root, timeout_seconds=60)
    assert not (root / ".grid_run_reserved").exists()
    assert not (root / "grid_run_evidence.json").exists()



@pytest.mark.parametrize("initial_levels,case,forged_axes,expected_error", [
    (
        {"coarse": [6, 6, 6], "medium": [7, 8, 9], "fine": [8, 10, 11]},
        "configuration_2/medium",
        [7, 9, 8],
        "generated mesh axes differ across configurations",
    ),
    (
        {"coarse": [7, 7, 7], "medium": [8, 9, 10], "fine": [10, 12, 13]},
        "configuration_1/medium",
        [6, 10, 12],
        "generated mesh axes do not refine strictly",
    ),
])
def test_same_total_cells_cannot_forge_grid_axis_refinement(
    tmp_path, monkeypatch, initial_levels, case, forged_axes, expected_error
):
    """Source geometry, hashes and total cell counts can all still agree."""
    spec = {
        "schema_version": FAMILY_SCHEMA,
        "base_case": {
            "schema_version": SCHEMA,
            "name": "SYNTHETIC grid-axis replay test",
            "room_m": [1, 1.5, 2],
            "mesh_cells": [6, 6, 6],
            "supply_flow_m3_s": 0.1,
            "kinematic_viscosity_m2_s": 1.5e-5,
            "max_iterations": 12,
            "output_interval": 6,
        },
        "mesh_levels": initial_levels,
    }
    root = tmp_path / "family"
    generate_grid_family(spec, root)
    original_manifest_sha = _verify_generated_inputs(root)
    assert len(original_manifest_sha) == 64

    config_number = int(case.split("/", 1)[0].removeprefix("configuration_"))
    level = case.split("/", 1)[1]
    original_count = 1
    for dimension in initial_levels[level]:
        original_count *= dimension
    tampered_count = 1
    for dimension in forged_axes:
        tampered_count *= dimension
    assert tampered_count == original_count

    modified_spec = dict(spec["base_case"], mesh_cells=forged_axes)
    forged_files, forged_metadata = build_openfoam_files(
        modified_spec, config_number
    )
    assert forged_metadata["mesh_cells"] == original_count
    relative = f"{case}/system/blockMeshDict"
    source_path = root / relative
    source_path.write_text(
        forged_files["system/blockMeshDict"], encoding="utf-8"
    )
    assert verify_generated_blockmesh_source(
        source_path, expected_cells=original_count,
        expected_configuration=config_number
    )["axis_cell_counts"] == tuple(forged_axes)

    # The manifest remains locally unsigned; regenerating its digest alone
    # must not promote an anisotropically replayed mesh family.
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][relative] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=expected_error):
        _verify_generated_inputs(root)

    import cleanroomx.cfd_grid_runner as runner

    def forbidden_discovery(_name):
        pytest.fail("Forged source grid dimensions reached external solver discovery")

    monkeypatch.setattr(runner.shutil, "which", forbidden_discovery)
    with pytest.raises(ValueError, match=expected_error):
        run_grid_family(root, timeout_seconds=60)
    assert not (root / ".grid_run_reserved").exists()
    assert not (root / "grid_run_evidence.json").exists()


def test_source_axis_counts_are_returned_without_audit_snapshots(generated_source):
    path, cells = generated_source
    compact = verify_generated_blockmesh_source(path, expected_cells=cells)
    detailed = verify_generated_blockmesh_source(
        path, expected_cells=cells, capture_vertices=True,
    )
    assert compact["axis_cell_counts"] == detailed["axis_cell_counts"] == (6, 6, 6)
    assert "vertices_m" not in compact
    assert "hex_cells" not in compact



def _shift_generated_source_x(source: str, delta: float) -> str:
    """Translate only the generated vertex section; preserve other input bytes."""
    prefix, marker, tail = source.partition("vertices\n(\n")
    assert marker
    vertex_section, closing, suffix = tail.partition("\n);\nblocks\n(\n")
    assert closing
    translated = []
    for line in vertex_section.splitlines():
        values = line.strip()[1:-1].split()
        assert len(values) == 3
        shifted_x = format(float(values[0]) + delta, ".12g")
        translated.append(
            "    (" + " ".join((shifted_x, values[1], values[2])) + ")"
        )
    return prefix + marker + "\n".join(translated) + closing + suffix


@pytest.mark.parametrize("tamper,expected_error", [
    ("scaled_one_case", "generated room bounds differ across cases"),
    ("translate_all_cases", "generated room origin is not canonical"),
])
def test_rehashed_room_domain_mutations_fail_before_solver_discovery(
    tmp_path, monkeypatch, tamper, expected_error
):
    """Same cell counts/layout cannot authorize inconsistent physical domains."""
    spec = {
        "schema_version": FAMILY_SCHEMA,
        "base_case": {
            "schema_version": SCHEMA,
            "name": "SYNTHETIC physical-domain consistency fixture",
            "room_m": [1, 1.5, 2],
            "mesh_cells": [6, 6, 6],
            "supply_flow_m3_s": 0.1,
            "kinematic_viscosity_m2_s": 1.5e-5,
            "max_iterations": 12,
            "output_interval": 6,
        },
        "mesh_levels": {
            "coarse": [6, 6, 6],
            "medium": [7, 7, 7],
            "fine": [8, 8, 8],
        },
    }
    root = tmp_path / "grid-family"
    generate_grid_family(spec, root)
    assert len(_verify_generated_inputs(root)) == 64
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if tamper == "scaled_one_case":
        key = "configuration_2/medium"
        forged_spec = dict(
            spec["base_case"], mesh_cells=[7, 7, 7],
            room_m=[2, 1.5, 2]
        )
        files, _ = build_openfoam_files(forged_spec, 2)
        relative = f"{key}/system/blockMeshDict"
        target = root / relative
        target.write_text(files["system/blockMeshDict"], encoding="utf-8")
        manifest["files"][relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    else:
        for configuration in (1, 2, 3):
            for level in ("coarse", "medium", "fine"):
                relative = (
                    f"configuration_{configuration}/{level}/system/blockMeshDict"
                )
                target = root / relative
                target.write_text(
                    _shift_generated_source_x(
                        target.read_text(encoding="utf-8"), 0.25
                    ),
                    encoding="utf-8",
                )
                manifest["files"][relative] = hashlib.sha256(
                    target.read_bytes()
                ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match=expected_error):
        _verify_generated_inputs(root)

    import cleanroomx.cfd_grid_runner as runner

    def forbidden_discovery(_name):
        pytest.fail("Forged room domain reached OpenFOAM discovery")

    monkeypatch.setattr(runner.shutil, "which", forbidden_discovery)
    with pytest.raises(ValueError, match=expected_error):
        run_grid_family(root, timeout_seconds=60)
    assert not (root / ".grid_run_reserved").exists()
    assert not (root / "grid_run_evidence.json").exists()



def test_source_axes_capture_interior_planes_without_full_mesh_snapshot(
    generated_source
):
    path, cells = generated_source
    compact = verify_generated_blockmesh_source(path, expected_cells=cells)
    assert len(compact["axis_positions_m"]) == 3
    assert tuple(len(axis) for axis in compact["axis_positions_m"]) == (7, 7, 7)
    assert compact["axis_positions_m"][0][0] == 0
    assert compact["axis_positions_m"][0][-1] == 1
    assert "vertices_m" not in compact
    assert "hex_cells" not in compact


def test_rehashed_interior_grid_plane_shift_fails_before_solver_discovery(
    tmp_path, monkeypatch
):
    """Nonuniform internal plane with equal cell counts and room bounds fails."""
    spec = {
        "schema_version": FAMILY_SCHEMA,
        "base_case": {
            "schema_version": SCHEMA,
            "name": "SYNTHETIC interior plane mismatch",
            "room_m": [1, 1.5, 2],
            "mesh_cells": [6, 6, 6],
            "supply_flow_m3_s": 0.1,
            "kinematic_viscosity_m2_s": 1.5e-5,
            "max_iterations": 12,
            "output_interval": 6,
        },
        "mesh_levels": {
            "coarse": [6, 6, 6],
            "medium": [7, 7, 7],
            "fine": [8, 8, 8],
        },
    }
    root = tmp_path / "family"
    generate_grid_family(spec, root)
    assert len(_verify_generated_inputs(root)) == 64

    relative = "configuration_2/medium/system/blockMeshDict"
    path = root / relative
    old = format(1.0 / 7.0, ".12g")
    original = path.read_text(encoding="utf-8")
    prefix, marker, tail = original.partition("vertices\n(\n")
    assert marker
    body, closing, suffix = tail.partition("\n);\nblocks\n(\n")
    assert closing
    adjusted = []
    moved_vertices = 0
    for line in body.splitlines():
        values = line.strip()[1:-1].split()
        if values[0] == old:
            values[0] = "0.155"
            moved_vertices += 1
        adjusted.append("    (" + " ".join(values) + ")")
    assert moved_vertices == 64
    path.write_text(
        prefix + marker + "\n".join(adjusted) + closing + suffix,
        encoding="utf-8",
    )
    geometry = verify_generated_blockmesh_source(
        path, expected_cells=343, expected_configuration=2
    )
    assert geometry["axis_cell_counts"] == (7, 7, 7)
    assert geometry["bounds_m"] == ((0.0, 1.0), (0.0, 1.5), (0.0, 2.0))
    assert 0.155 in geometry["axis_positions_m"][0]

    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="internal grid planes differ"):
        _verify_generated_inputs(root)

    import cleanroomx.cfd_grid_runner as runner

    def forbidden_discovery(_name):
        pytest.fail("Altered internal source planes reached solver discovery")

    monkeypatch.setattr(runner.shutil, "which", forbidden_discovery)
    with pytest.raises(ValueError, match="internal grid planes differ"):
        run_grid_family(root, timeout_seconds=60)
    assert not (root / ".grid_run_reserved").exists()
    assert not (root / "grid_run_evidence.json").exists()
