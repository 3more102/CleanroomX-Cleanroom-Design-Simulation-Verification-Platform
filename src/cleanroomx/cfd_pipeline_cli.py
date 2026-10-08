"""CLI for reproducible OpenFOAM case generation, execution and VTK studies."""
from __future__ import annotations
import argparse
import sys
from .cfd_openfoam import export_openfoam_cases, run_openfoam_cases
from .cfd_vtk import populate_study_from_vtk
from .cfd_visualization import render_cfd_cross_section
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
