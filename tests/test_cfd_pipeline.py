"""SYNTHETIC regression fixtures; not proof of real CFD physics validation."""
import json
import math
from types import SimpleNamespace
import pytest

from cleanroomx.cfd_openfoam import (
    SCHEMA, _layout, audit_openfoam_boundary_inputs, build_openfoam_files, export_openfoam_cases,
    run_openfoam_cases, validate_openfoam_spec,
)
from cleanroomx.cfd_vtk import import_vtk_case, populate_study_from_vtk

def spec():
    return {"schema_version":SCHEMA,"name":"synthetic test input",
            "room_m":[3.0,2.0,2.0],"mesh_cells":[6,6,6],
            "supply_flow_m3_s":0.15,"kinematic_viscosity_m2_s":1.5e-5,
            "max_iterations":100,"output_interval":25}

def test_mesh_and_flow_generation(tmp_path):
    s=spec()
    manifest=export_openfoam_cases(s,tmp_path/"cases")
    assert set(manifest["evidence"])=={"1","2","3"}
    assert len(manifest["files"])==24
    for cfg in (1,2,3):
        meta=manifest["evidence"][str(cfg)]
        assert meta["mesh_cells"]==216
        assert meta["mesh"]["outlet_face_count"]>0
        assert meta["inlet_normal_speed_m_s"]*meta["mesh"]["inlet_area_m2"]==pytest.approx(0.15)
        audit=meta["boundary_audit"]
        assert audit["status"]=="input_geometry_and_inlet_flow_consistent"
        assert audit["inlet"]["outward_normal_area_m2"]=={"+z":audit["inlet"]["area_m2"]}
        assert audit["inlet"]["prescribed_inward_volume_flow_m3_s"]==pytest.approx(0.15)
        assert set(audit["outlet"]["outward_normal_area_m2"])==({"-z"} if cfg==3 else {"+x","-x"})
        assert audit["outlet"]["actual_solver_volume_flow_m3_s"] is None
        assert audit["flow_balance_status"]=="not_measured"
        assert audit["scientific_validation"]=="BLOCKED"
        f=tmp_path/"cases"/f"configuration_{cfg}"
        assert "hex (" in (f/"system/blockMeshDict").read_text()
        assert "pressureInletOutletVelocity" in (f/"0/U").read_text()
        properties=(f/"constant/physicalProperties").read_text()
        assert "object physicalProperties;" in properties
        assert "viscosityModel constant;" in properties
        assert "nu 1.5e-05;" in properties
        momentum=(f/"constant/momentumTransport").read_text()
        assert "object momentumTransport;" in momentum
        assert "simulationType laminar;" in momentum
        assert not (f/"constant/transportProperties").exists()
        assert not (f/"constant/turbulenceProperties").exists()
        schemes=(f/"system/fvSchemes").read_text()
        assert "div((nuEff*dev2(T(grad(U))))) Gauss linear;" in schemes
    with pytest.raises(FileExistsError):
        export_openfoam_cases(s,tmp_path/"cases")
    copy=export_openfoam_cases(s,tmp_path/"other")
    assert copy==manifest

@pytest.mark.parametrize("configuration",[1,2,3])
def test_boundary_audit_rejects_outward_inlet_velocity(configuration):
    files,metadata=build_openfoam_files(spec(),configuration)
    tampered=dict(files)
    tampered["0/U"]=tampered["0/U"].replace("(0 0 -","(0 0 +",1)
    with pytest.raises(ValueError,match="does not point into"):
        audit_openfoam_boundary_inputs(tampered,metadata)

def test_boundary_audit_rejects_blockmesh_geometry_changed_after_metadata():
    files,metadata=build_openfoam_files(spec(),3)
    tampered=dict(files)
    tampered["system/blockMeshDict"]=tampered["system/blockMeshDict"].replace(
        "(0 0 0)","(0.1 0 0)",1
    )
    with pytest.raises(ValueError,match="geometry disagrees"):
        audit_openfoam_boundary_inputs(tampered,metadata)

def test_patch_topology_is_closed():
    nx=ny=nz=6
    for cfg in (1,2,3):
        p=_layout(nx,ny,nz,cfg)
        faces=[frozenset(face) for part in p.values() for face in part]
        assert len(faces)==2*(nx*ny+nx*nz+ny*nz)
        assert len(faces)==len(set(faces))
        assert p["inlet"] and p["outlet"]

@pytest.mark.parametrize("field,value",[
    ("schema_version","bogus"),("mesh_cells",[80,80,80]),
    ("mesh_cells",[6.5,6,6]),("room_m",[2,0,1]),
    ("supply_flow_m3_s",True),("supply_flow_m3_s",float("nan")),
    ("output_interval",101),("max_iterations",0),
])
def test_invalid_spec_rejected(field,value):
    s=spec();s[field]=value
    with pytest.raises(ValueError):validate_openfoam_spec(s)

def test_unsupported_config():
    with pytest.raises(ValueError):build_openfoam_files(spec(),True)
    with pytest.raises(ValueError):build_openfoam_files(spec(),4)

def test_solver_not_installed_fails_closed(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases")
    monkeypatch.setattr("cleanroomx.cfd_openfoam.shutil.which",lambda name:None)
    with pytest.raises(RuntimeError,match="not found"):
        run_openfoam_cases(tmp_path/"cases")

def test_runner_requires_foundation_v10_environment(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases")
    monkeypatch.setattr("cleanroomx.cfd_openfoam.shutil.which",lambda name:f"/fake/{name}")
    monkeypatch.setenv("WM_PROJECT","OpenFOAM")
    monkeypatch.setenv("WM_PROJECT_VERSION","2312")
    with pytest.raises(RuntimeError,match="OpenFOAM Foundation v10"):
        run_openfoam_cases(tmp_path/"cases")

def test_runner_records_and_checks_foundation_v10_banners(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases")
    monkeypatch.setattr("cleanroomx.cfd_openfoam.shutil.which",lambda name:f"/fake/{name}")
    monkeypatch.setenv("WM_PROJECT","OpenFOAM")
    monkeypatch.setenv("WM_PROJECT_VERSION","10")
    banner=("  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox\n"
            "  \\\\    /   O peration     | Website:  https://openfoam.org\n"
            "     \\\\/     M anipulation  | Version:  10\n"
            "Build  : 10-c4cf895ad8fa\n")

    def fake_run(command,*,cwd,stdout,stderr,timeout,check):
        stdout.write(banner)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("cleanroomx.cfd_openfoam.subprocess.run",fake_run)
    result=run_openfoam_cases(tmp_path/"cases")
    assert result["status"]=="executed_requires_convergence_review"
    assert result["solver_release"]=="OpenFOAM Foundation v10"
    assert result["solver_build"]=="10-c4cf895ad8fa"
    assert set(result["boundary_audits"])=={"1","2","3"}
    assert all(
        stage["openfoam"]["is_foundation_v10"]
        for case in result["cases"].values()
        for stage in case["stages"]
    )

def test_tampered_case_fails_closed(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases")
    p=tmp_path/"cases/configuration_1/0/U"
    p.write_text(p.read_text()+"\n// tamper")
    monkeypatch.setattr("cleanroomx.cfd_openfoam.shutil.which",lambda name:"/usr/bin/mock")
    with pytest.raises(ValueError,match="Tampered"):
        run_openfoam_cases(tmp_path/"cases")

def test_tampered_boundary_audit_manifest_fails_before_solver_launch(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases")
    manifest_path=tmp_path/"cases/manifest.json"
    manifest=json.loads(manifest_path.read_text())
    manifest["evidence"]["1"]["boundary_audit"]["inlet"]["area_m2"]+=1
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr("cleanroomx.cfd_openfoam.shutil.which",lambda name:f"/fake/{name}")
    with pytest.raises(ValueError,match="Boundary audit metadata mismatch"):
        run_openfoam_cases(tmp_path/"cases")

def vtk_fixture(path, concentration=1., recirc=0., speed=.2):
    vtk=pytest.importorskip("vtk")
    points=vtk.vtkPoints()
    for p in ((0,0,0),(1,0,0),(1,1,0),(0,1,0),
              (0,0,1),(1,0,1),(1,1,1),(0,1,1)):
        points.InsertNextPoint(*p)
    grid=vtk.vtkUnstructuredGrid()
    grid.SetPoints(points)
    cell=vtk.vtkHexahedron()
    for i in range(8):cell.GetPointIds().SetId(i,i)
    grid.InsertNextCell(cell.GetCellType(),cell.GetPointIds())
    u=vtk.vtkDoubleArray();u.SetName("U");u.SetNumberOfComponents(3)
    u.InsertNextTuple3(0,0,-speed)
    t=vtk.vtkDoubleArray();t.SetName("T");t.InsertNextValue(concentration)
    r=vtk.vtkDoubleArray();r.SetName("recirculating");r.InsertNextValue(recirc)
    for arr in (u,t,r):grid.GetCellData().AddArray(arr)
    writer=vtk.vtkXMLUnstructuredGridWriter()
    writer.SetFileName(str(path));writer.SetInputData(grid)
    assert writer.Write()==1

def test_actual_vtk_field_import_and_pareto(tmp_path):
    sources={}
    for cfg in (1,2,3):
        path=tmp_path/f"case{cfg}.vtu"
        vtk_fixture(path,concentration=0 if cfg==3 else 10,
                    recirc=0 if cfg==3 else 1)
        sources[cfg]=path
    study={"schema_version":"cleanroomx.cfd-study.v1","name":"synthetic VTK smoke",
           "room":{"length_m":1,"width_m":1,"height_m":1},
           "analysis":{"contaminant_limit":5,"contaminant_unit":"particles/m3",
                       "max_unrepresented_volume_fraction":0,
                       "max_flow_imbalance_fraction":0},
           "cases":[{"configuration":i,"source_location_m":[.5,.5,.5],
                     "inlet_flow_m3_s":1,"outlet_flow_m3_s":1,"cells":[]}
                     for i in (1,2,3)]}
    result=populate_study_from_vtk(study,sources,solver_name="synthetic VTK")
    assert result["analysis"]["comparison_status"]=="comparable"
    assert result["analysis"]["unique_pareto_dominant_configuration"]==3
    assert result["analysis"]["cases"][2]["metrics"]["sampled_volume_m3"]==pytest.approx(1)
    assert all(not case["cells"] for case in study["cases"])
    assert result["import_manifest"]["1"]["source_sha256"]
    with pytest.raises(ValueError,match="overwrite"):
        populate_study_from_vtk(result["study"],sources,solver_name="synthetic VTK")

def test_vtk_png_sampled_cross_section(tmp_path):
    from cleanroomx.cfd_visualization import render_cfd_cross_section
    pytest.importorskip("matplotlib")
    sources={}
    for cfg in (1,2,3):
        f=tmp_path/f"plot{cfg}.vtu"
        vtk_fixture(f,speed=cfg*.2)
        sources[cfg]=f
    target=tmp_path/"actual-vtk-data.png"
    info=render_cfd_cross_section(sources,target,axis="y",position_m=.5,slab_thickness_m=.2)
    assert target.stat().st_size>5000
    assert info["sample_count"]=={"1":1,"2":1,"3":1}
    with pytest.raises(FileExistsError):
        render_cfd_cross_section(sources,target,axis="y",position_m=.5,slab_thickness_m=.2)
