"""Synthetic CleanroomX blockMesh source integrity tests; not real CFD."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cleanroomx.cfd_blockmesh_source import verify_generated_blockmesh_source
from cleanroomx.cfd_grid_family import SCHEMA as FAMILY_SCHEMA, generate_grid_family
from cleanroomx.cfd_grid_runner import run_grid_family
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
