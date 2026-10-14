"""Build and score a traceable OpenFOAM Foundation v14 capability matrix.

The score is deliberately conservative: only rows marked ``complete`` with a
CleanroomX implementation path and passing evidence count as complete. This
module does not execute OpenFOAM or infer solver/physical validation from CI.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


RELEASE = "OpenFOAM Foundation v14"
RELEASE_TAG = "version-14"
RELEASE_COMMIT = "b4f91ad8bbbab628441562fc419f040cc4796f11"
REPOSITORY = "OpenFOAM/OpenFOAM-14"
RELEASE_ROOT = f"https://github.com/{REPOSITORY}/tree/{RELEASE_TAG}"
GUIDE_PDF = f"https://github.com/{REPOSITORY}/blob/{RELEASE_TAG}/doc/Guides/OpenFOAMUserGuide-A4.pdf"
ISSUE_URL = "https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/issues/1296"
STATUSES = {"complete", "partial", "unsupported", "not_tested", "blocked", "not_applicable"}
METRICS = ("native", "integration", "workflow")
FIELDS = (
    "capability_id", "category", "capability", "inventory_source", "upstream_reference",
    "native_scope", "native_status", "native_implementation", "native_test_evidence", "native_gap",
    "integration_scope", "integration_status", "integration_path", "integration_test_evidence", "integration_gap",
    "workflow_scope", "workflow_status", "workflow_path", "workflow_test_evidence", "workflow_gap",
)


def _scope(value: str) -> bool:
    if value not in {"true", "false"}:
        raise ValueError(f"scope values must be 'true' or 'false', got {value!r}")
    return value == "true"


def validate_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Validate row identity, scopes, statuses, and evidence for completed rows."""
    result = list(rows)
    seen: set[str] = set()
    for row_number, row in enumerate(result, 2):
        missing = [field for field in FIELDS if field not in row]
        if missing:
            raise ValueError(f"row {row_number}: missing columns {missing}")
        capability_id = row["capability_id"].strip()
        if not capability_id:
            raise ValueError(f"row {row_number}: capability_id is empty")
        if capability_id in seen:
            raise ValueError(f"row {row_number}: duplicate capability_id {capability_id!r}")
        seen.add(capability_id)
        if not row["capability"].strip() or not row["upstream_reference"].strip():
            raise ValueError(f"row {row_number}: capability and upstream reference are required")
        for metric in METRICS:
            in_scope = _scope(row[f"{metric}_scope"])
            status = row[f"{metric}_status"]
            if status not in STATUSES:
                raise ValueError(f"row {row_number}: invalid {metric} status {status!r}")
            if in_scope and status == "not_applicable":
                raise ValueError(f"row {row_number}: in-scope {metric} row is not_applicable")
            if not in_scope and status != "not_applicable":
                raise ValueError(f"row {row_number}: out-of-scope {metric} row must be not_applicable")
            if in_scope and status == "complete":
                path_field = "workflow_path" if metric == "workflow" else f"{metric}_implementation" if metric == "native" else "integration_path"
                evidence = row[f"{metric}_test_evidence"].strip()
                if not row[path_field].strip() or not evidence or evidence.lower() in {"none", "n/a", "not available"}:
                    raise ValueError(f"row {row_number}: complete {metric} row needs an implementation path and passing evidence")
                if not evidence.casefold().startswith("pass:"):
                    raise ValueError(f"row {row_number}: complete {metric} evidence must start with 'PASS:'")
                if metric in {"integration", "workflow"} and any(
                    marker in evidence.casefold()
                    for marker in ("synthetic", "mock", "fixture", "simulated", "generated only", "not tested")
                ):
                    raise ValueError(f"row {row_number}: synthetic or mocked evidence cannot complete {metric} coverage")
    return result


def read_matrix(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError(f"matrix header must exactly match: {','.join(FIELDS)}")
        return validate_rows(reader)


def score_rows(rows: Iterable[dict[str, str]]) -> dict:
    """Return exact complete/denominator scores overall and by category."""
    rows = validate_rows(rows)
    output: dict[str, dict] = {}
    for metric in METRICS:
        included = [row for row in rows if _scope(row[f"{metric}_scope"])]
        completed = [row for row in included if row[f"{metric}_status"] == "complete"]
        category_data: dict[str, dict[str, int]] = defaultdict(lambda: {"complete": 0, "denominator": 0})
        for row in included:
            bucket = category_data[row["category"]]
            bucket["denominator"] += 1
            if row[f"{metric}_status"] == "complete":
                bucket["complete"] += 1
        output[metric] = {
            "complete": len(completed),
            "denominator": len(included),
            "percent": (100.0 * len(completed) / len(included)) if included else None,
            "categories": dict(sorted(category_data.items())),
        }
    output["catalog"] = {
        "rows": len(rows),
        "status_counts": {
            metric: dict(Counter(row[f"{metric}_status"] for row in rows if _scope(row[f"{metric}_scope"])))
            for metric in METRICS
        },
    }
    return output


def _category_for_guide(section: str) -> str:
    chapter = section.split(".", 1)[0]
    return {
        "2": "tutorial_documentation",
        "3": "applications_and_apis",
        "4": "case_setup_and_numerics",
        "5": "mesh",
        "6": "fields_and_boundary_conditions",
        "7": "postprocessing",
        "8": "physical_models",
    }.get(chapter, "guide_overview")


def _guide_native_scope(section: str) -> bool:
    if section.startswith(("4.", "5.", "6.", "8.")):
        return True
    if section == "3" or section.startswith(("3.1", "3.2", "3.3", "3.4", "3.5", "3.6")):
        return True
    return False


def _guide_rows(source_root: Path) -> list[dict[str, str]]:
    pdf = source_root / "doc/Guides/OpenFOAMUserGuide-A4.pdf"
    pdftotext = shutil.which("pdftotext")
    if not pdf.is_file() or not pdftotext:
        raise ValueError("matrix generation needs the tagged v14 User Guide PDF and pdftotext (Poppler)")
    text = subprocess.check_output([pdftotext, "-layout", "-f", "9", "-l", "16", str(pdf), "-"], text=True)
    pattern = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+(.*?)\s+U-(\d+)\s*$")
    rows = []
    for line in text.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        section, title, page = match.groups()
        # The PDF uses dot-and-space leaders, not a contiguous dotted string.
        title = re.sub(r"(?:\s*\.\s*){3,}$", "", title).strip()
        if not title:
            continue
        category = _category_for_guide(section)
        in_scope = section != "1"
        native_scope = in_scope and _guide_native_scope(section)
        rows.append(_row(
            capability_id=f"guide/{section}", category=category,
            capability=f"User Guide §{section}: {title}", inventory_source="OpenFOAM v14 User Guide table of contents",
            upstream_reference=f"{GUIDE_PDF}#page={page}", native_scope=native_scope,
            integration_scope=in_scope,
            integration_status=_guide_integration_status(section) if in_scope else "not_applicable",
        ))
    if len(rows) != 288 or len({row["capability_id"] for row in rows}) != len(rows):
        raise ValueError(f"expected 288 unique numbered User Guide entries, parsed {len(rows)}")
    return rows


def _guide_integration_status(section: str) -> str:
    # Partial means some v10-era CleanroomX case generation or import code maps
    # to the topic. It never means v14 execution or scientific validation.
    if section.startswith(("3.3", "3.5", "3.6", "4.1", "4.3", "4.4", "4.5", "4.6", "5.4", "6.3", "6.4", "7.3", "7.4", "8.1")):
        return "partial"
    return "unsupported"


def _row(*, capability_id: str, category: str, capability: str, inventory_source: str,
         upstream_reference: str, native_scope: bool = False, integration_scope: bool = False,
         workflow_scope: bool = False, native_status: str | None = None,
         integration_status: str | None = None, workflow_status: str | None = None,
         native_implementation: str = "none", native_test_evidence: str = "none",
         native_gap: str = "No native finite-volume CFD solver implementation in CleanroomX.",
         integration_path: str = "none", integration_test_evidence: str = "none",
         integration_gap: str = "No OpenFOAM v14 end-to-end integration evidence.",
         workflow_path: str = "none", workflow_test_evidence: str = "none",
         workflow_gap: str = "Required real-run or independent physical evidence is absent.") -> dict[str, str]:
    native_status = native_status or ("unsupported" if native_scope else "not_applicable")
    integration_status = integration_status or ("unsupported" if integration_scope else "not_applicable")
    workflow_status = workflow_status or ("blocked" if workflow_scope else "not_applicable")
    return {
        "capability_id": capability_id,
        "category": category,
        "capability": capability,
        "inventory_source": inventory_source,
        "upstream_reference": upstream_reference,
        "native_scope": str(native_scope).lower(),
        "native_status": native_status,
        "native_implementation": native_implementation if native_scope else "not in this score",
        "native_test_evidence": native_test_evidence if native_scope else "not in this score",
        "native_gap": native_gap if native_scope else "not in this score",
        "integration_scope": str(integration_scope).lower(),
        "integration_status": integration_status,
        "integration_path": integration_path if integration_scope else "not in this score",
        "integration_test_evidence": integration_test_evidence if integration_scope else "not in this score",
        "integration_gap": integration_gap if integration_scope else "not in this score",
        "workflow_scope": str(workflow_scope).lower(),
        "workflow_status": workflow_status,
        "workflow_path": workflow_path if workflow_scope else "not in this score",
        "workflow_test_evidence": workflow_test_evidence if workflow_scope else "not in this score",
        "workflow_gap": workflow_gap if workflow_scope else "not in this score",
    }


def _cleanroom_evidence(row_id: str) -> dict[str, str]:
    common_path = "src/cleanroomx/cfd_openfoam.py; src/cleanroomx/cfd_grid_family.py"
    if row_id.startswith("run/"):
        config, grid = row_id.split("/")[1:]
        return dict(category="real_solver_runs", capability=f"Real OpenFOAM Foundation v10 run: {config}, {grid} grid",
                    status="blocked", path=common_path, evidence="tests/test_cfd_grid_study.py::test_generate_nine_openfoam_cases_reproducibly (synthetic generation only)",
                    gap="No OpenFOAM executable is installed here and no solver run evidence exists for this case.")
    if row_id == "provenance/manifest":
        return dict(category="run_provenance", capability="Immutable run manifest with commands, environment, input/output hashes and exit codes",
                    status="partial", path="src/cleanroomx/cfd_openfoam.py; generated input SHA-256 manifest and local run_manifest.json",
                    evidence="tests/test_cfd_pipeline.py (mocked/synthetic; no immutable real-run evidence)",
                    gap="No immutable real OpenFOAM execution bundle or published nine-case run manifest.")
    if row_id.startswith("audit/"):
        config = row_id.split("/")[1]
        return dict(category="grid_convergence", capability=f"Three-grid GCI audit for ventilation configuration {config}",
                    status="partial", path="src/cleanroomx/cfd_grid_study.py; cleanroomx-cfd-pipeline grid-audit",
                    evidence="tests/test_cfd_grid_study.py (synthetic grids; no real v10 solve)",
                    gap="No per-family audit based on nine actual solver outputs.")
    if row_id == "physics/model-review":
        return dict(category="physics_model_review", capability="Independent review of turbulence, transport, source terms, filtration, deposition and boundary assumptions",
                    status="blocked", path="docs/CFD_OPENFOAM_PIPELINE.md (limitations documented)", evidence="none",
                    gap="Model assumptions are laminar and simplified; independent cleanroom CFD review has not been completed.")
    if row_id == "measurement/correlation":
        return dict(category="measured_validation", capability="Correlation and uncertainty analysis against independent cleanroom measurements",
                    status="blocked", path="none", evidence="none",
                    gap="No aligned independent flow, pressure/ACH or particle measurements were supplied.")
    if row_id == "evidence/proofgraph":
        return dict(category="evidence_integration", capability="Run manifests, hashes, checks and verdicts linked in ProofGraph/dossier",
                    status="blocked", path="none", evidence="none",
                    gap="CFD run evidence is not integrated into an engineering ProofGraph/dossier verdict.")
    raise ValueError(f"unknown cleanroom workflow row {row_id}")


def _current_integration_assessment(source_type: str, capability_id: str, name: str) -> tuple[str, str, str, str]:
    if source_type == "solver_binary" and name == "foamRun":
        return ("partial", "src/cleanroomx/cfd_openfoam.py::build_openfoam_files and run_openfoam_cases (v14 modular case path)", "tests/test_cfd_pipeline.py (generated-dictionary and mocked-command checks only)", "No real OpenFOAM v14 case execution or solver-output evidence is available.")
    if source_type == "solver_module" and name == "incompressibleFluid":
        return ("partial", "src/cleanroomx/cfd_openfoam.py emits solver incompressibleFluid in the v14 controlDict", "tests/test_cfd_pipeline.py (synthetic case generation; mocked solver command)", "No real v14 solver run, convergence review or physical validation.")
    if source_type == "utility_binary" and name in {"blockMesh", "checkMesh"}:
        return ("partial", "src/cleanroomx/cfd_openfoam.py::build_openfoam_files and run_openfoam_cases (v10/v14 cases)", "tests/test_cfd_pipeline.py (mocked commands and release checks; no v14 execution)", "No real v14 mesh generation or mesh-quality command run is available.")
    if source_type == "guide_section" and capability_id.startswith(("guide/3.3", "guide/3.5", "guide/3.6", "guide/4.1", "guide/4.3", "guide/4.4", "guide/4.5", "guide/4.6", "guide/5.4", "guide/6.3", "guide/6.4", "guide/7.3", "guide/7.4", "guide/8.1")):
        return ("partial", "src/cleanroomx/cfd_openfoam.py; src/cleanroomx/cfd_vtk.py; src/cleanroomx/cfd_grid_study.py", "tests/test_cfd_pipeline.py; tests/test_cfd_grid_study.py (synthetic/mocked)", "Only a narrow v10/v14 case-generation and field-import subset exists; no real v14 solver output or complete feature coverage.")
    return ("unsupported", "none", "none", "No implementation path with passing OpenFOAM v14 integration evidence.")


def build_matrix(source_root: Path) -> list[dict[str, str]]:
    """Build a source-derived baseline catalogue and current assessment."""
    source_root = source_root.resolve()
    commit = subprocess.check_output(["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True).strip()
    if commit != RELEASE_COMMIT:
        raise ValueError(f"OpenFOAM source must be pinned at {RELEASE_TAG} ({RELEASE_COMMIT}), got {commit}")
    tree = subprocess.check_output(["git", "-C", str(source_root), "ls-tree", "-r", "--name-only", RELEASE_COMMIT], text=True).splitlines()
    rows: list[dict[str, str]] = []

    for area, source_type in (("solvers", "solver_binary"), ("utilities", "utility_binary")):
        root = source_root / "applications" / area
        if not root.is_dir():
            raise ValueError(f"missing source inventory directory: {root}")
        for manifest in sorted(root.rglob("Make/files")):
            text = manifest.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r"(?m)^\s*EXE\s*=\s*\$\(FOAM_APPBIN\)/(\S+)\s*$", text):
                name = match.group(1)
                relative = manifest.relative_to(source_root).as_posix()
                native = source_type == "solver_binary"
                category = "solver_applications" if native else _utility_category(relative)
                row_id = f"{source_type}/{name}"
                status, path, evidence, gap = _current_integration_assessment(source_type, row_id, name)
                rows.append(_row(
                    capability_id=row_id, category=category, capability=f"OpenFOAM v14 executable {name}",
                    inventory_source=f"{source_type} target in {relative}",
                    upstream_reference=f"{RELEASE_ROOT}/{relative}", native_scope=native, integration_scope=True,
                    integration_status=status, integration_path=path, integration_test_evidence=evidence,
                    integration_gap=gap,
                ))

    modules = sorted(name for name in subprocess.check_output(
        ["git", "-C", str(source_root), "ls-tree", "-d", "--name-only", f"{RELEASE_COMMIT}:applications/modules"], text=True
    ).splitlines() if not name.startswith("."))
    for name in modules:
        source = f"applications/modules/{name}"
        if name == "incompressibleFluid":
            module_status = "partial"
            module_path = "src/cleanroomx/cfd_openfoam.py emits the incompressibleFluid v14 module selector"
            module_evidence = "tests/test_cfd_pipeline.py (synthetic case generation; mocked solver command)"
            module_gap = "No real OpenFOAM v14 module execution, convergence review or physical validation."
        else:
            module_status = "unsupported"
            module_path = "none"
            module_evidence = "none"
            module_gap = "No CleanroomX v14 modular-solver adapter or module selection/evaluation evidence."
        rows.append(_row(
            capability_id=f"solver_module/{name}", category=_module_category(name),
            capability=f"OpenFOAM v14 solver/module package {name}", inventory_source="applications/modules package",
            upstream_reference=f"{RELEASE_ROOT}/{source}", native_scope=True, integration_scope=True,
            integration_status=module_status, integration_path=module_path,
            integration_test_evidence=module_evidence, integration_gap=module_gap,
        ))

    apis = sorted(name for name in subprocess.check_output(
        ["git", "-C", str(source_root), "ls-tree", "-d", "--name-only", f"{RELEASE_COMMIT}:src"], text=True
    ).splitlines() if not name.startswith("."))
    for package in apis:
        source = f"src/{package}"
        rows.append(_row(
            capability_id=f"api/{package}", category="public_api_libraries",
            capability=f"OpenFOAM v14 source/API family {package}", inventory_source="top-level src library package",
            upstream_reference=f"{RELEASE_ROOT}/{source}", native_scope=True, integration_scope=True,
            integration_status="unsupported", integration_gap="No CleanroomX binding or equivalent OpenFOAM v14 API integration.",
        ))

    tutorials = sorted(p for p in tree if p.startswith("tutorials/") and p.endswith("/Allrun") and p != "tutorials/Allrun")
    for source in tutorials:
        case = source[len("tutorials/"):-len("/Allrun")]
        family = case.split("/", 1)[0]
        rows.append(_row(
            capability_id=f"tutorial/{case}", category="tutorial_workflows",
            capability=f"OpenFOAM v14 tutorial workflow {case}", inventory_source="executable tutorial Allrun script",
            upstream_reference=f"{RELEASE_ROOT}/{source}", integration_scope=True,
            integration_status="unsupported", integration_gap="CleanroomX does not reproduce or execute this OpenFOAM v14 tutorial workflow.",
        ))

    for directory in ("bin", "etc"):
        raw = subprocess.check_output(["git", "-C", str(source_root), "ls-tree", "-r", "-z", RELEASE_COMMIT, directory])
        for entry in raw.decode("utf-8").split("\0"):
            if not entry:
                continue
            metadata, source = entry.split("\t", 1)
            mode, _kind, _oid = metadata.split()
            if mode != "100755":
                continue
            name = Path(source).name
            if directory == "etc":
                category = "case_template_workflows"
                integration_status = "unsupported"
                integration_gap = "CleanroomX does not reproduce or execute this OpenFOAM v14 case-template workflow."
            elif source.startswith("bin/tools/"):
                category = "developer_tools"
                integration_status = "unsupported"
                integration_gap = "No CleanroomX equivalent for this OpenFOAM v14 environment/developer helper."
            else:
                category = "solver_entrypoint_scripts" if name in _LEGACY_SOLVER_ENTRYPOINTS else "case_management_tools"
                integration_status = "unsupported"
                integration_gap = "The v14 case runner selects foamRun directly; this compatibility script is not invoked or tested by CleanroomX."
            rows.append(_row(
                capability_id=f"script/{source}", category=category,
                capability=f"OpenFOAM v14 executable script {name}", inventory_source=f"executable script {source}",
                upstream_reference=f"{RELEASE_ROOT}/{source}", integration_scope=True,
                integration_status=integration_status,
                integration_path="none",
                integration_test_evidence="none",
                integration_gap=integration_gap,
            ))

    rows.extend(_runtime_registration_rows(source_root))
    rows.extend(_guide_rows(source_root))

    # Issue #1296 is the finite cleanroom qualification denominator. Nine real
    # runs, three family audits, and the three remaining evidence gates are
    # counted separately; synthetic tests never satisfy those rows.
    for config in ("central_supply", "distributed_supply", "perforated_floor"):
        for grid in ("coarse", "medium", "fine"):
            row_id = f"run/{config}/{grid}"
            item = _cleanroom_evidence(row_id)
            rows.append(_row(
                capability_id=row_id, category=item["category"], capability=item["capability"],
                inventory_source="CleanroomX issue #1296 acceptance gate", upstream_reference=ISSUE_URL,
                workflow_scope=True, workflow_status=item["status"], workflow_path=item["path"],
                workflow_test_evidence=item["evidence"], workflow_gap=item["gap"],
            ))
    rows.append(_row(
        capability_id="provenance/manifest", **{k: _cleanroom_evidence("provenance/manifest")[k] for k in ("category", "capability")},
        inventory_source="CleanroomX issue #1296 acceptance gate", upstream_reference=ISSUE_URL,
        workflow_scope=True, workflow_status="partial", workflow_path=_cleanroom_evidence("provenance/manifest")["path"],
        workflow_test_evidence=_cleanroom_evidence("provenance/manifest")["evidence"], workflow_gap=_cleanroom_evidence("provenance/manifest")["gap"],
    ))
    for config in ("central_supply", "distributed_supply", "perforated_floor"):
        row_id = f"audit/{config}"
        item = _cleanroom_evidence(row_id)
        rows.append(_row(
            capability_id=row_id, category=item["category"], capability=item["capability"],
            inventory_source="CleanroomX issue #1296 acceptance gate", upstream_reference=ISSUE_URL,
            workflow_scope=True, workflow_status=item["status"], workflow_path=item["path"],
            workflow_test_evidence=item["evidence"], workflow_gap=item["gap"],
        ))
    for row_id in ("physics/model-review", "measurement/correlation", "evidence/proofgraph"):
        item = _cleanroom_evidence(row_id)
        rows.append(_row(
            capability_id=row_id, category=item["category"], capability=item["capability"],
            inventory_source="CleanroomX issue #1296 acceptance gate", upstream_reference=ISSUE_URL,
            workflow_scope=True, workflow_status=item["status"], workflow_path=item["path"],
            workflow_test_evidence=item["evidence"], workflow_gap=item["gap"],
        ))

    rows.sort(key=lambda row: row["capability_id"])
    return validate_rows(rows)


def _utility_category(path: str) -> str:
    parts = Path(path).parts
    group = parts[2] if len(parts) > 2 else "other"
    return {
        "mesh": "mesh_utilities", "parallelProcessing": "parallel_utilities",
        "postProcessing": "postprocessing_utilities", "preProcessing": "preprocessing_utilities",
        "surface": "surface_utilities", "thermophysical": "thermophysical_utilities",
        "miscellaneous": "miscellaneous_utilities", "deprecated": "deprecated_utilities",
        "lagrangian": "particle_utilities", "thermophysical": "thermophysical_utilities",
    }.get(group, "other_utilities")


def _module_category(name: str) -> str:
    if "multiphase" in name.lower() or "vof" in name.lower() or "driftflux" in name.lower():
        return "solver_modules_multiphase"
    if "particle" in name.lower() or "lagrangian" in name.lower():
        return "solver_modules_particles"
    if "solid" in name.lower():
        return "solver_modules_solid"
    if "compressible" in name.lower() or name == "shockFluid":
        return "solver_modules_compressible"
    if "film" in name.lower():
        return "solver_modules_film"
    if name in {"XiFluid"}:
        return "solver_modules_combustion"
    if name in {"incompressibleFluid", "isothermalFluid", "multicomponentFluid"}:
        return "solver_modules_single_phase"
    return "solver_modules_base"


_LEGACY_SOLVER_ENTRYPOINTS = {
    "SRFPimpleFoam", "SRFSimpleFoam", "XiFoam", "buoyantFoam", "buoyantReactingFoam",
    "cavitatingFoam", "chtMultiRegionFoam", "compressibleInterFoam", "compressibleMultiphaseInterFoam",
    "denseParticleFoam", "dnsFoam", "driftFluxFoam", "interFoam", "multiphaseEulerFoam",
    "multiphaseInterFoam", "particleFoam", "pimpleFoam", "pisoFoam", "potentialFreeSurfaceFoam",
    "reactingFoam", "reactingMultiphaseEulerFoam", "reactingTwoPhaseEulerFoam", "rhoCentralFoam",
    "rhoParticleFoam", "rhoPimpleFoam", "rhoSimpleFoam", "simpleFoam", "solidDisplacementFoam",
    "solidEquilibriumDisplacementFoam", "twoPhaseEulerFoam",
}


def _runtime_category(path: str) -> str:
    lower = path.lower()
    if "boundarycondition" in lower or "patchfield" in lower:
        return "runtime_boundary_conditions"
    if "functionobject" in lower or "functionobjects" in lower:
        return "runtime_function_objects"
    if any(token in lower for token in ("fvschemes", "fvsolution", "solver/", "preconditioner", "smoothsolver")):
        return "runtime_numerics"
    if any(token in lower for token in ("momentumtransport", "thermophysical", "radiationmodels", "reactionmodels", "multiphase", "lagrangian", "twophase", "atmosphericmodels", "waves/")):
        return "runtime_physical_models"
    if "/fvmodels/" in lower or "/fvconstraints/" in lower:
        return "runtime_sources_constraints"
    if "/mesh" in lower or "/fvmesh" in lower or "/trisurface" in lower:
        return "runtime_mesh"
    return "runtime_selection_other"


def _runtime_registration_rows(source_root: Path) -> list[dict[str, str]]:
    """Inventory literal runtime-selection registrations in source and apps."""
    pattern = re.compile(r"\b(add\w*ToRunTimeSelectionTable)\s*\((.*?)\)\s*;", re.S)
    rows = []
    for area in ("src", "applications"):
        root = source_root / area
        for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in {".C", ".H", ".I"}):
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            relative = path.relative_to(source_root).as_posix()
            for ordinal, match in enumerate(pattern.finditer(content), 1):
                macro, arguments = match.groups()
                line = content.count("\n", 0, match.start()) + 1
                arguments = re.sub(r"\s+", " ", arguments).strip()
                rows.append(_row(
                    capability_id=f"runtime_registration/{relative}#L{line}:{ordinal}",
                    category=_runtime_category(relative),
                    capability=f"Runtime selection registration `{macro}({arguments})`",
                    inventory_source=f"literal {macro} registration in tagged C++ source",
                    upstream_reference=f"{RELEASE_ROOT}/{relative}#L{line}",
                    native_scope=True, integration_scope=True,
                    integration_status="unsupported",
                    integration_gap="No equivalent CleanroomX OpenFOAM v14 runtime-selection registry or end-to-end model-selection evidence.",
                ))
    return rows


def verify_source_coverage(rows: list[dict[str, str]], source_root: Path) -> dict[str, int]:
    """Check that all source-derived ids match the exact tagged source inventory."""
    expected = build_matrix(source_root)
    expected_ids = {row["capability_id"] for row in expected}
    actual_ids = {row["capability_id"] for row in rows}
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids)
        extra = sorted(actual_ids - expected_ids)
        raise ValueError(f"matrix/source inventory mismatch; missing={missing[:12]}, extra={extra[:12]}")
    counts = Counter(row["inventory_source"].split(" ", 1)[0] for row in expected)
    return dict(sorted(counts.items()))


def write_matrix(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def markdown_summary(scores: dict) -> str:
    labels = {"native": "Native solver capability parity", "integration": "End-to-end OpenFOAM integration", "workflow": "Validated cleanroom engineering workflows"}
    lines = ["| Measure | Complete | In-scope rows | Score |", "|---|---:|---:|---:|"]
    for metric in METRICS:
        value = scores[metric]
        lines.append(f"| {labels[metric]} | {value['complete']} | {value['denominator']} | {value['percent']:.2f}% |")
    lines.extend(["", "| Category | Native | Integration | Cleanroom workflow |", "|---|---:|---:|---:|"])
    categories = sorted({category for metric in METRICS for category in scores[metric]["categories"]})
    for category in categories:
        cells = []
        for metric in METRICS:
            value = scores[metric]["categories"].get(category)
            cells.append(f"{value['complete']}/{value['denominator']}" if value else "—")
        lines.append(f"| {category} | {cells[0]} | {cells[1]} | {cells[2]} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score or regenerate the pinned OpenFOAM Foundation v14 capability matrix")
    parser.add_argument("matrix", nargs="?", type=Path, default=Path("docs/OPENFOAM_V14_CAPABILITY_MATRIX.csv"))
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--generate-openfoam-source", type=Path, help="regenerate from a local OpenFOAM v14 tag checkout")
    parser.add_argument("--verify-source", type=Path, help="verify matrix IDs against the exact tagged OpenFOAM source inventory")
    args = parser.parse_args(argv)
    try:
        if args.generate_openfoam_source:
            rows = build_matrix(args.generate_openfoam_source)
            write_matrix(args.matrix, rows)
        else:
            rows = read_matrix(args.matrix)
        if args.verify_source:
            verify_source_coverage(rows, args.verify_source)
        scores = score_rows(rows)
        if args.format == "json":
            print(json.dumps(scores, indent=2, sort_keys=True))
        else:
            print(markdown_summary(scores), end="")
        return 0
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"openfoam parity matrix: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
