"""OpenFOAM Foundation v10 passive-scalar point-source case preparation.

The existing airflow solver is NOT modified. A separate immutable-input
scalar case copies the *computed* U field and polyMesh from its source case.
This models a DIMENSIONLESS passive tracer, not particles or pathogen fate.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

from .cfd_openfoam import _header, _field

SCHEMA = "cleanroomx.scalar-transport.v1"
MESH_FILES = ("points", "faces", "owner", "neighbour", "boundary")
FLOW_FIELD = "U"
MAX_COPY_BYTES = 256 * 1024 * 1024


def _positive(value, field):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(field + " must be finite and strictly positive")
    return float(value)


def validate_scalar_spec(data):
    if type(data) is not dict or set(data) != {
        "schema_version", "room_m", "source_location_m",
        "source_strength_m3_s", "diffusivity_m2_s",
        "iterations", "write_interval",
    } or data.get("schema_version") != SCHEMA:
        raise ValueError("scalar specification must match " + SCHEMA + " exactly")
    room = data["room_m"]
    source = data["source_location_m"]
    if type(room) is not list or type(source) is not list or len(room) != 3 or len(source) != 3:
        raise ValueError("room_m and source_location_m require three coordinates")
    for axis in range(3):
        length = _positive(room[axis], f"room_m[{axis}]")
        coordinate = source[axis]
        if type(coordinate) not in (int,float) or not math.isfinite(coordinate) or not 0 < coordinate < length:
            raise ValueError(f"source_location_m[{axis}] must lie strictly inside room")
    for name in ("source_strength_m3_s", "diffusivity_m2_s"):
        _positive(data[name], name)
    for name in ("iterations", "write_interval"):
        n=data[name]
        if type(n) is not int or not 1 <= n <= 100_000:
            raise ValueError(name + " must be integer in [1,100000]")
    if data["write_interval"] > data["iterations"]:
        raise ValueError("write_interval cannot exceed iterations")
    return data


def _scalar_files(spec):
    validate_scalar_spec(spec)
    coords=" ".join(f"{v:.12g}" for v in spec["source_location_m"])
    source=f"{spec['source_strength_m3_s']:.12g}"
    diffusivity=f"{spec['diffusivity_m2_s']:.12g}"
    scalar_bcs={
        "inlet":"type fixedValue; value uniform 0;",
        "outlet":"type zeroGradient;",
        "walls":"type zeroGradient;",
    }
    control=f"""application scalarTransportFoam;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime {spec['iterations']};
deltaT 1;
writeControl timeStep;
writeInterval {spec['write_interval']};
writeFormat ascii;
writePrecision 10;
runTimeModifiable no;"""
    schemes="""ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes { default none; div(phi,T) bounded Gauss upwind; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
fluxRequired { default no; }"""
    solution="""solvers
{
    T
    {
        solver smoothSolver;
        smoother symGaussSeidel;
        tolerance 1e-9;
        relTol 0;
    }
}
SIMPLE
{
    nNonOrthogonalCorrectors 0;
    residualControl { T 1e-7; }
}
relaxationFactors
{
    equations { T 0.7; }
}"""
    fvmodels=f"""pointTracer
{{
    type semiImplicitSource;
    selectionMode points;
    points ( ({coords}) );
    volumeMode absolute;
    sources
    {{
        T
        {{
            explicit {source};
            implicit 0;
        }}
    }}
}}"""
    return {
        "0/T": _field("T","[0 0 0 0 0 0 0]","0",scalar_bcs),
        "system/controlDict": _header("dictionary","controlDict",control,"system"),
        "system/fvSchemes": _header("dictionary","fvSchemes",schemes,"system"),
        "system/fvSolution": _header("dictionary","fvSolution",solution,"system"),
        "constant/physicalProperties":_header(
            "dictionary","physicalProperties",
            f"DT [0 2 -1 0 0 0 0] {diffusivity};", "constant"
        ),
        "constant/fvModels": _header("dictionary","fvModels",fvmodels,"constant"),
    }


def _hash_bytes(path: Path):
    with path.open("rb") as file:
        return hashlib.file_digest(file,"sha256").hexdigest()


def _guard_source_file(path: Path, case_root: Path):
    if path.is_symlink() or not path.is_file() or not path.resolve(strict=True).is_relative_to(case_root):
        raise ValueError(f"Unsafe/missing airflow input: {path}")
    if path.stat().st_size > MAX_COPY_BYTES:
        raise ValueError(f"Airflow source exceeds bounded size: {path}")


def _flow_time_directory(root: Path):
    candidates=[]
    for entry in root.iterdir():
        if entry.is_symlink() or not entry.is_dir():
            continue
        if not re.fullmatch(r"(?:0|[1-9]\d*)(?:\.\d+)?", entry.name):
            continue
        value=float(entry.name)
        if not math.isfinite(value):
            continue
        if (entry/FLOW_FIELD).is_file():
            candidates.append((value,entry))
    if not candidates or max(t for t,_ in candidates) <= 0:
        raise ValueError("Computed airflow U field at a nonzero solver time is required")
    candidates.sort(key=lambda x:x[0])
    return candidates[-1][1]


def prepare_scalar_case(flow_directory,scalar_spec,output_directory):
    """Prepare an isolated case from latest CFD velocity and generated mesh.

    Output hashes bind all six scalar configs plus 0/U and the mesh inputs.
    Source location must refer to the same room geometry as the parent flow.
    Callers must independently verify airflow convergence and provenance.
    """
    validate_scalar_spec(scalar_spec)
    flow=Path(flow_directory).resolve(strict=True)
    if not flow.is_dir():
        raise ValueError("Airflow case must be a directory")
    output=Path(output_directory)
    if output.exists(): raise FileExistsError("Refuse to overwrite scalar case")
    if output.resolve(strict=False).is_relative_to(flow):
        raise ValueError("Scalar case cannot be nested in source airflow case")
    velocity_dir=_flow_time_directory(flow)
    mesh=flow/"constant"/"polyMesh"
    inputs=[velocity_dir/"U",*(mesh/name for name in MESH_FILES)]
    for path in inputs:
        _guard_source_file(path,flow)
    combined_size=sum(p.stat().st_size for p in inputs)
    if combined_size>MAX_COPY_BYTES:
        raise ValueError("Flow input snapshot exceeds 256 MiB")
    if b"volVectorField" not in (velocity_dir/"U").read_bytes()[:8192]:
        raise ValueError("Velocity source is not a volVectorField")
    output.mkdir(parents=True,exist_ok=False)
    files=_scalar_files(scalar_spec)
    try:
        for relative,content in files.items():
            dest=output/relative
            dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open("x",encoding="utf-8",newline="\n") as stream:
                stream.write(content)
        dest=output/"0"/"U"
        shutil.copyfile(velocity_dir/"U",dest)
        for name in MESH_FILES:
            target=output/"constant"/"polyMesh"/name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(mesh/name,target)
        if any(_hash_bytes(src)!=_hash_bytes(output/rel) for src,rel in
               [(velocity_dir/"U","0/U"),*((mesh/n,f"constant/polyMesh/{n}") for n in MESH_FILES)]):
            raise ValueError("Copied solver input hash mismatch")
        paths=sorted(list(files)+["0/U"]+[f"constant/polyMesh/{n}" for n in MESH_FILES])
        manifest={
            "schema_version":SCHEMA,
            "source_flow_case":str(flow),
            "source_velocity_time":velocity_dir.name,
            "source_velocity_sha256":_hash_bytes(velocity_dir/"U"),
            "scalar_spec_sha256":hashlib.sha256(
                json.dumps(scalar_spec,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
            ).hexdigest(),
            "files":{p:_hash_bytes(output/p) for p in paths},
            "validation_status":"unvalidated_airflow_scalar_setup_only",
        }
        with (output/"manifest.json").open("x",encoding="utf-8") as stream:
            json.dump(manifest,stream,indent=2,sort_keys=True)
    except BaseException:
        shutil.rmtree(output)
        raise
    return manifest


def _verify_manifest(root:Path):
    import json
    manifest_path=root/"manifest.json"
    if manifest_path.is_symlink(): raise ValueError("Manifest cannot be symlinked")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version")!=SCHEMA or type(manifest.get("files")) is not dict:
        raise ValueError("Not a CleanroomX scalar case")
    files=manifest["files"]
    expected=set(_scalar_files({
        "schema_version":SCHEMA,"room_m":[1,1,1],"source_location_m":[.5,.5,.5],
        "source_strength_m3_s":1,"diffusivity_m2_s":1,"iterations":1,"write_interval":1,
    })) | {"0/U"} | {f"constant/polyMesh/{n}" for n in MESH_FILES}
    if set(files)!=expected: raise ValueError("Scalar manifest is incomplete")
    for rel, digest in files.items():
        path=root/rel
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
            raise ValueError("Unsafe solver input: "+rel)
        if _hash_bytes(path)!=digest: raise ValueError("Scalar input mutated: "+rel)
    return manifest


def run_scalar_case(directory,*,timeout_seconds=3600):
    if type(timeout_seconds) is not int or not 60<=timeout_seconds<=86400:
        raise ValueError("timeout_seconds must be integer [60,86400]")
    root=Path(directory).resolve(strict=True)
    manifest=_verify_manifest(root)
    executable=shutil.which("scalarTransportFoam")
    if not executable: raise RuntimeError("scalarTransportFoam (OpenFOAM Foundation v10) not found")
    log=root/"scalarTransportFoam.log"
    with log.open("x",encoding="utf-8") as out:
        result=subprocess.run([executable],cwd=root,stdout=out,stderr=subprocess.STDOUT,
                              check=False,timeout=timeout_seconds)
    return {
        "status":"executed_requires_residual_and_field_validation" if result.returncode==0 else "solver_failed",
        "exit_code":result.returncode,
        "log_sha256":_hash_bytes(log),
        "input_manifest_sha256":_hash_bytes(root/"manifest.json"),
        "source_velocity_sha256":manifest["source_velocity_sha256"],
        "warning":"Numerical execution does not establish convergence, mixing, particles or certification",
    }
