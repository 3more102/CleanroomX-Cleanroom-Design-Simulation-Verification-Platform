"""Numerical verification fixtures. No fabricated CFD evidence is treated as physical validation."""
import hashlib
import json
import math
from pathlib import Path

import pytest

from cleanroomx.cfd_grid_family import SCHEMA as FAMILY_SCHEMA, generate_grid_family, validate_family_spec
from cleanroomx.cfd_grid_study import (
    SCHEMA, _analysis, _observed_order, _resolve_study_input, analyze_vtk_grid_study, validate_grid_spec,
)


def family_spec():
    return {
        "schema_version":FAMILY_SCHEMA,
        "base_case":{
            "schema_version":"cleanroomx.openfoam.v1",
            "name":"SYNTHETIC nine-case mesh study",
            "room_m":[1,1,1],
            "mesh_cells":[6,6,6],
            "supply_flow_m3_s":0.1,
            "kinematic_viscosity_m2_s":1.5e-5,
            "max_iterations":100,
            "output_interval":20,
        },
        "mesh_levels":{"coarse":[6,6,6],"medium":[9,9,9],"fine":[12,12,12]},
    }


def criteria():
    return {
        "min_refinement_ratio":1.1,
        "max_relative_volume_error":0.001,
        "min_observed_order":0.5,
        "max_observed_order":6.0,
        "max_fine_gci_percent":5.0,
        "safety_factor":1.25,
        "max_axis_ratio_spread":0.05,
    }


def audit_params():
    return {
        "fields":["Ux","Uy","Uz","p"],"window":3,
        "max_initial_residual":1e-5,"max_final_residual":1e-7,
        "max_global_continuity":1e-6,
    }


def study_spec():
    return {
        "schema_version":SCHEMA,"name":"Synthetic and externally testable mesh study",
        "configuration":1,"room_volume_m3":1,"quantity":"velocity_mean_m_s",
        "unit":"m/s","criteria":criteria(),"log_audit":audit_params(),
        "runs":[
            {"level":level,"mesh_cells":[n,n,n],"vtk_file":f"{level}.vtu",
             "solver_log":f"{level}.log","run_id":level+"-synthetic",
             "conditions_sha256":"a"*64}
            for level,n in (("fine",8),("medium",4),("coarse",2))
        ],
    }


def test_nasa_three_grid_reference():
    # NASA Glenn: pressure-recovery values 0.97050, 0.96854, 0.96178,
    # with spacing h=1,2,4; reported observed p ~1.78617, GCI ~0.10308%.
    rows=[{"value":v,"characteristic_h_m":h}
          for v,h in ((0.97050,1),(0.96854,2),(0.96178,4))]
    result=_analysis(rows,criteria())
    assert result["observed_order"]==pytest.approx(1.78617,abs=3e-5)
    assert result["richardson_zero_spacing_estimate"]==pytest.approx(.97130,abs=2e-5)
    assert result["fine_grid_gci_percent"]==pytest.approx(.10308,abs=3e-5)
    assert result["screening_status"]=="eligible_for_engineering_review"


def test_exact_second_order_nonuniform_ratios():
    h1,h2,h3=.1,.16,.32
    p=2
    f=lambda h:4-1.7*h**p
    assert _observed_order(h1,h2,h3,f(h1),f(h2),f(h3))==pytest.approx(p,abs=1e-9)


@pytest.mark.parametrize("values",[
    (1,2,1), (1,2,3.0), (3,2,1), (1,1,1), (0,0.5,0.2),
])
def test_nonconvergence_or_unusable_order_fails_closed(values):
    rows=[{"value":v,"characteristic_h_m":h}
          for v,h in zip(values,(1,2,4))]
    result=_analysis(rows,criteria())
    if values==(1,2,3.0): # linear changes imply observed p=0, not positive
        assert result["screening_status"]=="indeterminate_or_failed"
    else:
        assert result["screening_status"]=="indeterminate_or_failed"


def test_zero_fine_grid_value_has_no_relative_gci():
    rows=[{"value":v,"characteristic_h_m":h}
          for v,h in ((0,1),(1,2),(5,4))]
    result=_analysis(rows,criteria())
    assert result["fine_grid_gci_percent"] is None
    assert result["screening_status"]=="indeterminate_or_failed"


def test_generate_nine_openfoam_cases_reproducibly(tmp_path):
    spec=family_spec()
    report=generate_grid_family(spec,tmp_path/"family")
    assert len(report["case_inputs"])==9
    assert len(report["files"])==72
    assert report["status"]=="generated_not_executed"
    for config in (1,2,3):
        for level in ("coarse","medium","fine"):
            root=tmp_path/"family"/f"configuration_{config}"/level
            expected=report["case_inputs"][f"configuration_{config}/{level}"]
            assert expected["mesh_cells"]==math.prod(spec["mesh_levels"][level])
            assert (root/"system/blockMeshDict").is_file()
            assert (root/"0/U").is_file()
            assert hashlib.sha256((root/"0/U").read_bytes()).hexdigest()==report["files"][
                f"configuration_{config}/{level}/0/U"
            ]
    second=generate_grid_family(spec,tmp_path/"family-other")
    assert second==report
    with pytest.raises(FileExistsError):
        generate_grid_family(spec,tmp_path/"family")


@pytest.mark.parametrize("bad_levels",[
    {"coarse":[6,6,6],"medium":[9,9,9],"fine":[9,12,12]},
    {"coarse":[6,6,6],"medium":[9,9,9],"fine":[30,30,30]},
    {"coarse":[6,6,6],"medium":[9,9,9],"fine":[12,12,True]},
    {"coarse":[6,6,6],"medium":[6,9,9],"fine":[12,12,12]},
])
def test_reject_invalid_grid_families(bad_levels):
    spec=family_spec();spec["mesh_levels"]=bad_levels
    with pytest.raises(ValueError):
        validate_family_spec(spec)


def test_spec_requires_identical_comparability_fingerprints():
    spec=study_spec()
    validate_grid_spec(spec)
    spec["runs"][0]["conditions_sha256"]="f"*64
    assert len({run["conditions_sha256"] for run in spec["runs"]})==2


@pytest.mark.parametrize("mutator",[
    lambda s:s.update(schema_version="bogus"),
    lambda s:s.update(configuration=True),
    lambda s:s.update(quantity="temperature"),
    lambda s:s.update(unit="km/h"),
    lambda s:s["criteria"].update(min_refinement_ratio=1),
    lambda s:s["criteria"].update(safety_factor=1),
    lambda s:s["runs"][0].update(level="medium"),
    lambda s:s["runs"][0].update(mesh_cells=[2,False,2]),
    lambda s:s["runs"][0].update(vtk_file=""),
    lambda s:s["runs"][0].update(conditions_sha256="bad"),
])
def test_invalid_grid_study_rejected(mutator):
    spec=study_spec();mutator(spec)
    with pytest.raises(ValueError):
        validate_grid_spec(spec)



def test_grid_evidence_allows_files_in_nested_study_directory(tmp_path):
    study = tmp_path / "study"
    nested = study / "solved"
    nested.mkdir(parents=True)
    vtk_path = nested / "fine.vtu"
    vtk_path.write_bytes(b"VTK-placeholder")
    assert _resolve_study_input(study, "solved/fine.vtu", "VTK file") == vtk_path


@pytest.mark.parametrize("escape", ["absolute", "parent"])
def test_grid_evidence_rejects_absolute_and_parent_traversal(tmp_path, escape):
    study = tmp_path / "study"
    study.mkdir()
    external = tmp_path / "external.vtu"
    external.write_bytes(b"VTK-placeholder")
    supplied = str(external) if escape == "absolute" else "../external.vtu"
    with pytest.raises(ValueError, match="relative|outside"):
        _resolve_study_input(study, supplied, "VTK file")


def test_grid_evidence_rejects_symlink_that_escapes_study_directory(tmp_path):
    study = tmp_path / "study"
    study.mkdir()
    external = tmp_path / "outside.log"
    external.write_text("external data", encoding="utf-8")
    link = study / "solver.log"
    try:
        link.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("This runner cannot create symbolic links")
    with pytest.raises(ValueError, match="outside"):
        _resolve_study_input(study, "solver.log", "solver log")


def test_grid_audit_rejects_escaping_source_before_external_vtk_import(tmp_path):
    study = tmp_path / "study"
    study.mkdir()
    (tmp_path / "escape.vtu").write_bytes(b"must-not-be-read")
    spec = study_spec()
    spec["runs"][0]["vtk_file"] = "../escape.vtu"
    with pytest.raises(ValueError, match="fine VTK file.*outside"):
        analyze_vtk_grid_study(spec, base_directory=study)


def _vtk_case(path,n,velocity):
    vtk=pytest.importorskip("vtk")
    points=vtk.vtkPoints()
    for k in range(n+1):
        for j in range(n+1):
            for i in range(n+1):
                points.InsertNextPoint(i/n,j/n,k/n)
    grid=vtk.vtkUnstructuredGrid()
    grid.SetPoints(points)
    u=vtk.vtkDoubleArray();u.SetName("U");u.SetNumberOfComponents(3)
    t=vtk.vtkDoubleArray();t.SetName("T");t.SetNumberOfComponents(1)
    idx=lambda i,j,k: (k*(n+1)+j)*(n+1)+i
    for k in range(n):
        for j in range(n):
            for i in range(n):
                vertices=[
                    idx(i,j,k),idx(i+1,j,k),idx(i+1,j+1,k),idx(i,j+1,k),
                    idx(i,j,k+1),idx(i+1,j,k+1),idx(i+1,j+1,k+1),idx(i,j+1,k+1),
                ]
                cell=vtk.vtkHexahedron()
                for m,v in enumerate(vertices):
                    cell.GetPointIds().SetId(m,v)
                grid.InsertNextCell(cell.GetCellType(),cell.GetPointIds())
                u.InsertNextTuple3(velocity,0,0)
                t.InsertNextValue(velocity)
    grid.GetCellData().AddArray(u);grid.GetCellData().AddArray(t)
    writer=vtk.vtkXMLUnstructuredGridWriter()
    writer.SetFileName(str(path));writer.SetInputData(grid)
    assert writer.Write()==1


def _solver_log(path):
    # Mark synthetic logs uniquely to model independent case outputs.
    lines=[f"Synthetic run identifier: {path.stem}"]
    for _ in range(3):
        for field in ("Ux","Uy","Uz","p"):
            lines.append(f"Solving for {field}, Initial residual = 1e-8, Final residual = 1e-11, No Iterations 3")
        lines.append("time step continuity errors : sum local = 1e-9, global = 1e-10, cumulative = 3e-10")
    path.write_text("\n".join(lines)+"\nEnd\n")


def test_real_vtk_three_grid_convergence_and_incomplete_evidence(tmp_path):
    spec=study_spec()
    for record in spec["runs"]:
        n=record["mesh_cells"][0]
        # Synthetic O(h^2) field manufactured solely to test GCI calculation.
        velocity=1+.1*(1/n)**2
        _vtk_case(tmp_path/record["vtk_file"],n,velocity)
        _solver_log(tmp_path/record["solver_log"])
    result=analyze_vtk_grid_study(spec,base_directory=tmp_path)
    assert result["status"]=="eligible_for_engineering_review",result["blockers"]
    assert result["observed_order"]==pytest.approx(2,abs=1e-6)
    assert result["richardson_zero_spacing_estimate"]==pytest.approx(1,abs=1e-7)
    assert all(r["log_screening_status"]=="numerically_screened" for r in result["grids"])
    assert all(r["relative_volume_error"]<1e-10 for r in result["grids"])
    assert result["grids"][0]["vtk_sha256"]!=result["grids"][1]["vtk_sha256"]
    assert len({row["log_sha256"] for row in result["grids"]}) == 3

    # Distinct declared log paths cannot disguise byte-identical replay.
    (tmp_path/"medium.log").write_bytes((tmp_path/"fine.log").read_bytes())
    replayed=analyze_vtk_grid_study(spec,base_directory=tmp_path)
    assert replayed["status"]=="indeterminate_or_failed"
    assert any("Duplicate solver logs" in b for b in replayed["blockers"])
    _solver_log(tmp_path/"medium.log")
    restored=analyze_vtk_grid_study(spec,base_directory=tmp_path)
    assert restored["status"]=="eligible_for_engineering_review",restored["blockers"]
    spec["runs"][0]["conditions_sha256"]="f"*64
    mismatched=analyze_vtk_grid_study(spec,base_directory=tmp_path)
    assert mismatched["status"]=="indeterminate_or_failed"
    assert any("fingerprint" in b for b in mismatched["blockers"])
    spec["runs"][0]["conditions_sha256"]="a"*64
    spec["runs"][0]["mesh_cells"]=[10,10,10]
    wrong=analyze_vtk_grid_study(spec,base_directory=tmp_path)
    assert wrong["status"]=="indeterminate_or_failed"
    assert any("cell count" in b for b in wrong["blockers"])
    spec["runs"][0]["mesh_cells"]=[8,8,8]
    (tmp_path/"fine.log").write_text("Solving for p, Initial residual = 1e-10, Final residual = 1e-11\n")
    rejected=analyze_vtk_grid_study(spec,base_directory=tmp_path)
    assert rejected["status"]=="indeterminate_or_failed"
    assert any("residual audit" in b for b in rejected["blockers"])
