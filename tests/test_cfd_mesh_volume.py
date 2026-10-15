"""Synthetic mesh-integrity tests; these do not qualify CFD physics."""
import hashlib

import pytest

from cleanroomx.cfd_vtk import (
    _parse_checkmesh_volume_summary,
    audit_openfoam_checkmesh_poly_mesh_volume,
)


FOUNDATION_CHECKMESH_SAMPLE = """\
Mesh stats
    cells:            216
Checking geometry...
    Min volume = 0.05555555544. Max volume = 0.05555555578.  Total volume = 12.  Cell volumes OK.
Mesh OK.
End
"""


def _hex_faces(hex_vertices):
    a, b, c, d, e, f, g, h = hex_vertices
    return (
        (a, d, c, b), (e, f, g, h), (a, e, h, d),
        (b, c, g, f), (a, b, f, e), (d, h, g, c),
    )


def two_cell_case(case_dir):
    mesh = case_dir / "constant" / "polyMesh"
    mesh.mkdir(parents=True)
    points = [
        (x, y, z)
        for z in (0, 1)
        for y in (0, 1)
        for x in (0, 1, 2)
    ]
    (mesh / "points").write_text(
        "FoamFile { format ascii; class vectorField; object points; }\n"
        + str(len(points)) + "\n(\n"
        + "\n".join(f"({x} {y} {z})" for x, y, z in points)
        + "\n);\n",
        encoding="ascii",
    )
    blocks = (
        (0, 1, 4, 3, 6, 7, 10, 9),
        (1, 2, 5, 4, 7, 8, 11, 10),
    )
    cell_faces = [_hex_faces(block) for block in blocks]
    face_by_signature = {}
    for cell_id, faces in enumerate(cell_faces):
        for face in faces:
            signature = tuple(sorted(face))
            face_by_signature.setdefault(signature, []).append((cell_id, face))
    internal = [items for items in face_by_signature.values() if len(items) == 2]
    assert len(internal) == 1
    shared = internal[0]
    ordered_faces = [shared[0][1]]
    owners = [shared[0][0]]
    boundary_faces = [
        (cell_id, face)
        for items in face_by_signature.values()
        if len(items) == 1
        for cell_id, face in items
    ]
    for owner, face in boundary_faces:
        ordered_faces.append(face)
        owners.append(owner)
    rendered_faces = [f"{len(face)}(" + " ".join(map(str, face)) + ")" for face in ordered_faces]
    (mesh / "faces").write_text(
        "FoamFile { format ascii; class faceList; object faces; }\n"
        + str(len(ordered_faces)) + "\n(\n"
        + "\n".join(rendered_faces) + "\n);\n",
        encoding="ascii",
    )
    (mesh / "owner").write_text(
        "FoamFile { format ascii; class labelList; object owner; }\n"
        + str(len(owners)) + "\n(\n"
        + "\n".join(map(str, owners)) + "\n);\n",
        encoding="ascii",
    )
    (mesh / "neighbour").write_text(
        "FoamFile { format ascii; class labelList; object neighbour; }\n1\n(\n1\n);\n",
        encoding="ascii",
    )
    (mesh / "boundary").write_text(
        "FoamFile { format ascii; class polyBoundaryMesh; object boundary; }\n"
        f"1\n(\nwalls {{ type wall; nFaces {len(boundary_faces)}; startFace 1; }}\n);\n",
        encoding="ascii",
    )
    log = case_dir / "checkMesh.log"
    log.write_text(
        "    cells: 2\n"
        "    Min volume = 1.000000000. Max volume = 1.000000000. "
        "Total volume = 2.000000000. Cell volumes OK.\n"
        "Mesh OK.\n",
        encoding="ascii",
    )
    return case_dir, mesh, log


def test_parses_foundation_v10_checkmesh_summary_layout():
    result = _parse_checkmesh_volume_summary(FOUNDATION_CHECKMESH_SAMPLE)
    assert result["cell_count"] == 216
    assert result["volumes_m3"] == {
        "minimum": pytest.approx(0.05555555544),
        "maximum": pytest.approx(0.05555555578),
        "total": 12.0,
    }
    assert result["tokens"]["total"] == "12"


def test_reconstructs_two_cell_poly_mesh_and_checks_receipt_bound_log(tmp_path):
    case, _, log = two_cell_case(tmp_path / "case")
    digest = hashlib.sha256(log.read_bytes()).hexdigest()

    result = audit_openfoam_checkmesh_poly_mesh_volume(
        case,
        expected_cell_count=2,
        expected_nominal_cell_volume_m3=1.0,
        checkmesh_log_sha256=digest,
    )

    assert result["status"] == "PASS"
    assert result["qualification_status"] == "DIAGNOSTIC_ONLY"
    assert result["scientific_validation"] == "BLOCKED"
    assert result["poly_mesh"]["internal_face_count"] == 1
    assert result["poly_mesh"]["minimum_cell_volume_m3"] == pytest.approx(1.0)
    assert result["poly_mesh"]["maximum_cell_volume_m3"] == pytest.approx(1.0)
    assert result["poly_mesh"]["total_cell_volume_m3"] == pytest.approx(2.0)
    assert result["poly_mesh"]["bounding_box_volume_m3"] == pytest.approx(2.0)
    assert result["checkmesh_log_sha256"] == digest
    assert result["checkmesh_inferred_significant_digits"] == 10
    assert set(result["poly_mesh"]["files_sha256"]) == {
        "points", "faces", "owner", "neighbour", "boundary",
    }


def test_checkmesh_volume_audit_rejects_tampered_summary_and_receipt_digest(tmp_path):
    case, _, log = two_cell_case(tmp_path / "case")
    valid_digest = hashlib.sha256(log.read_bytes()).hexdigest()
    log.write_text(
        log.read_text(encoding="ascii").replace(
            "Min volume = 1.000000000. Max volume = 1.000000000.",
            "Min volume = 0.990000000. Max volume = 1.010000000.",
        ),
        encoding="ascii",
    )
    changed_digest = hashlib.sha256(log.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="differs from its execution receipt"):
        audit_openfoam_checkmesh_poly_mesh_volume(
            case,
            expected_cell_count=2,
            expected_nominal_cell_volume_m3=1.0,
            checkmesh_log_sha256=valid_digest,
        )
    with pytest.raises(ValueError, match="do not agree"):
        audit_openfoam_checkmesh_poly_mesh_volume(
            case,
            expected_cell_count=2,
            expected_nominal_cell_volume_m3=1.0,
            checkmesh_log_sha256=changed_digest,
        )


def test_checkmesh_parser_rejects_ambiguous_or_failed_logs():
    text = FOUNDATION_CHECKMESH_SAMPLE
    with pytest.raises(ValueError, match="one complete volume summary"):
        _parse_checkmesh_volume_summary(text + "\n" + text)
    with pytest.raises(ValueError, match="one complete volume summary"):
        _parse_checkmesh_volume_summary(text.replace("Mesh OK.", "Mesh FAILED."))


def test_poly_mesh_volume_audit_rejects_negative_owner_id(tmp_path):
    case, mesh, log = two_cell_case(tmp_path / "case")
    (mesh / "owner").write_text(
        (mesh / "owner").read_text(encoding="ascii").replace("\n0\n", "\n-1\n", 1),
        encoding="ascii",
    )
    digest = hashlib.sha256(log.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="owner list"):
        audit_openfoam_checkmesh_poly_mesh_volume(
            case,
            expected_cell_count=2,
            expected_nominal_cell_volume_m3=1.0,
            checkmesh_log_sha256=digest,
        )
