"""CLI for reproducible OpenFOAM case generation, execution and VTK studies."""
from __future__ import annotations
import argparse
import sys
from .cfd_openfoam import export_openfoam_cases, run_openfoam_cases
from .cfd_vtk import populate_study_from_vtk
from .cfd_visualization import render_cfd_cross_section
from .cfd_scalar import prepare_scalar_case, run_scalar_case
from .cfd_audit import audit_openfoam_log
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
        result=audit_openfoam_log(args.log,fields=args.fields,
                  max_initial_residual=args.max_initial_residual,
                  max_final_residual=args.max_final_residual,
                  max_global_continuity=args.max_global_continuity,window=args.window)
        payload=dumps_strict_json(result)
        if args.output:
            if not publish_cli_output("cleanroomx-cfd-pipeline",args.output,payload,
                                      protected_inputs=(args.log,)):
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
