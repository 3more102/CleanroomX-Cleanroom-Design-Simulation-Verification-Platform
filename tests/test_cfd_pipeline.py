"""SYNTHETIC regression fixtures; not proof of real CFD physics validation."""
import json
import math
import re
from types import SimpleNamespace
import pytest

from cleanroomx.cfd_openfoam import (
    SCHEMA, _layout, audit_openfoam_boundary_inputs, build_openfoam_files, export_openfoam_cases,
    run_openfoam_cases, validate_openfoam_spec,
)
from cleanroomx.cfd_vtk import (
    audit_openfoam_vtk_boundary_patch,
    audit_openfoam_vtk_pressure,
    audit_openfoam_vtk_velocity,
    import_vtk_case,
    populate_study_from_vtk,
)

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

@pytest.mark.parametrize(("mutation","message"),[
    ("duplicate","duplicated across patches"),
    ("omit","cover every exterior hex face"),
])
def test_boundary_audit_rejects_duplicate_or_missing_exterior_faces(mutation,message):
    files,metadata=build_openfoam_files(spec(),1)
    tampered=dict(files)
    mesh=tampered["system/blockMeshDict"]
    match=re.search(
        r"(?ms)(^\s*inlet\s*\{.*?^\s*faces\s*\(\s*)(.*?)(^\s*\);\s*\})",mesh
    )
    assert match is not None
    face_lines=list(re.finditer(
        r"(?m)^\s*(\(\s*\d+\s+\d+\s+\d+\s+\d+\s*\))\s*$",match.group(2)
    ))
    assert len(face_lines)>=2
    body=match.group(2)
    if mutation=="duplicate":
        first,second=face_lines[0],face_lines[1]
        body=body[:second.start(1)]+first.group(1)+body[second.end(1):]
    else:
        last=face_lines[-1]
        body=body[:last.start()]+body[last.end():]
    tampered["system/blockMeshDict"]=mesh[:match.start(2)]+body+mesh[match.end(2):]
    with pytest.raises(ValueError,match=message):
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

def openfoam_velocity_fixture(path):
    path.write_text("\n".join((
        "FoamFile",
        "{",
        "    format ascii;",
        "    class volVectorField;",
        '    location "150";',
        "    object U;",
        "}",
        "dimensions [0 1 -1 0 0 0 0];",
        "internalField nonuniform List<vector>",
        "2",
        "(",
        "(1.234567891 -0.25 0.000001234567)",
        "(-3.14159265 0.00000001 0.125000001)",
        ");",
        "boundaryField {}",
        "",
    )),encoding="ascii")

def legacy_vtk_velocity_fixture(
    path, *, cell_ids=(1, 0), perturb=0.0, pressure_perturb=0.0,
    include_ids=True, point_velocity=False
):
    vtk=pytest.importorskip("vtk")
    native=((1.234567891,-0.25,0.000001234567),
            (-3.14159265,0.00000001,0.125000001))
    native_pressure=(0.123456789, -2.5)
    grid=vtk.vtkUnstructuredGrid()
    points=vtk.vtkPoints()
    for cell_index in range(2):
        offset=2.0*cell_index
        coordinates=((offset,0,0),(offset+1,0,0),(offset+1,1,0),(offset,1,0),
                     (offset,0,1),(offset+1,0,1),(offset+1,1,1),(offset,1,1))
        start=points.GetNumberOfPoints()
        for point in coordinates:
            points.InsertNextPoint(*point)
        cell=vtk.vtkHexahedron()
        for local_index in range(8):
            cell.GetPointIds().SetId(local_index,start+local_index)
        grid.InsertNextCell(cell.GetCellType(),cell.GetPointIds())
    grid.SetPoints(points)
    velocity=vtk.vtkFloatArray()
    velocity.SetName("U")
    velocity.SetNumberOfComponents(3)
    pressure=vtk.vtkFloatArray()
    pressure.SetName("p")
    ids=vtk.vtkIntArray()
    ids.SetName("cellID")
    for cell_id in cell_ids:
        vector=list(native[cell_id])
        if perturb:
            vector[0]+=perturb
        velocity.InsertNextTuple3(*vector)
        pressure.InsertNextValue(native_pressure[cell_id]+pressure_perturb)
        ids.InsertNextValue(cell_id)
    if point_velocity:
        point_u=vtk.vtkFloatArray()
        point_u.SetName("U")
        point_u.SetNumberOfComponents(3)
        for _ in range(points.GetNumberOfPoints()):
            point_u.InsertNextTuple3(0,0,0)
        grid.GetPointData().AddArray(point_u)
    else:
        grid.GetCellData().AddArray(velocity)
    grid.GetCellData().AddArray(pressure)
    if include_ids:
        grid.GetCellData().AddArray(ids)
    writer=vtk.vtkUnstructuredGridWriter()
    writer.SetFileName(str(path))
    writer.SetFileTypeToASCII()
    writer.SetInputData(grid)
    assert writer.Write()==1

def test_openfoam_vtk_velocity_parity_uses_cell_ids_and_float32_tolerance(tmp_path):
    native=tmp_path/"150"/"U"
    native.parent.mkdir()
    openfoam_velocity_fixture(native)
    exported=tmp_path/"case_150.vtk"
    legacy_vtk_velocity_fixture(exported,cell_ids=(1,0))

    report=audit_openfoam_vtk_velocity(native,exported)

    assert report["status"]=="PASS"
    assert report["cell_id_mapping"]=="complete_unique_permutation_of_native_cell_indices"
    assert report["cell_count"]==2
    assert report["compared_velocity_components"]==6
    assert report["vtk_velocity_scalar_type"]=="float"
    assert report["max_absolute_error_native_to_vtk_m_s"]>0
    assert report["max_absolute_error_native_to_vtk_m_s"] <= report["max_allowed_native_to_vtk_error_m_s"]

def test_openfoam_vtk_velocity_parity_rejects_missing_or_duplicate_cell_ids(tmp_path):
    native=tmp_path/"150"/"U"
    native.parent.mkdir()
    openfoam_velocity_fixture(native)
    missing=tmp_path/"missing_ids.vtk"
    legacy_vtk_velocity_fixture(missing,include_ids=False)
    with pytest.raises(ValueError,match="cellID"):
        audit_openfoam_vtk_velocity(native,missing)

    duplicate=tmp_path/"duplicate_ids.vtk"
    legacy_vtk_velocity_fixture(duplicate,cell_ids=(0,0))
    with pytest.raises(ValueError,match="unique in-range"):
        audit_openfoam_vtk_velocity(native,duplicate)

    point_only=tmp_path/"point_only_U.vtk"
    legacy_vtk_velocity_fixture(point_only,point_velocity=True)
    with pytest.raises(ValueError,match="cell-data U"):
        audit_openfoam_vtk_velocity(native,point_only)

def test_openfoam_vtk_velocity_parity_rejects_field_mismatch(tmp_path):
    native=tmp_path/"150"/"U"
    native.parent.mkdir()
    openfoam_velocity_fixture(native)
    exported=tmp_path/"mismatch.vtk"
    legacy_vtk_velocity_fixture(exported,perturb=0.01)
    with pytest.raises(ValueError,match="differs from the native field"):
        audit_openfoam_vtk_velocity(native,exported)

def openfoam_pressure_fixture(path):
    path.write_text("\n".join((
        "FoamFile",
        "{",
        "    format ascii;",
        "    class volScalarField;",
        '    location "150";',
        "    object p;",
        "}",
        "dimensions [0 2 -2 0 0 0 0];",
        "internalField nonuniform List<scalar>",
        "2",
        "(",
        "0.123456789",
        "-2.5",
        ");",
        "boundaryField {}",
        "",
    )), encoding="ascii")

def test_openfoam_vtk_pressure_parity_uses_cell_ids_and_float32_tolerance(tmp_path):
    native=tmp_path/"150"/"p"
    native.parent.mkdir()
    openfoam_pressure_fixture(native)
    exported=tmp_path/"case_150.vtk"
    legacy_vtk_velocity_fixture(exported,cell_ids=(1,0))

    report=audit_openfoam_vtk_pressure(native,exported)

    assert report["status"]=="PASS"
    assert report["field"]=="p"
    assert report["dimensions"]=="[0 2 -2 0 0 0 0]"
    assert report["cell_id_mapping"]=="complete_unique_permutation_of_native_cell_indices"
    assert report["cell_count"]==2
    assert report["compared_scalar_values"]==2
    assert report["vtk_scalar_type"]=="float"
    assert report["max_absolute_error_native_to_vtk_m2_s2"]>0
    assert report["max_absolute_error_native_to_vtk_m2_s2"] <= report["max_allowed_native_to_vtk_error_m2_s2"]

def test_openfoam_vtk_pressure_parity_rejects_wrong_dimensions_and_mismatch(tmp_path):
    native=tmp_path/"150"/"p"
    native.parent.mkdir()
    openfoam_pressure_fixture(native)
    exported=tmp_path/"case_150.vtk"
    legacy_vtk_velocity_fixture(exported,pressure_perturb=0.01)
    with pytest.raises(ValueError,match="differs from the native field"):
        audit_openfoam_vtk_pressure(native,exported)

    native.write_text(native.read_text(encoding="ascii").replace(
        "dimensions [0 2 -2 0 0 0 0];", "dimensions [0 1 -1 0 0 0 0];"
    ), encoding="ascii")
    with pytest.raises(ValueError,match="kinematic-pressure dimensions"):
        audit_openfoam_vtk_pressure(native,exported)

def openfoam_patch_fixture(case_dir):
    mesh=case_dir/"constant"/"polyMesh"
    mesh.mkdir(parents=True)
    (mesh/"points").write_text("\n".join((
        "FoamFile { format ascii; class vectorField; object points; }",
        "6", "(", "(0 0 0)", "(1 0 0)", "(0 1 0)",
        "(0 0 1)", "(2 0 0)", "(2 1 0)", ");", "",
    )),encoding="ascii")
    (mesh/"faces").write_text("\n".join((
        "FoamFile { format ascii; class faceList; object faces; }",
        "2", "(", "3(0 1 2)", "3(1 4 5)", ");", "",
    )),encoding="ascii")
    (mesh/"owner").write_text("\n".join((
        "FoamFile { format ascii; class labelList; object owner; }",
        "2", "(", "0", "1", ");", "",
    )),encoding="ascii")
    (mesh/"boundary").write_text("\n".join((
        "FoamFile { format ascii; class polyBoundaryMesh; object boundary; }",
        "1", "(", "outlet", "{", "type patch;", "nFaces 2;", "startFace 0;", "}", ");", "",
    )),encoding="ascii")
    time_dir=case_dir/"150"
    time_dir.mkdir()
    (time_dir/"U").write_text("\n".join((
        "FoamFile { format ascii; class volVectorField; object U; }",
        "dimensions [0 1 -1 0 0 0 0];",
        "internalField nonuniform List<vector> 2 ((0 0 0) (0 0 0));",
        "boundaryField { outlet { type fixedValue;",
        "value nonuniform List<vector> 2 ((1.234567891 0 0) (2.34567891 3.45678912 0)); } }", "",
    )),encoding="ascii")
    (time_dir/"p").write_text("\n".join((
        "FoamFile { format ascii; class volScalarField; object p; }",
        "dimensions [0 2 -2 0 0 0 0];",
        "internalField nonuniform List<scalar> 2 (4.123456789 5.123456789);",
        "boundaryField { outlet { type zeroGradient; } }", "",
    )),encoding="ascii")
    return mesh,time_dir

def legacy_vtk_patch_fixture(path, *, reverse=True, perturb_velocity=0.0,
                             patch_id=0, shift_geometry=0.0):
    vtk=pytest.importorskip("vtk")
    native_points=((0,0,0),(1,0,0),(0,1,0),(0,0,1),(2,0,0),(2,1,0))
    native_faces=((0,1,2),(1,4,5))
    native_velocity=((1.234567891,0,0),(2.34567891,3.45678912,0))
    native_pressure=(4.123456789,5.123456789)
    poly=vtk.vtkPolyData()
    points=vtk.vtkPoints()
    point_order=(5,4,2,1,0)
    point_ids={}
    for native_id in point_order:
        x,y,z=native_points[native_id]
        point_ids[native_id]=points.InsertNextPoint(x+shift_geometry,y,z)
    poly.SetPoints(points)
    polys=vtk.vtkCellArray()
    order=(1,0) if reverse else (0,1)
    velocity=vtk.vtkFloatArray()
    velocity.SetName("U")
    velocity.SetNumberOfComponents(3)
    pressure=vtk.vtkFloatArray()
    pressure.SetName("p")
    patch_ids=vtk.vtkFloatArray()
    patch_ids.SetName("patchID")
    for face_index in order:
        face=native_faces[face_index]
        cell=vtk.vtkPolygon()
        cell.GetPointIds().SetNumberOfIds(len(face))
        # Reversing the vertex order keeps an equivalent polygon while
        # ensuring neither point nor face array order is treated as identity.
        for local_index,native_point_id in enumerate(reversed(face)):
            cell.GetPointIds().SetId(local_index,point_ids[native_point_id])
        polys.InsertNextCell(cell)
        vector=list(native_velocity[face_index])
        vector[0]+=perturb_velocity
        velocity.InsertNextTuple3(*vector)
        pressure.InsertNextValue(native_pressure[face_index])
        patch_ids.InsertNextValue(patch_id)
    poly.SetPolys(polys)
    poly.GetCellData().AddArray(velocity)
    poly.GetCellData().AddArray(pressure)
    poly.GetCellData().AddArray(patch_ids)
    writer=vtk.vtkPolyDataWriter()
    writer.SetFileName(str(path))
    writer.SetFileTypeToASCII()
    writer.SetInputData(poly)
    assert writer.Write()==1

def test_openfoam_vtk_boundary_patch_parity_maps_faces_by_geometry(tmp_path):
    case=tmp_path/"case"
    mesh,time_dir=openfoam_patch_fixture(case)
    exported=tmp_path/"outlet_150.vtk"
    legacy_vtk_patch_fixture(exported,reverse=True)

    report=audit_openfoam_vtk_boundary_patch(
        time_dir/"U",time_dir/"p",mesh,exported,"outlet"
    )

    assert report["status"]=="PASS"
    assert report["patch_id"]==0
    assert report["native_face_count"]==report["vtk_face_count"]==2
    assert report["face_mapping"]=="complete_unique_geometry_signature_at_ascii_precision"
    assert report["native_u_boundary_type"]=="fixedValue"
    assert report["native_p_boundary_type"]=="zeroGradient"
    assert report["compared_velocity_components"]==6
    assert report["compared_pressure_values"]==2
    assert 0 < report["max_absolute_velocity_error_m_s"] <= report["max_allowed_velocity_error_m_s"]
    assert report["max_absolute_pressure_error_m2_s2"] <= report["max_allowed_pressure_error_m2_s2"]

def test_openfoam_vtk_boundary_patch_parity_rejects_wrong_geometry_id_and_values(tmp_path):
    case=tmp_path/"case"
    mesh,time_dir=openfoam_patch_fixture(case)
    exported=tmp_path/"outlet_150.vtk"

    legacy_vtk_patch_fixture(exported,shift_geometry=0.1)
    with pytest.raises(ValueError,match="face geometry"):
        audit_openfoam_vtk_boundary_patch(time_dir/"U",time_dir/"p",mesh,exported,"outlet")

    legacy_vtk_patch_fixture(exported,patch_id=1)
    with pytest.raises(ValueError,match="patchID"):
        audit_openfoam_vtk_boundary_patch(time_dir/"U",time_dir/"p",mesh,exported,"outlet")

    legacy_vtk_patch_fixture(exported,perturb_velocity=0.1)
    with pytest.raises(ValueError,match="patch U differs"):
        audit_openfoam_vtk_boundary_patch(time_dir/"U",time_dir/"p",mesh,exported,"outlet")

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
