"""Independent synthetic native mesh; values are parser fixtures, not CFD."""
import json
from pathlib import Path
import shutil

import pytest

from cleanroomx.cfd_room_flux import MESH_PATHS, diagnose_two_room_face_flux
from cleanroomx.cfd_two_room import _write_json, export_two_room_case


def write_native_two_room_fixture(root: Path, *, reverse_ids=False):
    from test_cfd_two_room import _spec
    spec = _spec()
    spec.update(room_m=[3., 3., 3.], mesh_cells_per_room=[6, 6, 6], door_opening_m=[1., 1.])
    case = root / "case"
    export_two_room_case(spec, case)
    points, point_ids = [], {}
    def vertex(x, y, z):
        xyz = (x / 2, y / 2, z / 2)
        if xyz not in point_ids:
            point_ids[xyz] = len(points)
            points.append(xyz)
        return point_ids[xyz]
    # Uniform independent grid. The partition has a centered 1m by 1m
    # floor-level opening at x=3; other x=3 faces are paired baffle walls.
    candidates = {}
    for ix in range(12):
        for iy in range(6):
            for iz in range(6):
                original = (ix * 6 + iy) * 6 + iz
                cell = 431 - original if reverse_ids else original
                a,b,c,d,e,f,g,h = [vertex(ix+x, iy+y, iz+z) for x,y,z in (
                    (0,0,0),(1,0,0),(1,1,0),(0,1,0),
                    (0,0,1),(1,0,1),(1,1,1),(0,1,1))]
                for face in ((a,d,c,b),(e,f,g,h),(a,b,f,e),(d,h,g,c),(a,e,h,d),(b,c,g,f)):
                    coords = [points[p] for p in face]
                    xs = [p[0] for p in coords]
                    partition = all(x == 3 for x in xs)
                    opening = partition and 1 <= iy/2 and (iy+1)/2 <= 2 and (iz+1)/2 <= 1
                    key = (tuple(sorted(face)), cell if partition and not opening else None)
                    candidates.setdefault(key, []).append((cell, face))
    internal, boundary = [], {name: [] for name in ("inlet","outlet","walls","partition")}
    for entries in candidates.values():
        entries.sort()
        own, face = entries[0]
        if len(entries) == 2:
            internal.append((face, own, entries[1][0]))
        else:
            xs = [points[p][0] for p in face]
            patch = "inlet" if all(x == 0 for x in xs) else "outlet" if all(x == 6 for x in xs) else "partition" if all(x == 3 for x in xs) else "walls"
            boundary[patch].append((face, own, None))
    rows = internal + [row for group in boundary.values() for row in group]
    mesh = case / "constant/polyMesh"
    mesh.mkdir()
    def listing(name, cls, lines):
        (mesh/name).write_text(f"FoamFile\n{{format ascii; class {cls}; object {name};}}\n{len(lines)}\n(\n" + "\n".join(lines) + "\n)\n")
    listing("points", "vectorField", ["("+" ".join(map(str,p))+")" for p in points])
    listing("faces", "faceList", ["4("+" ".join(map(str,row[0]))+")" for row in rows])
    listing("owner", "labelList", [str(row[1]) for row in rows])
    listing("neighbour", "labelList", [str(row[2]) for row in internal])
    patches, cursor = [], len(internal)
    for name, group in boundary.items():
        patches.append(f"{name}\n{{type {'wall' if name in ('walls','partition') else 'patch'}; nFaces {len(group)}; startFace {cursor};\n}}")
        cursor += len(group)
    listing("boundary", "polyBoundaryMesh", patches)
    values, doorway_indices = [], []
    for i, (face, own, neigh) in enumerate(internal):
        coords = [points[p] for p in face]
        if all(p[0] == 3 for p in coords):
            doorway_indices.append(i)
            # Four doorway faces: one reverses, three flow forward.
            flow = -.02 if len(doorway_indices) == 1 else .04
            values.append(-flow if reverse_ids else flow)
        else:
            values.append(0.)
    phi = case / "2/phi"
    phi.parent.mkdir()
    phi.write_text("FoamFile {format ascii; class surfaceScalarField; object phi;}\n"
                   "dimensions [0 3 -1 0 0 0 0];\ninternalField nonuniform List<scalar>\n" + str(len(values)) + "\n(\n" +
                   "\n".join(map(str, values)) + "\n);\nboundaryField\n{\n" +
                   "\n".join(f"{name}\n{{type calculated; value uniform {(-.1 if name=='inlet' else .1 if name=='outlet' else 0)/len(group)};\n}}"
                             for name, group in boundary.items()) + "\n}\n")
    return case, doorway_indices


@pytest.mark.parametrize("reverse_ids", [False, True])
def test_native_doorway_bidirectional_flux_uses_owner_neighbour_and_not_cell_velocity(tmp_path, reverse_ids):
    case, indices = write_native_two_room_fixture(tmp_path, reverse_ids=reverse_ids)
    result = diagnose_two_room_face_flux(case, "2/phi")
    door = result["doorway"]
    assert door["face_count"] == len(indices) == 4
    assert door["area_m2"] == pytest.approx(1)
    assert door["gross_room_1_to_room_2_m3_s"] == pytest.approx(.12)
    assert door["gross_room_2_to_room_1_m3_s"] == pytest.approx(.02)
    assert door["net_room_1_to_room_2_m3_s"] == pytest.approx(.1)
    assert [r["volume_m3"] for r in result["rooms"]] == pytest.approx([27,27])
    assert [r["net_outward_m3_s"] for r in result["rooms"]] == pytest.approx([0,0], abs=1e-12)
    assert [r["doorway_net_outward_m3_s"] for r in result["rooms"]] == pytest.approx([.1,-.1])
    assert result["per_room_ach"] == "NOT_ASSESSED"
    assert result["scientific_validation"] == "BLOCKED"
    assert set(result["source_sha256"]) == {"manifest.json", "2/phi", *MESH_PATHS}
    assert diagnose_two_room_face_flux(case, "2/phi", expected_sources=result["source_sha256"]) == result


@pytest.mark.parametrize("name", ["points", "faces", "owner", "neighbour", "boundary", "phi"])
def test_native_room_flux_rejects_any_receipt_bound_source_change(tmp_path, name):
    case, _ = write_native_two_room_fixture(tmp_path)
    recorded = diagnose_two_room_face_flux(case, "2/phi")["source_sha256"]
    path = case / ("2/phi" if name == "phi" else "constant/polyMesh/" + name)
    path.write_bytes(path.read_bytes() + b"// changed\n")
    with pytest.raises(ValueError, match="hashes differ"):
        diagnose_two_room_face_flux(case, "2/phi", expected_sources=recorded)


@pytest.mark.parametrize("path", ["../2/phi", "/2/phi", "2/../2/phi", "NaN/phi", "Infinity/phi", "-1/phi", "2/U"])
def test_native_room_flux_rejects_ambiguous_time_paths(tmp_path, path):
    case, _ = write_native_two_room_fixture(tmp_path)
    with pytest.raises((ValueError, FileNotFoundError)):
        diagnose_two_room_face_flux(case, path)


@pytest.mark.parametrize("mutation", ["wrong_dimensions", "wrong_count", "nonfinite", "missing_door", "wrong_patch", "wrong_cell", "same_cell", "wrong_geometry", "symlink"])
def test_native_room_flux_fails_closed_for_inconsistent_native_inputs(tmp_path, mutation):
    case, _ = write_native_two_room_fixture(tmp_path)
    mesh = case / "constant/polyMesh"
    if mutation in ("wrong_dimensions", "wrong_count", "nonfinite"):
        path = case / "2/phi"
        content = path.read_text()
        if mutation == "wrong_dimensions":
            content = content.replace("[0 3 -1", "[1 3 -1")
        elif mutation == "wrong_count":
            content = content.replace("nonuniform List<scalar>\n", "nonuniform List<scalar>\n99999 // ")
        else:
            content = content.replace("-0.02", "1e999")
        path.write_text(content)
    elif mutation == "missing_door":
        # Corrupt a neighbour link so the native cell shell cannot close.
        path = mesh / "neighbour"
        path.write_text(path.read_text().replace("\n144\n", "\n0\n", 1))
    elif mutation == "wrong_patch":
        path = mesh / "boundary"
        path.write_text(path.read_text().replace("inlet\n", "unknown\n"))
    elif mutation == "wrong_cell":
        path = mesh / "owner"
        path.write_text(path.read_text().replace("\n0\n", "\n99999\n", 1))
    elif mutation == "same_cell":
        path = mesh / "neighbour"
        content = path.read_text().split("(\n")
        owner = (mesh/"owner").read_text().split("(\n")[1].splitlines()[0]
        lines = content[1].splitlines()
        lines[0] = owner
        path.write_text(content[0]+"(\n"+"\n".join(lines)+"\n")
    elif mutation == "wrong_geometry":
        path = mesh / "points"
        path.write_text(path.read_text().replace("(0.0 0.0 0.0)", "(-1.0 0.0 0.0)"))
    else:
        path = mesh / "points"
        saved = tmp_path / "points"
        path.rename(saved)
        path.symlink_to(saved)
    with pytest.raises(ValueError):
        diagnose_two_room_face_flux(case, "2/phi")


def bind_fixture_receipt(case, path):
    from test_cfd_proofgraph import _write_two_room_receipt
    # Preserve the independent native mesh while the legacy receipt helper
    # creates its deliberately non-numeric boundary parser fixture.
    mesh = case / "constant/polyMesh"
    saved = case / "constant/saved-native-mesh"
    mesh.rename(saved)
    receipt = _write_two_room_receipt(case, path)
    shutil.rmtree(mesh)
    saved.rename(mesh)
    receipt["room_flux"] = diagnose_two_room_face_flux(case, "2/phi")
    receipt["pressure_probe"]["last_solver_time"] = 2
    probe = case / receipt["pressure_probe"]["path"]
    probe.write_text("# SYNTHETIC pressure parser fixture\n1 2 1\n2 4.2 0.1\n")
    import hashlib
    receipt["pressure_probe"].update(sha256=hashlib.sha256(probe.read_bytes()).hexdigest(), sample_count=2)
    receipt["result_sha256"][receipt["pressure_probe"]["path"]] = receipt["pressure_probe"]["sha256"]
    receipt["solver_flux"].update(phi_path="2/phi", last_solver_time="2", phi_sha256=receipt["room_flux"]["source_sha256"]["2/phi"])
    receipt["solver_flux"]["poly_mesh_boundary_sha256"] = receipt["room_flux"]["source_sha256"]["constant/polyMesh/boundary"]
    receipt["result_sha256"].pop("150/phi")
    receipt["result_sha256"].update({p:sha for p,sha in receipt["room_flux"]["source_sha256"].items() if p!="manifest.json"})
    _write_json(path, receipt)
    return receipt


def test_receipt_proofgraph_replays_native_room_flux_and_rejects_changed_topology(tmp_path):
    from cleanroomx.cfd_proofgraph import proofgraph_from_two_room_receipt
    case, _ = write_native_two_room_fixture(tmp_path)
    path = tmp_path / "receipts/two_room_run_receipt.json"
    receipt = bind_fixture_receipt(case, path)
    graph = proofgraph_from_two_room_receipt(case, path)
    assert graph.evidence[0].value["room_flux"] == receipt["room_flux"]
    source = case / "constant/polyMesh/neighbour"
    source.write_bytes(source.read_bytes() + b"// changed\n")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        proofgraph_from_two_room_receipt(case, path)


@pytest.mark.parametrize("mutation", ["value", "source", "missing_source", "time", "null"])
def test_self_rehashed_receipt_cannot_forge_room_flux(tmp_path, mutation):
    from cleanroomx.cfd_proofgraph import proofgraph_from_two_room_receipt
    case, _ = write_native_two_room_fixture(tmp_path)
    path = tmp_path / "receipts/two_room_run_receipt.json"
    receipt = bind_fixture_receipt(case, path)
    if mutation == "value":
        receipt["room_flux"]["doorway"]["net_room_1_to_room_2_m3_s"] = 123
    elif mutation == "source":
        receipt["room_flux"]["source_sha256"]["constant/polyMesh/faces"] = "a"*64
    elif mutation == "missing_source":
        receipt["result_sha256"].pop("constant/polyMesh/points")
    elif mutation == "time":
        receipt["pressure_probe"]["last_solver_time"] = 3
    else:
        receipt["room_flux"] = None
    _write_json(path, receipt)
    with pytest.raises(ValueError, match="room-flux|bind every"):
        proofgraph_from_two_room_receipt(case, path)


def test_room_flux_analysis_graph_and_export_keep_exact_native_sources(tmp_path):
    pytest.importorskip("matplotlib")
    from cleanroomx.cfd_analysis_export import export_analysis_bundle
    from cleanroomx.cfd_result_analysis import analyze_two_room_results, build_analysis_graph
    case, _ = write_native_two_room_fixture(tmp_path)
    path = tmp_path / "receipts/two_room_run_receipt.json"
    bind_fixture_receipt(case, path)
    session = analyze_two_room_results(case, path)
    assert session.report["room_flux"]["doorway"]["net_room_1_to_room_2_m3_s"] == pytest.approx(.1)
    graph = build_analysis_graph([session], kind="doorway_flow", time_name="2.0")
    assert graph["status"] == "computed_diagnostic"
    assert [p["y"] for p in graph["series"][0]["points"]] == pytest.approx([.12,.02,.1,0,0], abs=1e-12)
    assert all(any(source["path"] == str(case/p) for source in graph["sources"]) for p in MESH_PATHS)
    assert build_analysis_graph([session], kind="doorway_flow", time_name="3")["status"] == "not_available"
    assert build_analysis_graph([session], kind="doorway_flow", case_id="unknown")["status"] == "not_available"
    output = export_analysis_bundle([session], [graph], tmp_path / "export")
    assert (output/"figure-01.png").read_bytes().startswith(b"\x89PNG")
    assert "Gross 1" in (output/"graphs.csv").read_text(encoding="utf-8")
    source = case / "constant/polyMesh/owner"
    source.write_bytes(source.read_bytes() + b"// mutated before export\n")
    with pytest.raises(ValueError, match="changed|hash mismatch"):
        export_analysis_bundle([session], [graph], tmp_path / "stale-export")


def test_legacy_receipt_keeps_doorway_flow_unavailable(tmp_path):
    from cfd_analysis_fixtures import write_two_room_analysis_fixture
    from cleanroomx.cfd_result_analysis import analyze_two_room_results, build_analysis_graph
    case, path = write_two_room_analysis_fixture(tmp_path)
    result = analyze_two_room_results(case, path)
    assert "room_flux" not in result.report
    assert build_analysis_graph([result], kind="doorway_flow")["status"] == "not_available"
