"""SYNTHETIC regression fixtures; not proof of real CFD physics validation."""
import json
import math
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
        assert "simulationType laminar;" in (f/"constant/turbulenceProperties").read_text()
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

def test_solver_not_installed_fails_closed(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases")
    monkeypatch.setattr("cleanroomx.cfd_openfoam.shutil.which",lambda name:None)
    with pytest.raises(RuntimeError,match="not found"):
        run_openfoam_cases(tmp_path/"cases")

def test_tampered_case_fails_closed(tmp_path,monkeypatch):
    export_openfoam_cases(spec(),tmp_path/"cases")
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
