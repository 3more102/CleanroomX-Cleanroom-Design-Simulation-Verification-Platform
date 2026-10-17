"""CLI for reproducible OpenFOAM case generation, execution and VTK studies."""
from __future__ import annotations
import argparse
import sys
from .cfd_openfoam import export_openfoam_cases, run_openfoam_cases
from .cfd_project_handoff import project_room_openfoam_spec
from .cfd_openfoam_timeseries import (
    export_openfoam_time_series_csv,
    read_openfoam_sync_time_series,
)
from .cfd_vtk import populate_study_from_vtk
from .cfd_visualization import render_cfd_cross_section
from .cfd_scalar import prepare_scalar_case, run_scalar_case
from .cfd_audit import audit_openfoam_log
from .cfd_grid_study import analyze_vtk_grid_study, validate_grid_spec
from .cfd_grid_family import generate_grid_family
from .cfd_sync import synchronize_openfoam_vtk_once, watch_openfoam_vtk
from .cfd_openfoam_runtime_sync import (
    DEFAULT_OPTIONAL_FIELDS,
    OpenFOAMResultSynchronizer,
    hash_case_configuration,
)
from .proofgraph_openfoam import (
    build_openfoam_sync_proofgraph,
    openfoam_sync_graph_input_paths,
)
from pathlib import Path
from .cli_output import cli_error_boundary, dumps_strict_json, load_cli_input, publish_cli_output
from .strict_json import load_strict_json
from .project import load_project_document
from .spatial_integrity import SPATIAL_METADATA_KEY

def build_parser():
    parser=argparse.ArgumentParser(prog="cleanroomx-cfd-pipeline",
                                   description="OpenFOAM v10 and VTK cleanroom CFD pipeline")
    sub=parser.add_subparsers(dest="command",required=True)
    create=sub.add_parser("generate",help="Generate three OpenFOAM cases")
    create.add_argument("spec")
    create.add_argument("directory")
    project_spec=sub.add_parser(
        "project-room-spec",
        help="Create a reviewable OpenFOAM spec from one selected CleanroomX room",
    )
    project_spec.add_argument("project",help="CleanroomX project document")
    project_spec.add_argument("template_spec",help="Existing spec for explicit CFD inputs")
    project_spec.add_argument("--room-id",required=True)
    project_spec.add_argument("--output",required=True)
    runner=sub.add_parser("run",help="Opt-in: run blockMesh, checkMesh, simpleFoam")
    runner.add_argument("directory")
    runner.add_argument("--timeout-seconds",type=int,default=3600)
    runner.add_argument("--sync-results",metavar="DIRECTORY",
                        help="Incrementally import stable simpleFoam outputs while it runs")
    runner.add_argument("--simulation-id",help="Stable ID to resume or group synchronized outputs")
    runner.add_argument("--sync-poll-interval-seconds",type=float,default=1.0)
    runner.add_argument("--sync-timeout-seconds",type=int,default=600,
                        help="Maximum time for each foamToVTK snapshot export")
    runner.add_argument("--sync-max-field-mib",type=int,default=256)
    runner.add_argument("--sync-max-snapshot-mib",type=int,default=512)
    runner.add_argument("--sync-max-output-mib",type=int,default=2048)
    runner.add_argument("--sync-max-retries",type=int,default=3)
    importer=sub.add_parser("import-vtk",help="Import real VTK cell data to existing study")
    for cfg in (1,2,3):
        importer.add_argument(f"--case-{cfg}",required=True)
    importer.add_argument("study")
    importer.add_argument("--solver-name",required=True)
    importer.add_argument("--contaminant-array",
                          help="Explicitly identify a scalar VTK array as contaminant concentration")
    importer.add_argument("--temperature-array",
                          help="Explicitly identify a scalar VTK array containing absolute temperature")
    importer.add_argument("--temperature-units",choices=("K",),
                          help="Required with --temperature-array; source values must be kelvin")
    importer.add_argument("--field-map-file",
                          help="Optional JSON map for additional scalar/vector VTK fields")
    importer.add_argument("--output",required=True)
    sync=sub.add_parser("sync-vtk",help="Incrementally import stable OpenFOAM foamToVTK time datasets")
    sync.add_argument("source_directory",help="foamToVTK VTK output root for one simulation")
    sync.add_argument("output_directory",help="Persistent CleanroomX result snapshot store")
    sync.add_argument("--simulation-id",required=True)
    sync.add_argument("--configuration-file",required=True,
                      help="Configuration/manifest file whose raw SHA-256 binds this run")
    sync.add_argument("--field-map-file",
                      help="Optional JSON map that assigns units and meanings to VTK cell arrays")
    sync.add_argument("--contaminant-array",
                      help="Explicitly identify a VTK scalar as contaminant concentration")
    sync.add_argument("--interval-seconds",type=float,default=2.0)
    sync.add_argument("--stable-scans",type=int,default=2)
    sync.add_argument("--stable-seconds",type=float,default=2.0)
    sync.add_argument("--max-files",type=int,default=1000)
    sync.add_argument("--max-file-bytes",type=int,default=256*1024*1024)
    sync.add_argument("--max-total-bytes",type=int,default=2*1024*1024*1024)
    sync.add_argument("--max-record-bytes",type=int,default=128*1024*1024)
    sync.add_argument("--max-scan-entries",type=int,default=100000)
    sync.add_argument("--once",action="store_true",help="Run one scan and exit; repeat to satisfy the stability window")
    sync.add_argument("--quiet-unchanged",action="store_true",
                      help="In watch mode, print only when imported results or scan counts change")
    proofgraph=sub.add_parser(
        "proofgraph-export",
        help="Verify retained OpenFOAM sync snapshots and export a ProofGraph",
    )
    proofgraph.add_argument("result_directory",help="CleanroomX sync-vtk result store")
    proofgraph.add_argument("--output",required=True,help="Output ProofGraph JSON path")
    timeseries=sub.add_parser(
        "timeseries-export",
        help="Audit synchronized snapshots and export one mapped field series as CSV",
    )
    timeseries.add_argument("result_directory",help="CleanroomX synchronized result store")
    timeseries.add_argument("--case-id",required=True)
    timeseries.add_argument("--field",required=True,help="Explicitly mapped field semantic")
    timeseries.add_argument("--output",required=True,help="Output CSV path")
    case_sync=sub.add_parser("sync-case",help="Watch a live Foundation v10 case and import stable native fields")
    case_sync.add_argument("case_directory")
    case_sync.add_argument("output_directory")
    case_sync.add_argument("--simulation-id",help="Stable ID; defaults to a configuration-hash-derived ID")
    case_sync.add_argument("--configuration-hash",help="Reuse a recorded configuration hash")
    case_sync.add_argument("--expected-build",help="Reuse the recorded Foundation v10 build identity")
    case_sync.add_argument("--solver-log",default="simpleFoam.log")
    case_sync.add_argument("--max-runtime-seconds",type=int)
    case_sync.add_argument("--poll-interval-seconds",type=float,default=1.0)
    case_sync.add_argument("--settle-polls",type=int,default=2)
    case_sync.add_argument("--timeout-seconds",type=int,default=600)
    case_sync.add_argument("--max-field-mib",type=int,default=256)
    case_sync.add_argument("--max-snapshot-mib",type=int,default=512)
    case_sync.add_argument("--max-output-mib",type=int,default=2048)
    case_sync.add_argument("--max-retries",type=int,default=3)
    case_sync.add_argument("--optional-fields",nargs="*",default=list(DEFAULT_OPTIONAL_FIELDS))
    case_sync.add_argument("--required-fields",nargs="+",choices=("U","p","T"),default=["U","p"])
    case_sync.add_argument("--contaminant-field")
    case_sync.add_argument("--field-map-file",
                           help="Explicit semantic and unit mapping for additional OpenFOAM fields")
    plot=sub.add_parser("plot",help="3-panel sampled-cell cross-section PNG")
    for cfg in (1,2,3): plot.add_argument(f"--case-{cfg}",required=True)
    plot.add_argument("--field",choices=("speed","temperature","contaminant","scalar"),default="speed")
    plot.add_argument("--array-name",help="Explicit VTK scalar array name for non-speed plots")
    plot.add_argument("--units",help="Explicit source units for non-speed plots (temperature requires K)")
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
    scalar_runner.add_argument("--sync-results",metavar="DIRECTORY",
                               help="Incrementally import stable scalarTransportFoam U/T writes")
    scalar_runner.add_argument("--simulation-id",
                               help="Stable synchronization ID; defaults to the case configuration hash")
    scalar_runner.add_argument("--expected-build",
                               help="Require this OpenFOAM Foundation v10 build identity")
    scalar_runner.add_argument("--sync-poll-interval-seconds",type=float,default=1.0)
    scalar_runner.add_argument("--sync-settle-polls",type=int,default=2)
    scalar_runner.add_argument("--field-map-file",
                               help="Explicit semantic/units mapping for scalar fields such as normalized T")
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
    if args.command=="project-room-spec":
        project=load_project_document(args.project)
        spec=project_room_openfoam_spec(
            load_cli_input(load_strict_json,args.template_spec),
            project_name=project.name,
            spatial_layout=project.metadata.get(SPATIAL_METADATA_KEY),
            selection_kind="room",
            selected_room_id=args.room_id,
        )
        if not publish_cli_output(
            "cleanroomx-cfd-pipeline",
            args.output,
            dumps_strict_json(spec),
            protected_inputs=(args.project,args.template_spec),
        ):
            return 1
        print(dumps_strict_json({
            "status":"reviewable_spec_created",
            "output":str(Path(args.output).expanduser()),
            "room_id":args.room_id,
            "room_m":spec["room_m"],
            "mapping":"rectangular_room_envelope_only",
            "scientific_validation":"BLOCKED",
        }))
        return 0
    if args.command=="run":
        result=run_openfoam_cases(
            args.directory,
            timeout_seconds=args.timeout_seconds,
            sync_results_directory=args.sync_results,
            simulation_id=args.simulation_id,
            sync_poll_interval_seconds=args.sync_poll_interval_seconds,
            sync_timeout_seconds=args.sync_timeout_seconds,
            sync_max_field_bytes=args.sync_max_field_mib*1024*1024,
            sync_max_snapshot_bytes=args.sync_max_snapshot_mib*1024*1024,
            sync_max_output_bytes=args.sync_max_output_mib*1024*1024,
            sync_max_retries=args.sync_max_retries,
        )
        print(dumps_strict_json(result))
        return 0 if result["status"]=="executed_requires_convergence_review" else 2
    if args.command=="sync-vtk":
        options={
            "simulation_id":args.simulation_id,
            "configuration_file":args.configuration_file,
            "field_map":load_cli_input(load_strict_json,args.field_map_file) if args.field_map_file else None,
            "stable_scans":args.stable_scans,
            "stable_seconds":args.stable_seconds,
            "max_files":args.max_files,
            "max_file_bytes":args.max_file_bytes,
            "max_total_bytes":args.max_total_bytes,
            "max_record_bytes":args.max_record_bytes,
            "max_scan_entries":args.max_scan_entries,
            "contaminant_array":args.contaminant_array,
        }
        if args.once:
            report=synchronize_openfoam_vtk_once(args.source_directory,args.output_directory,**options)
            print(dumps_strict_json(report))
            return 0
        last_signature=None
        def emit_scan(report):
            nonlocal last_signature
            imported=tuple(sorted(
                (item.get("relative_path"),item.get("source_sha256"),item.get("status"))
                for item in report.get("imported",[]) if isinstance(item,dict)
            ))
            counts=tuple(sorted(report.get("counts",{}).items()))
            signature=(report.get("discovered_results"),counts,imported)
            if not args.quiet_unchanged or signature!=last_signature:
                print(
                    dumps_strict_json(report, indent=None, separators=(",", ":")),
                    flush=True,
                )
            last_signature=signature
        try:
            watch_openfoam_vtk(
                args.source_directory,args.output_directory,
                interval_seconds=args.interval_seconds,
                on_scan=emit_scan,
                **options,
            )
        except KeyboardInterrupt:
            return 130
        return 0
    if args.command=="proofgraph-export":
        graph=build_openfoam_sync_proofgraph(args.result_directory).to_dict()
        payload=dumps_strict_json(graph)
        if not publish_cli_output(
            "cleanroomx-cfd-pipeline",
            args.output,
            payload,
            protected_inputs=openfoam_sync_graph_input_paths(args.result_directory),
        ):
            return 1
        verdicts={item["requirement_id"]:item["status"] for item in graph["verdicts"]}
        print(dumps_strict_json({
            "status":"proofgraph_exported",
            "output":str(Path(args.output).expanduser()),
            "graph_id":graph["id"],
            "graph_sha256":graph["graph_sha256"],
            "verdicts":verdicts,
            "scientific_validation":"BLOCKED",
        }))
        return 0
    if args.command=="timeseries-export":
        series=read_openfoam_sync_time_series(args.result_directory)
        output=export_openfoam_time_series_csv(
            series,
            args.output,
            case_id=args.case_id,
            field=args.field,
        )
        print(dumps_strict_json({
            "status":"descriptive_time_series_exported",
            "output":str(output),
            "case_id":args.case_id,
            "field":args.field,
            "row_count":sum(
                row["case_id"]==args.case_id and row["field"]==args.field
                for row in series["rows"]
            ),
            "integrity_status":series["integrity_status"],
            "scientific_validation":"BLOCKED",
            "solver_time_units":"not_asserted",
        }))
        return 0
    if args.command=="sync-case":
        case=Path(args.case_directory).resolve(strict=True)
        configuration_hash=args.configuration_hash or hash_case_configuration(case)
        simulation_id=args.simulation_id or f"sync-{case.name}-{configuration_hash[:16]}"
        solver_log=Path(args.solver_log)
        if not solver_log.is_absolute():
            solver_log=case/solver_log
        synchronizer=OpenFOAMResultSynchronizer(
            case,
            args.output_directory,
            simulation_id=simulation_id,
            configuration_hash=configuration_hash,
            expected_build=args.expected_build,
            poll_interval_seconds=args.poll_interval_seconds,
            settle_polls=args.settle_polls,
            timeout_seconds=args.timeout_seconds,
            max_field_bytes=args.max_field_mib*1024*1024,
            max_snapshot_bytes=args.max_snapshot_mib*1024*1024,
            max_output_bytes=args.max_output_mib*1024*1024,
            max_retries=args.max_retries,
            optional_fields=args.optional_fields,
            required_fields=tuple(args.required_fields),
            contaminant_field=args.contaminant_field,
            field_map=load_cli_input(load_strict_json,args.field_map_file) if args.field_map_file else None,
        )
        result=synchronizer.watch(
            solver_log=solver_log,
            max_runtime_seconds=args.max_runtime_seconds,
        )
        print(dumps_strict_json(result))
        return 0 if result["status"]=="outputs_synced_process_status_unknown" else 2
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
        synchronizer=None
        if args.sync_results:
            case=Path(args.directory).resolve(strict=True)
            configuration_hash=hash_case_configuration(case)
            simulation_id=args.simulation_id or f"scalar-{configuration_hash[:24]}"
            field_map=(load_cli_input(load_strict_json,args.field_map_file)
                       if args.field_map_file else None)
            synchronizer=OpenFOAMResultSynchronizer(
                case,
                args.sync_results,
                simulation_id=simulation_id,
                case_id=case.name,
                configuration_hash=configuration_hash,
                expected_build=args.expected_build,
                poll_interval_seconds=args.sync_poll_interval_seconds,
                settle_polls=args.sync_settle_polls,
                timeout_seconds=min(args.timeout_seconds,3600),
                required_fields=("U","T"),
                optional_fields=(),
                field_map=field_map,
            )
        elif (
            args.field_map_file
            or args.simulation_id
            or args.expected_build
            or args.sync_poll_interval_seconds != 1.0
            or args.sync_settle_polls != 2
        ):
            raise ValueError("scalar synchronization options require --sync-results")
        result=run_scalar_case(
            args.directory,timeout_seconds=args.timeout_seconds,synchronizer=synchronizer
        )
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
                 position_m=args.position_m,slab_thickness_m=args.slab_thickness_m,
                 field=args.field,array_name=args.array_name,units=args.units)
        print(dumps_strict_json(result))
        return 0
    result=populate_study_from_vtk(load_cli_input(load_strict_json,args.study),files,
                                    solver_name=args.solver_name,
                                    contaminant_array=args.contaminant_array,
                                    temperature_array=args.temperature_array,
                                    temperature_units=args.temperature_units,
                                    field_map=(load_cli_input(load_strict_json,args.field_map_file)
                                               if args.field_map_file else None))
    if not publish_cli_output("cleanroomx-cfd-pipeline",args.output,
                              dumps_strict_json(result),protected_inputs=(args.study,*files.values())):
        return 1
    return 0 if result["analysis"]["comparison_status"]=="comparable" else 3

if __name__=="__main__":
    sys.exit(main())

