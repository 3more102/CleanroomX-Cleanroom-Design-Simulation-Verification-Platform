"""Conformal voxel open-door CFD input cases; synthetic geometry, no solver run."""
from __future__ import annotations

import hashlib
import json

import pytest

from cleanroomx.cfd_pipeline_cli import build_parser
from cleanroomx.cfd_multizone import (
    SCHEMA, _build_case, _geometry,
    generate_multizone_open_door_case, run_multizone_open_door_case,
)
from cleanroomx.gui import bundled_demo_project_path
from cleanroomx.project import load_project_document


def _generate(tmp_path, **opts):
    return generate_multizone_open_door_case(
        bundled_demo_project_path(), tmp_path / "multi",
        door_mode="open", kinematic_viscosity_m2_s=1.5e-5,
        **opts
    )


def test_multizone_geometry_has_real_cross_room_internal_faces_and_single_component():
    project=load_project_document(bundled_demo_project_path())
    geometry,_=_geometry(project,(0.5,0.1,0.3))
    assert len(geometry["occupancy"]) > 1000
    assert geometry["dimensions"] == (36,50,10)
    assert set(geometry["doors"]) == {
        "door-process-preparation","door-preparation-ante","door-ante-corridor"
    }
    for door in geometry["doors"].values():
        assert door["open_face_count"] > 0
        assert door["clear_width_m"] == pytest.approx(1.0)
        assert door["clear_height_m"] == pytest.approx(2.1)
        assert door["wall_thickness_m"] == pytest.approx(0.5)
    # The same face is occupied on both sides; this is actual fluid connectivity.
    assert any(
        geometry["occupancy"].get((i+1,j,k)) not in (None,rid)
        for (i,j,k),rid in geometry["occupancy"].items()
    )


def test_generated_case_has_real_conformal_multiblock_and_every_device_boundary(tmp_path):
    manifest=_generate(tmp_path)
    assert manifest["schema_version"]==SCHEMA
    assert manifest["input_mode"]=="hypothetical_all_doors_open"
    assert set(manifest["files"]) == {
        "system/blockMeshDict","system/controlDict","system/fvSchemes","system/fvSolution",
        "constant/transportProperties","constant/momentumTransport","0/U","0/p"
    }
    evidence=manifest["case"]
    assert evidence["door_mode"]=="open"
    assert evidence["connected_component_count"]==1
    assert evidence["fluid_block_count"]>1000
    assert len(evidence["open_doors"])==3
    assert len(evidence["ffu_mesh_faces"])==12
    assert len(evidence["return_mesh_faces"])==3
    assert all(x>0 for x in evidence["ffu_mesh_faces"].values())
    assert all(x>0 for x in evidence["return_mesh_faces"].values())
    assert set(evidence["room_boundary_flows"])=={"process","preparation","ante"}
    assert evidence["room_boundary_flows"]["process"]["supply_m3_s"]==pytest.approx(.75)
    assert "no 5 Pa" in evidence["pressure_boundary"]
    root=tmp_path/"multi"
    mesh=(root/"system/blockMeshDict").read_text()
    u=(root/"0/U").read_text()
    p=(root/"0/p").read_text()
    assert mesh.count("    hex (")==evidence["fluid_block_count"]
    for rid in ("process","preparation","ante"):
        assert f"supply_{rid}" in mesh
        assert f"return_{rid}" in mesh
        assert f"supply_{rid}\n    {{\n        type fixedValue;" in u
        assert f"return_{rid}\n    {{\n        type pressureInletOutletVelocity;" in u
        assert f"return_{rid}\n    {{\n        type fixedValue; value uniform 0;" in p
    assert "walls\n    {\n        type noSlip;" in u
    assert "application simpleFoam;" in (root/"system/controlDict").read_text()
    assert "simulationType laminar;" in (root/"constant/momentumTransport").read_text()
    assert "div((nuEff*dev2(T(grad(U))))) Gauss linear;" in (root/"system/fvSchemes").read_text()
    assert all(hashlib.sha256((root/name).read_bytes()).hexdigest()==sha
               for name,sha in manifest["files"].items())
    assert json.loads((root/"manifest.json").read_text())==manifest
    with pytest.raises(FileExistsError,match="overwrite"):
        _generate(tmp_path)


def test_doors_must_explicitly_be_open_and_inputs_fail_closed(tmp_path):
    with pytest.raises(ValueError,match="explicitly select"):
        generate_multizone_open_door_case(
            bundled_demo_project_path(), tmp_path/"closed",
            door_mode="closed", kinematic_viscosity_m2_s=1.5e-5
        )
    with pytest.raises(ValueError,match="align"):
        generate_multizone_open_door_case(
            bundled_demo_project_path(), tmp_path/"nonconformal",
            door_mode="open", kinematic_viscosity_m2_s=1.5e-5,
            cell_size_y_m=0.3
        )
    with pytest.raises(ValueError,match="voxel grid"):
        generate_multizone_open_door_case(
            bundled_demo_project_path(), tmp_path/"huge",
            door_mode="open", kinematic_viscosity_m2_s=1.5e-5,
            cell_size_x_m=.1,cell_size_y_m=.1,cell_size_z_m=.1
        )
    with pytest.raises(ValueError,match="strictly positive"):
        generate_multizone_open_door_case(
            bundled_demo_project_path(), tmp_path/"badphysics",
            door_mode="open", kinematic_viscosity_m2_s=float("nan")
        )
    assert list(tmp_path.iterdir())==[]


def test_open_door_geometry_avoids_inventing_nearby_door_locations():
    project=load_project_document(bundled_demo_project_path())
    layout=project.metadata["spatial_layout"]
    door=next(d for d in layout["devices"] if d["id"]=="door-process-preparation")
    door["y_m"]=2.01
    with pytest.raises(ValueError,match="door clear width edge"):
        _geometry(project,(.5,.1,.3))


def test_multizone_runner_rejects_changed_inputs_before_external_solver(tmp_path,monkeypatch):
    _generate(tmp_path)
    root=tmp_path/"multi"
    monkeypatch.setattr("cleanroomx.cfd_multizone.shutil.which",lambda name: None)
    with pytest.raises(RuntimeError,match="blockMesh not found"):
        run_multizone_open_door_case(root)
    modified=root/"0/U"
    modified.write_text(modified.read_text()+"\n// tampered")
    with pytest.raises(ValueError,match="Solver input changed"):
        run_multizone_open_door_case(root)


def test_cli_explicit_open_door_mode_required():
    parser=build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["multizone-generate","demo.json","output",
                           "--kinematic-viscosity-m2-s","1.5e-5"])
    args=parser.parse_args([
        "multizone-generate","demo.json","output","--door-mode","open",
        "--kinematic-viscosity-m2-s","1.5e-5",
    ])
    assert args.command=="multizone-generate"
    assert args.cell_size_y_m==.1
    assert parser.parse_args(["multizone-run","output"]).command=="multizone-run"


def test_independent_closed_room_export_rejects_open_design_door(tmp_path):
    from cleanroomx.cfd_project_rooms import generate_project_room_cases
    raw=json.loads(bundled_demo_project_path().read_text())
    door=next(d for d in raw["project"]["metadata"]["spatial_layout"]["devices"] if d["type"]=="door")
    door["door_state"]="open"
    source=tmp_path/"open-design.json"
    source.write_text(json.dumps(raw))
    with pytest.raises(ValueError,match="requires closed"):
        generate_project_room_cases(source,tmp_path/"closed",kinematic_viscosity_m2_s=1.5e-5)


def test_multizone_equipment_respects_room_floor_elevation():
    project=load_project_document(bundled_demo_project_path())
    for room in project.metadata["spatial_layout"]["rooms"]:
        room["floor_elevation_m"]=1.2
    _,metadata=_build_case(project,pitch=(.5,.1,.3),viscosity_m2_s=1.5e-5,iterations=10,interval=5)
    assert metadata["origin_m"][2]==1.2
    assert len(metadata["ffu_mesh_faces"])==12
    assert all(x>0 for x in metadata["ffu_mesh_faces"].values())
    assert all(x>0 for x in metadata["return_mesh_faces"].values())


def test_unconfigured_shared_wall_never_becomes_an_unintended_passage():
    project=load_project_document(bundled_demo_project_path())
    devices=project.metadata["spatial_layout"]["devices"]
    devices[:]=[d for d in devices if d["id"]!="door-preparation-ante"]
    with pytest.raises(ValueError,match="Unconfigured shared"):
        _geometry(project,(.5,.1,.3))
