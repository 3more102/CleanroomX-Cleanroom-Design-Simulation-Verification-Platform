"""Run and synchronize an actual Foundation v10 passive-tracer case."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys

from cleanroomx.cfd_openfoam import _foundation_v10_banner
from cleanroomx.cfd_openfoam_runtime_sync import (
    OpenFOAMResultSynchronizer,
    hash_case_configuration,
)
from cleanroomx.cfd_scalar import prepare_scalar_case, run_scalar_case


def _write_json(path: Path, document: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    family = Path(sys.argv[1]).resolve(strict=True)
    output = Path(sys.argv[2]).resolve(strict=False)
    spec_path = Path(sys.argv[3]).resolve(strict=True)
    field_map_path = Path(sys.argv[4]).resolve(strict=True)
    if output.exists():
        raise SystemExit("Refusing to overwrite scalar synchronization evidence")
    if os.environ.get("WM_PROJECT") != "OpenFOAM" or os.environ.get("WM_PROJECT_VERSION") != "10":
        raise SystemExit("Expected OpenFOAM Foundation v10")

    base_receipt = json.loads((family / "grid_execution_evidence.json").read_text(encoding="utf-8"))
    family_manifest = json.loads((family / "manifest.json").read_text(encoding="utf-8"))
    build = base_receipt.get("solver_build")
    if not isinstance(build, str) or not build:
        raise SystemExit("Base airflow run has no OpenFOAM build identity")
    source_case = family / "configuration_1" / "coarse"
    expected_cells = family_manifest["case_inputs"]["configuration_1/coarse"]["mesh_cells"]
    if type(expected_cells) is not int or expected_cells <= 0:
        raise SystemExit("Base airflow mesh cell count is missing or invalid")
    scalar_spec = json.loads(spec_path.read_text(encoding="utf-8"))
    field_map = json.loads(field_map_path.read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=False)
    scalar_case = output / "case"
    input_manifest = prepare_scalar_case(source_case, scalar_spec, scalar_case)
    configuration_hash = hash_case_configuration(scalar_case)
    simulation_id = "scalar-" + configuration_hash[:24]
    sync_directory = output / "synchronized"
    synchronizer = OpenFOAMResultSynchronizer(
        scalar_case,
        sync_directory,
        simulation_id=simulation_id,
        case_id="configuration_1/coarse/normalized_tracer",
        configuration_hash=configuration_hash,
        expected_build=build,
        poll_interval_seconds=0.25,
        settle_polls=2,
        timeout_seconds=600,
        required_fields=("U", "T"),
        optional_fields=(),
        field_map=field_map,
    )
    solver_report = run_scalar_case(
        scalar_case,
        timeout_seconds=600,
        synchronizer=synchronizer,
    )
    if solver_report.get("status") != "executed_requires_residual_and_field_validation":
        raise SystemExit("scalarTransportFoam execution or synchronization failed")
    sync_report = solver_report.get("result_synchronization")
    if not isinstance(sync_report, dict) or sync_report.get("status") != "results_synced":
        raise SystemExit("Scalar solver did not finish with synchronized outputs")

    solver_log = scalar_case / "scalarTransportFoam.log"
    log_bytes = solver_log.read_bytes()
    banner = _foundation_v10_banner(log_bytes.decode("utf-8", errors="replace"))
    if not banner.get("is_foundation_v10") or banner.get("build") != build:
        raise SystemExit("Scalar solver build differs from the Foundation v10 airflow run")
    sync_manifest_path = sync_directory / "sync_manifest.json"
    sync_manifest_bytes = sync_manifest_path.read_bytes()
    sync_manifest = json.loads(sync_manifest_bytes.decode("utf-8"))
    if (
        sync_manifest.get("status") != "results_synced"
        or sync_manifest.get("scientific_validation") != "BLOCKED"
        or sync_manifest.get("required_fields") != ["U", "T"]
        or sync_manifest.get("optional_fields") != []
        or sync_manifest.get("field_map") != field_map
        or sync_manifest.get("solver_build") != build
    ):
        raise SystemExit("Scalar synchronization manifest metadata is incomplete")

    expected_times = set()
    for entry in scalar_case.iterdir():
        if (
            not entry.is_dir()
            or re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d+)?", entry.name) is None
            or float(entry.name) <= 0
        ):
            continue
        if (entry / "U").is_file() and (entry / "T").is_file():
            expected_times.add(entry.name)
    records = sync_manifest.get("records")
    if not isinstance(records, dict) or set(records) != expected_times or not records:
        raise SystemExit("Not every completed scalarTransportFoam output time was synchronized")
    for time_name, record in records.items():
        if (
            record.get("status") != "imported"
            or record.get("scientific_validation") != "BLOCKED"
            or record.get("fields", {}).get("T", {}).get("dimensions") != "[0 0 0 0 0 0 0]"
            or record.get("fields", {}).get("U", {}).get("units") != "m/s"
            or record.get("native_vtk_parity", {}).get("U", {}).get("status") != "PASS"
            or record.get("native_vtk_parity", {}).get("T", {}).get("status") != "PASS"
            or "p" in record.get("fields", {})
            or record.get("cleanroomx_analysis_import", {}).get("field_data_names") != ["normalized_tracer"]
            or record.get("cleanroomx_analysis_import", {}).get("has_temperature_field") is not False
        ):
            raise SystemExit("Scalar field mapping or native-to-VTK validation failed at " + time_name)
        if record.get("cell_count") != expected_cells:
            raise SystemExit("Scalar VTK import did not preserve the source mesh cell count")

    evidence = {
        "schema_version": "cleanroomx.openfoam-scalar-sync-evidence.v1",
        "status": "PASS_EXECUTION_AND_FIELD_SYNC_DIAGNOSTIC_ONLY",
        "solver_release": "OpenFOAM Foundation v10",
        "solver_build": build,
        "source_flow_case": "configuration_1/coarse",
        "source_velocity_sha256": input_manifest["source_velocity_sha256"],
        "scalar_spec_sha256": input_manifest["scalar_spec_sha256"],
        "input_manifest_sha256": solver_report["input_manifest_sha256"],
        "solver_log_sha256": hashlib.sha256(log_bytes).hexdigest(),
        "simulation_id": simulation_id,
        "configuration_hash": configuration_hash,
        "synchronization_manifest_sha256": hashlib.sha256(sync_manifest_bytes).hexdigest(),
        "synchronized_times": sorted(records, key=lambda name: float(name)),
        "synchronized_record_count": len(records),
        "mesh_cells_per_snapshot": expected_cells,
        "fields": {
            "U": {"units": "m/s", "native_vtk_parity": "PASS"},
            "T": {
                "dimensions": "[0 0 0 0 0 0 0]",
                "semantic": "normalized_tracer",
                "units": "1",
                "native_vtk_parity": "PASS",
            },
        },
        "residual_acceptance": "not_assessed",
        "scientific_validation": "BLOCKED",
        "limitations": [
            "Synthetic geometry and source inputs",
            "Dimensionless normalized tracer is not measured contaminant concentration",
            "Solver execution and field parity do not establish physical validity or cleanroom qualification",
        ],
    }
    _write_json(output / "scalar_sync_evidence.json", evidence)
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
