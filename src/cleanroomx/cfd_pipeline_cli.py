"""CLI for reproducible OpenFOAM case generation, execution and VTK studies."""
from __future__ import annotations
import argparse
import sys
from .cfd_openfoam import export_openfoam_cases, run_openfoam_cases
from .cfd_project_rooms import generate_project_room_cases, run_project_room_cases
from .cfd_project_audit import audit_project_room_cases
from .cfd_multizone import generate_multizone_open_door_case, run_multizone_open_door_case
from .cfd_relaxation_comparison import (
    compare_independent_relaxation_cases,
    export_independent_relaxation_comparison,
)
from .cfd_multizone_results import analyze_multizone_case, export_multizone_report
from .cfd_vtk import populate_study_from_vtk
from .cfd_visualization import render_cfd_cross_section
from .cfd_scalar import prepare_scalar_case, run_scalar_case
from .cfd_audit import audit_openfoam_log
from .cfd_residual_dashboard import render_residual_dashboard
from .cfd_grid_study import analyze_vtk_grid_study, validate_grid_spec
from .cfd_grid_family import generate_grid_family
from pathlib import Path
from .cli_output import cli_error_boundary, dumps_strict_json, load_cli_input, publish_cli_output
from .strict_json import load_strict_json

def build_parser():
    parser=argparse.ArgumentParser(prog="cleanroomx-cfd-pipeline",
                                   description="OpenFOAM v10 and VTK cleanroom CFD pipeline")
    sub=parser.add_subparsers(dest="command",required=True)
    create=sub.add_parser("generate",help="Generate three OpenFOAM cases")
    create.add_argument("spec")
    create.add_argument("directory")
    runner=sub.add_parser("run",help="Opt-in: run blockMesh, checkMesh, simpleFoam")
    runner.add_argument("directory")
    runner.add_argument("--timeout-seconds",type=int,default=3600)
    project=sub.add_parser(
        "project-rooms-generate",
        help="Generate independent OpenFOAM v10 CFD cases for ceiling-FFU rooms and closed doors",
    )
    project.add_argument("project", help="CleanroomX GUI project JSON")
    project.add_argument("directory", help="New output directory (must not exist)")
    project.add_argument(
        "--kinematic-viscosity-m2-s", type=float, required=True,
        help="Explicit finite positive physical air property; never inferred",
    )
    project.add_argument("--mesh-cells", type=int, nargs=3, default=[24, 24, 12],
                         metavar=("NX", "NY", "NZ"))
    project.add_argument("--max-iterations", type=int, default=150)
    project.add_argument("--output-interval", type=int, default=50)
    project_run=sub.add_parser(
        "project-rooms-run",
        help="Opt-in run of independent hashed room cases: blockMesh, checkMesh, simpleFoam",
    )
    project_run.add_argument("directory")
    project_run.add_argument("--timeout-seconds", type=int, default=3600)
    project_audit=sub.add_parser(
        "project-rooms-audit",
        help="Fail-closed numerical screening of generated room solver logs",
    )
    project_audit.add_argument("directory")
    project_audit.add_argument("--fields", required=True, nargs="+")
    project_audit.add_argument("--max-initial-residual", required=True, type=float)
    project_audit.add_argument("--max-final-residual", required=True, type=float)
    project_audit.add_argument("--max-global-continuity", type=float)
    project_audit.add_argument("--window", type=int, default=3)
    multizone=sub.add_parser(
        "multizone-generate",
        help="Create ONE connected OpenFOAM CFD input domain through expressly OPEN doors",
    )
    multizone.add_argument("project")
    multizone.add_argument("directory")
    multizone.add_argument("--door-mode", choices=("open",), required=True,
                           help="Required: open door passages are a different scenario from the 5 Pa closed-door network")
    multizone.add_argument("--kinematic-viscosity-m2-s", type=float, required=True)
    multizone.add_argument("--cell-size-x-m", type=float, default=0.5)
    multizone.add_argument("--cell-size-y-m", type=float, default=0.1)
    multizone.add_argument("--cell-size-z-m", type=float, default=0.3)
    multizone.add_argument("--max-iterations", type=int, default=150)
    multizone.add_argument("--output-interval", type=int, default=50)
    multizone.add_argument(
        "--pressure-relaxation", type=float, default=0.3,
        help="SIMPLE pressure field relaxation 0.05..0.7; numerical sensitivity ONLY")
    multizone.add_argument(
        "--velocity-relaxation", type=float, default=0.7,
        help="SIMPLE velocity equation relaxation 0.1..0.95; numerical sensitivity ONLY")
    sensitivity=sub.add_parser(
        "multizone-compare-relaxation",
        help="Compare TWO executed matched-source OpenFOAM relaxation cases; engineering HOLD")
    sensitivity.add_argument("baseline_directory")
    sensitivity.add_argument("variant_directory")
    sensitivity.add_argument("--density-kg-m3",type=float,default=1.2)
    sensitivity.add_argument("--reference-room-id",default="corridor")
    sensitivity.add_argument("--output",help="Create a NEW noncertifying comparison JSON file")
    local=sub.add_parser(
        "multizone-leakage-local",
        help="Individually vary each sourced CLOSED-door leakage path; not CFD",
    )
    local.add_argument("case_directory",help="Executed, hash-checked all-open OpenFOAM case")
    local.add_argument("scenario",help="Explicit closed-door JSON leakage/network model")
    local.add_argument("--density-kg-m3",type=float,required=True)
    local.add_argument("--reference-room-id",required=True)
    local.add_argument("--factors",type=float,nargs="+",default=[.5,1.,2.])
    local.add_argument("--output",required=True,help="New replay-validated JSON report")
    multi_run=sub.add_parser("multizone-run",help="Opt-in blockMesh/checkMesh/simpleFoam for the connected case")
    multi_run.add_argument("directory")
    multi_run.add_argument("--timeout-seconds", type=int, default=3600)
    multi_results=sub.add_parser("multizone-analyze",help="Read recorded p/U/phi and export measured room/door diagnostics")
    multi_results.add_argument("directory")
    multi_results.add_argument("--density-kg-m3",required=True,type=float)
    multi_results.add_argument("--reference-room-id",required=True)
    multi_results.add_argument("--vertical-tolerance-m-s",type=float,default=.01)
    multi_results.add_argument("--time",dest="time_name")
    multi_results.add_argument("--report-directory",help="New report folder containing JSON, cell/residual CSV and HTML")
    importer=sub.add_parser("import-vtk",help="Import real VTK cell data to existing study")
    for cfg in (1,2,3):
        importer.add_argument(f"--case-{cfg}",required=True)
    importer.add_argument("study")
    importer.add_argument("--solver-name",required=True)
    importer.add_argument("--contaminant-array",default="T")
    importer.add_argument("--output",required=True)
    plot=sub.add_parser("plot",help="3-panel sampled-cell cross-section PNG")
    for cfg in (1,2,3): plot.add_argument(f"--case-{cfg}",required=True)
    plot.add_argument("--field",choices=("speed","contaminant"),default="speed")
    plot.add_argument("--axis",choices=("x","y","z"),required=True)
    plot.add_argument("--position-m",type=float,required=True)
    plot.add_argument("--slab-thickness-m",type=float,required=True)
    plot.add_argument("--output",required=True)
    scalar=sub.add_parser("scalar-prepare",help="Prepare independent OpenFOAM v10 point-source tracer case")
    scalar.add_argument("flow_case",help="Finished airflow case containing nonzero-time U and polyMesh")
    scalar.add_argument("spec",help="Dimensionless passive tracer specification JSON")
    scalar.add_argument("output_directory")
    scalar_runner=sub.add_parser("scalar-run",help="Run external scalarTransportFoam")
    scalar_runner.add_argument("directory")
    scalar_runner.add_argument("--timeout-seconds",type=int,default=3600)
    audit=sub.add_parser("audit-log",help="Apply explicitly supplied numerical residual criteria")
    audit.add_argument("log")
    audit.add_argument("--fields",required=True,nargs="+")
    audit.add_argument("--max-initial-residual",required=True,type=float)
    audit.add_argument("--max-final-residual",required=True,type=float)
    audit.add_argument("--max-global-continuity",type=float)
    audit.add_argument("--window",type=int,default=3)
    audit.add_argument("--output")
    audit.add_argument("--interactive-html", help="Self-contained interactive plot of actual bounded solver residuals")
    grid=sub.add_parser("grid-generate",help="Generate nine OpenFOAM cases: three configurations x three mesh resolutions")
    grid.add_argument("spec")
    grid.add_argument("directory")
    verify_grid=sub.add_parser("grid-audit",help="VTK/log grounded three-grid Richardson and GCI screening")
    verify_grid.add_argument("spec")
    verify_grid.add_argument("--output")
    return parser

@cli_error_boundary("cleanroomx-cfd-pipeline")
def main():
    args=build_parser().parse_args()
    if args.command=="generate":
        result=export_openfoam_cases(load_cli_input(load_strict_json,args.spec),args.directory)
        print(dumps_strict_json(result))
        return 0
    if args.command=="run":
        result=run_openfoam_cases(args.directory,timeout_seconds=args.timeout_seconds)
        print(dumps_strict_json(result))
        return 0 if result["status"]=="executed_requires_convergence_review" else 2
    if args.command=="project-rooms-generate":
        result=generate_project_room_cases(
            args.project, args.directory,
            mesh_cells=tuple(args.mesh_cells),
            kinematic_viscosity_m2_s=args.kinematic_viscosity_m2_s,
            max_iterations=args.max_iterations,
            output_interval=args.output_interval,
        )
        print(dumps_strict_json(result))
        return 0
    if args.command=="project-rooms-run":
        result=run_project_room_cases(
            args.directory, timeout_seconds=args.timeout_seconds,
        )
        print(dumps_strict_json(result))
        return 0 if result["status"]=="executed_requires_convergence_review" else 2
    if args.command=="multizone-generate":
        result=generate_multizone_open_door_case(
            args.project, args.directory, door_mode=args.door_mode,
            cell_size_x_m=args.cell_size_x_m,
            cell_size_y_m=args.cell_size_y_m,
            cell_size_z_m=args.cell_size_z_m,
            kinematic_viscosity_m2_s=args.kinematic_viscosity_m2_s,
            max_iterations=args.max_iterations,
            output_interval=args.output_interval,
            pressure_relaxation=args.pressure_relaxation,
            velocity_relaxation=args.velocity_relaxation,
        )
        print(dumps_strict_json(result))
        return 0
    if args.command=="multizone-compare-relaxation":
        result=compare_independent_relaxation_cases(
            args.baseline_directory,args.variant_directory,
            density_kg_m3=args.density_kg_m3,
            reference_room_id=args.reference_room_id)
        if args.output:
            export_independent_relaxation_comparison(result,args.output)
        print(dumps_strict_json(result))
        return 0
    if args.command=="multizone-leakage-local":
        from .cfd_closed_door_comparison import load_closed_door_network_scenario
        from .cfd_closed_door_single_path import (
            sweep_individual_leakage_sensitivity,export_individual_leakage_sensitivity)
        report=analyze_multizone_case(
            args.case_directory,density_kg_m3=args.density_kg_m3,
            reference_room_id=args.reference_room_id)
        network,evidence,sha=load_closed_door_network_scenario(args.scenario)
        comparison=sweep_individual_leakage_sensitivity(
            report,network,evidence,factors=args.factors,scenario_sha256=sha)
        export_individual_leakage_sensitivity(comparison,args.output)
        print(dumps_strict_json({
            "schema":comparison["schema"],
            "engineering_release":"HOLD",
            "source_closed_input_sha256":sha,
            "path_count":len(comparison["path_experiments"]),
            "factor_count":len(comparison["factors"]),
            "highest_sampled_margin_loss_path":(
                comparison["sampled_path_rankings"]["ranked_paths"][0]["path"]),
            "highest_sampled_margin_loss_pa":(
                comparison["sampled_path_rankings"]["ranked_paths"][0][
                    "max_sampled_target_margin_loss_pa"]),
            "output":str(args.output),
        }))
        return 0
    if args.command=="multizone-run":
        result=run_multizone_open_door_case(args.directory,timeout_seconds=args.timeout_seconds)
        print(dumps_strict_json(result))
        return 0 if result["status"]=="executed_requires_convergence_review" else 2
    if args.command=="multizone-analyze":
        result=analyze_multizone_case(
            args.directory,density_kg_m3=args.density_kg_m3,
            reference_room_id=args.reference_room_id,
            vertical_tolerance_m_s=args.vertical_tolerance_m_s,time_name=args.time_name,
        )
        if args.report_directory:
            export_multizone_report(result,args.report_directory)
        print(dumps_strict_json({k:v for k,v in result.items() if k not in ("cells","residual_history")}))
        return 0
    if args.command=="project-rooms-audit":
        result=audit_project_room_cases(
            args.directory, fields=args.fields,
            max_initial_residual=args.max_initial_residual,
            max_final_residual=args.max_final_residual,
            max_global_continuity=args.max_global_continuity,
            window=args.window,
        )
        print(dumps_strict_json(result))
        return 0 if result["status"]=="numerically_screened_requires_engineering_review" else 3
    if args.command=="grid-generate":
        report=generate_grid_family(load_cli_input(load_strict_json,args.spec),args.directory)
        print(dumps_strict_json(report))
        return 0
    if args.command=="grid-audit":
        spec=load_cli_input(load_strict_json,args.spec)
        validate_grid_spec(spec)
        base=Path(args.spec).resolve().parent
        report=analyze_vtk_grid_study(spec,base_directory=base)
        payload=dumps_strict_json(report)
        if args.output:
            protected=(args.spec,)+tuple(
                str(base/run[key]) for run in spec["runs"]
                for key in ("vtk_file","solver_log")
            )
            if not publish_cli_output("cleanroomx-cfd-pipeline",args.output,payload,
                                      protected_inputs=protected):
                return 1
        else:
            print(payload)
        return 0 if report["status"]=="eligible_for_engineering_review" else 3
    if args.command=="scalar-prepare":
        result=prepare_scalar_case(args.flow_case,load_cli_input(load_strict_json,args.spec),
                                   args.output_directory)
        print(dumps_strict_json(result))
        return 0
    if args.command=="scalar-run":
        result=run_scalar_case(args.directory,timeout_seconds=args.timeout_seconds)
        print(dumps_strict_json(result))
        return 0 if result["status"]=="executed_requires_residual_and_field_validation" else 2
    if args.command=="audit-log":
        if (args.output and args.interactive_html and
            Path(args.output).resolve() == Path(args.interactive_html).resolve()):
            raise ValueError("JSON and interactive HTML outputs must have different paths")
        result=audit_openfoam_log(args.log,fields=args.fields,
                  max_initial_residual=args.max_initial_residual,
                  max_final_residual=args.max_final_residual,
                  max_global_continuity=args.max_global_continuity,
                  window=args.window,include_plot_series=bool(args.interactive_html))
        dashboard=(render_residual_dashboard(result) if args.interactive_html else None)
        payload=dumps_strict_json(result)
        if args.interactive_html:
            if not publish_cli_output("cleanroomx-cfd-pipeline",args.interactive_html,
                                      dashboard,protected_inputs=(args.log,)+
                                      ((args.output,) if args.output else ())):
                return 1
        if args.output:
            if not publish_cli_output("cleanroomx-cfd-pipeline",args.output,payload,
                                      protected_inputs=(args.log,)+
                                      ((args.interactive_html,) if args.interactive_html else ())):
                return 1
        else:
            print(payload)
        return 0 if result["status"]=="numerically_screened" else 3
    files={i:getattr(args,f"case_{i}") for i in (1,2,3)}
    if args.command=="plot":
        result=render_cfd_cross_section(files,args.output,axis=args.axis,
                 position_m=args.position_m,slab_thickness_m=args.slab_thickness_m,field=args.field)
        print(dumps_strict_json(result))
        return 0
    result=populate_study_from_vtk(load_cli_input(load_strict_json,args.study),files,
                                    solver_name=args.solver_name,contaminant_array=args.contaminant_array)
    if not publish_cli_output("cleanroomx-cfd-pipeline",args.output,
                              dumps_strict_json(result),protected_inputs=(args.study,*files.values())):
        return 1
    return 0 if result["analysis"]["comparison_status"]=="comparable" else 3

if __name__=="__main__":
    sys.exit(main())
