"""SYNTHETIC regression fixtures; not proof of real CFD physics validation."""
import json
import math
from types import SimpleNamespace
import pytest

from cleanroomx.cfd_openfoam import (
    SCHEMA, _layout, build_openfoam_files, export_openfoam_cases,
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
    with pytest.raises(ValueError,match="openfoam_version"):
        build_openfoam_files(spec(),1,openfoam_version="v13")

def test_v14_case_uses_modular_solver_and_v14_properties():
    files,meta=build_openfoam_files(spec(),1,openfoam_version="v14")
    assert meta["openfoam_release"]=="OpenFOAM Foundation 14"
    assert meta["solver_command"]=="foamRun"
    assert meta["target"]=="OpenFOAM Foundation v14 / foamRun -solver incompressibleFluid"
    control=files["system/controlDict"]
    assert "solver incompressibleFluid;" in control
    assert "application simpleFoam;" not in control
    assert "constant/physicalProperties" in files
    assert "viscosityModel constant;" in files["constant/physicalProperties"]
    assert "nu 1.5e-05;" in files["constant/physicalProperties"]
    assert "simulationType laminar;" in files["constant/momentumTransport"]
    assert "constant/transportProperties" not in files
    assert "constant/turbulenceProperties" not in files
    assert "dimensions [velocity];" in files["0/U"]
    assert "dimensions [kinematicPressure];" in files["0/p"]

def test_v14_runner_checks_foamrun_and_records_mocked_commands(tmp_path,monkeypatch):
    manifest=export_openfoam_cases(spec(),tmp_path/"cases",openfoam_version="v14")
    assert manifest["openfoam_release"]=="OpenFOAM Foundation 14"
    monkeypatch.setenv("WM_PROJECT", "OpenFOAM")
    monkeypatch.setenv("WM_PROJECT_VERSION", "14")
    looked_up=[]
    monkeypatch.setattr("cleanroomx.cfd_openfoam.shutil.which",lambda name:looked_up.append(name) or "/usr/bin/mock")
    commands=[]
    def mocked_run(command,**kwargs):
        if command[-1] == "-help":
            return SimpleNamespace(returncode=0,stdout="OpenFOAM-14\n",stderr="")
        commands.append(command)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr("cleanroomx.cfd_openfoam.subprocess.run",mocked_run)
    result=run_openfoam_cases(tmp_path/"cases",openfoam_version="v14")
    assert looked_up==["blockMesh","checkMesh","foamRun"]
    assert commands==[["/usr/bin/mock"],["/usr/bin/mock"],["/usr/bin/mock"]]*3
    assert result["status"]=="executed_requires_convergence_review"
    assert result["run_manifest"]=="run_manifest.json"
    assert all(case["status"]=="executed_requires_convergence_review" for case in result["cases"].values())
    run_manifest=json.loads((tmp_path/"cases"/"run_manifest.json").read_text())
    assert run_manifest["openfoam_release"]=="OpenFOAM Foundation 14"
    assert run_manifest["timeout_seconds"]==3600
    assert run_manifest["active_environment"]["WM_PROJECT_VERSION"]=="14"
    assert run_manifest["version_probe"]["observed_banner_lines"]==["OpenFOAM-14"]
    assert run_manifest["input_manifest_sha256"]
    assert set(run_manifest["cases"])=={"1","2","3"}
    assert all(stage["command"]==["/usr/bin/mock"] and stage["log_sha256"]
               for case in run_manifest["cases"].values() for stage in case["stages"])
    prior_run_manifest=(tmp_path/"cases"/"run_manifest.json").read_bytes()
    with pytest.raises(FileExistsError,match="Refusing to overwrite existing OpenFOAM run manifest"):
        run_openfoam_cases(tmp_path/"cases",openfoam_version="v14")
    assert (tmp_path/"cases"/"run_manifest.json").read_bytes()==prior_run_manifest
    with pytest.raises(ValueError,match="does not match"):
        run_openfoam_cases(tmp_path/"cases",openfoam_version="v10")

def test_runner_records_failed_external_stage_without_claiming_execution(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases",openfoam_version="v14")
    monkeypatch.setenv("WM_PROJECT", "OpenFOAM")
    monkeypatch.setenv("WM_PROJECT_VERSION", "14")
    monkeypatch.setattr("cleanroomx.cfd_openfoam.shutil.which",lambda name:f"/fake/{name}")
    commands=[]
    def mocked_run(command,**kwargs):
        if command[-1] == "-help":
            return SimpleNamespace(returncode=0,stdout="OpenFOAM-14\n",stderr="")
        commands.append(command)
        return SimpleNamespace(returncode=2)
    monkeypatch.setattr("cleanroomx.cfd_openfoam.subprocess.run",mocked_run)
    result=run_openfoam_cases(tmp_path/"cases")
    assert result["status"]=="incomplete"
    assert commands==[["/fake/blockMesh"]]
    record=json.loads((tmp_path/"cases"/"run_manifest.json").read_text())
    assert record["status"]=="incomplete"
    assert record["failure"]["stage"]["program"]=="blockMesh"
    assert record["failure"]["stage"]["returncode"]==2

def test_v14_runner_fails_closed_without_foamrun(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases",openfoam_version="v14")
    monkeypatch.setenv("WM_PROJECT", "OpenFOAM")
    monkeypatch.setenv("WM_PROJECT_VERSION", "14")
    monkeypatch.setattr(
        "cleanroomx.cfd_openfoam.shutil.which",
        lambda name: f"/fake/{name}" if name in {"blockMesh", "checkMesh"} else None,
    )
    with pytest.raises(RuntimeError,match="foamRun not found"):
        run_openfoam_cases(tmp_path/"cases")

def test_solver_not_installed_fails_closed(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases")
    monkeypatch.setenv("WM_PROJECT", "OpenFOAM")
    monkeypatch.setenv("WM_PROJECT_VERSION", "10")
    monkeypatch.setattr("cleanroomx.cfd_openfoam.shutil.which",lambda name:None)
    with pytest.raises(RuntimeError,match="not found"):
        run_openfoam_cases(tmp_path/"cases")

def test_v10_runner_records_foundation_identity_for_every_stage(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases")
    monkeypatch.setenv("WM_PROJECT", "OpenFOAM")
    monkeypatch.setenv("WM_PROJECT_VERSION", "10")
    monkeypatch.setattr("cleanroomx.cfd_openfoam.shutil.which",lambda name:f"/fake/{name}")
    banner=("  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox\n"
            "  \\\\    /   O peration     | Website:  https://openfoam.org\n"
            "     \\\\/     M anipulation  | Version:  10\n"
            "Build  : 10-c4cf895ad8fa\n")

    def fake_run(command,**kwargs):
        if command[-1] == "-help":
            return SimpleNamespace(returncode=0,stdout="OpenFOAM-10\n",stderr="")
        kwargs["stdout"].write(banner)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("cleanroomx.cfd_openfoam.subprocess.run",fake_run)
    result=run_openfoam_cases(tmp_path/"cases")
    assert result["status"]=="executed_requires_convergence_review"
    assert result["solver_release"]=="OpenFOAM Foundation 10"
    assert result["solver_build"]=="10-c4cf895ad8fa"
    record=json.loads((tmp_path/"cases"/"run_manifest.json").read_text())
    assert record["foundation_build"]=="10-c4cf895ad8fa"
    assert all(
        stage["openfoam"]["is_foundation_v10"]
        for case in record["cases"].values()
        for stage in case["stages"]
    )

def test_v10_runner_rejects_mismatched_stage_banner(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases")
    monkeypatch.setenv("WM_PROJECT", "OpenFOAM")
    monkeypatch.setenv("WM_PROJECT_VERSION", "10")
    monkeypatch.setattr("cleanroomx.cfd_openfoam.shutil.which",lambda name:f"/fake/{name}")
    wrong_banner=("Website: https://openfoam.com\nVersion: 10\nBuild : 10-build\n")

    def fake_run(command,**kwargs):
        if command[-1] == "-help":
            return SimpleNamespace(returncode=0,stdout="OpenFOAM-10\n",stderr="")
        kwargs["stdout"].write(wrong_banner)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("cleanroomx.cfd_openfoam.subprocess.run",fake_run)
    result=run_openfoam_cases(tmp_path/"cases")
    assert result["status"]=="incomplete"
    assert result["cases"]["1"]["status"]=="unsupported_release"
    record=json.loads((tmp_path/"cases"/"run_manifest.json").read_text())
    assert record["status"]=="incomplete"
    assert record["failure"]["stage"]["program"]=="blockMesh"

def test_v10_runner_rejects_mixed_stage_builds(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases")
    monkeypatch.setenv("WM_PROJECT", "OpenFOAM")
    monkeypatch.setenv("WM_PROJECT_VERSION", "10")
    monkeypatch.setattr("cleanroomx.cfd_openfoam.shutil.which",lambda name:f"/fake/{name}")

    def fake_run(command,**kwargs):
        if command[-1] == "-help":
            return SimpleNamespace(returncode=0,stdout="OpenFOAM-10\n",stderr="")
        build="10-first-build" if command[0].endswith("blockMesh") else "10-other-build"
        kwargs["stdout"].write(f"Website: https://openfoam.org\nVersion: 10\nBuild : {build}\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("cleanroomx.cfd_openfoam.subprocess.run",fake_run)
    result=run_openfoam_cases(tmp_path/"cases")
    assert result["status"]=="incomplete"
    assert result["cases"]["1"]["status"]=="inconsistent_build"
    record=json.loads((tmp_path/"cases"/"run_manifest.json").read_text())
    assert record["failure"]["stage"]["program"]=="checkMesh"

def test_runner_rejects_mismatched_active_foundation_release(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases",openfoam_version="v14")
    monkeypatch.setenv("WM_PROJECT", "OpenFOAM")
    monkeypatch.setenv("WM_PROJECT_VERSION", "10")
    with pytest.raises(RuntimeError,match="active OpenFOAM environment mismatch"):
        run_openfoam_cases(tmp_path/"cases")

def test_runner_rejects_solver_binary_from_other_release(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases",openfoam_version="v14")
    monkeypatch.setenv("WM_PROJECT", "OpenFOAM")
    monkeypatch.setenv("WM_PROJECT_VERSION", "14")
    monkeypatch.setattr("cleanroomx.cfd_openfoam.shutil.which",lambda name:"/usr/bin/mock")
    monkeypatch.setattr(
        "cleanroomx.cfd_openfoam.subprocess.run",
        lambda *args,**kwargs:SimpleNamespace(returncode=0,stdout="OpenFOAM-140\n",stderr=""),
    )
    with pytest.raises(RuntimeError,match="did not identify OpenFOAM Foundation 14"):
        run_openfoam_cases(tmp_path/"cases")
    assert not (tmp_path/"cases"/"run_manifest.json").exists()

def test_tampered_case_fails_closed(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases")
    monkeypatch.setenv("WM_PROJECT", "OpenFOAM")
    monkeypatch.setenv("WM_PROJECT_VERSION", "10")
    p=tmp_path/"cases/configuration_1/0/U"
    p.write_text(p.read_text()+"\n// tamper")
    monkeypatch.setattr("cleanroomx.cfd_openfoam.shutil.which",lambda name:"/usr/bin/mock")
    with pytest.raises(ValueError,match="Tampered"):
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
