"""OpenFOAM Foundation v10/v14 case generation for three cleanroom layouts.

This models steady isothermal laminar flow; it is NOT CFD validation,
ISO certification, particle transport, turbulence or underfloor plenum CFD.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from .cfd_study import CONFIGURATIONS

SCHEMA = "cleanroomx.openfoam.v1"
MAX_CELLS = 20_000

def _number(x, name):
    if type(x) not in (int, float) or not math.isfinite(x) or x <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return float(x)

def validate_openfoam_spec(spec):
    if type(spec) is not dict:
        raise ValueError("specification must be an object")
    keys = {"schema_version","name","room_m","mesh_cells","supply_flow_m3_s",
            "kinematic_viscosity_m2_s","max_iterations","output_interval"}
    if set(spec) != keys or spec.get("schema_version") != SCHEMA:
        raise ValueError(f"expected {SCHEMA} and precisely {sorted(keys)}")
    if type(spec["name"]) is not str or not spec["name"].strip():
        raise ValueError("name must be nonempty")
    room=spec["room_m"]; mesh=spec["mesh_cells"]
    if type(room) is not list or len(room)!=3:
        raise ValueError("room_m must contain three metre dimensions")
    for i,x in enumerate(room): _number(x,f"room_m[{i}]")
    if type(mesh) is not list or len(mesh)!=3 or any(type(x) is not int or x<6 or x>80 for x in mesh):
        raise ValueError("mesh_cells must be three integers in [6,80]")
    if math.prod(mesh)>MAX_CELLS: raise ValueError("Mesh exceeds bounded generation limit")
    for k in ("supply_flow_m3_s","kinematic_viscosity_m2_s"): _number(spec[k], k)
    for k in ("max_iterations","output_interval"):
        if type(spec[k]) is not int or not 1<=spec[k]<=100_000:
            raise ValueError(f"{k} must be an integer in [1,100000]")
    if spec["output_interval"]>spec["max_iterations"]:
        raise ValueError("output_interval cannot exceed max_iterations")
    return spec

def _header(cls,name,body,loc):
    return (f'FoamFile\n{{\n    version 2.0;\n    format ascii;\n'
            f'    class {cls};\n    location "{loc}";\n    object {name};\n}}\n\n{body}\n')

def _idx(i,j,k,nx,ny):
    return (k*(ny+1)+j)*(nx+1)+i

def _layout(nx,ny,nz,config):
    patches={x:[] for x in ("inlet","outlet","walls")}
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                a=_idx(i,j,k,nx,ny); b=_idx(i+1,j,k,nx,ny)
                c=_idx(i+1,j+1,k,nx,ny); d=_idx(i,j+1,k,nx,ny)
                e=_idx(i,j,k+1,nx,ny); f=_idx(i+1,j,k+1,nx,ny)
                g=_idx(i+1,j+1,k+1,nx,ny); h=_idx(i,j+1,k+1,nx,ny)
                boundary=[]
                if k==0: boundary.append(("bottom",(a,d,c,b)))
                if k==nz-1: boundary.append(("top",(e,f,g,h)))
                if i==0: boundary.append(("left",(a,e,h,d)))
                if i==nx-1: boundary.append(("right",(b,c,g,f)))
                if j==0: boundary.append(("front",(a,b,f,e)))
                if j==ny-1: boundary.append(("back",(d,h,g,c)))
                for side,face in boundary:
                    if side=="top":
                        if config==1:
                            supply=nx//3<=i<nx-nx//3 and ny//3<=j<ny-ny//3
                        else:
                            supply=i%2==0 and j%2==0
                        patch="inlet" if supply else "walls"
                    elif config==3 and side=="bottom" and i%2==0 and j%2==0:
                        patch="outlet"
                    elif config in (1,2) and side in ("left","right") and k<max(1,nz//3):
                        patch="outlet"
                    else:
                        patch="walls"
                    patches[patch].append(face)
    if not patches["inlet"] or not patches["outlet"]:
        raise ValueError("Missing required inlet/outlet")
    return patches

def _mesh(spec,config):
    length,width,height=spec["room_m"]
    nx,ny,nz=spec["mesh_cells"]
    patches=_layout(nx,ny,nz,config)
    vertices=[]
    for k in range(nz+1):
        for j in range(ny+1):
            for i in range(nx+1):
                vertices.append(f"    ({length*i/nx:.12g} {width*j/ny:.12g} {height*k/nz:.12g})")
    blocks=[]
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                coords=((i,j,k),(i+1,j,k),(i+1,j+1,k),(i,j+1,k),
                        (i,j,k+1),(i+1,j,k+1),(i+1,j+1,k+1),(i,j+1,k+1))
                ids=[_idx(*v,nx,ny) for v in coords]
                blocks.append("    hex ("+" ".join(map(str,ids))+") (1 1 1) simpleGrading (1 1 1)")
    patchparts=[]
    for patch,faces in patches.items():
        rendered="\n".join("            ("+" ".join(map(str,face))+")" for face in faces)
        patchparts.append(f"    {patch}\n    {{\n        type {'wall' if patch=='walls' else 'patch'};"
                          f"\n        faces\n        (\n{rendered}\n        );\n    }}")
    body=("convertToMeters 1;\nvertices\n(\n"+"\n".join(vertices)+"\n);\n"
          "blocks\n(\n"+"\n".join(blocks)+"\n);\nedges ();\n"
          "boundary\n(\n"+"\n".join(patchparts)+"\n);\nmergePatchPairs ();")
    inlet_area=len(patches["inlet"])*length/nx*width/ny
    outlet_area=(len(patches["outlet"])*length/nx*width/ny if config==3
                 else len(patches["outlet"])*width/ny*height/nz)
    meta={"inlet_face_count":len(patches["inlet"]),
          "outlet_face_count":len(patches["outlet"]),
          "inlet_area_m2":inlet_area,"outlet_area_m2":outlet_area,
          "nominal_cell_volume_m3":length*width*height/(nx*ny*nz)}
    return _header("dictionary","blockMeshDict",body,"system"),meta

def _field(name, dims, initial, entries, vector=False):
    body=f"dimensions {dims};\ninternalField uniform {initial};\nboundaryField\n{{\n"
    for patch,content in entries.items():
        body+=f"    {patch}\n    {{\n        {content}\n    }}\n"
    return _header("volVectorField" if vector else "volScalarField",name,body+"}","0")

def build_openfoam_files(spec, configuration, *, openfoam_version="v10"):
    validate_openfoam_spec(spec)
    if openfoam_version not in {"v10", "v14"}:
        raise ValueError("openfoam_version must be 'v10' or 'v14'")
    if type(configuration) is not int or configuration not in CONFIGURATIONS:
        raise ValueError("configuration must be an integer 1, 2, or 3")
    mesh,info=_mesh(spec,configuration)
    flow=spec["supply_flow_m3_s"]
    speed=flow/info["inlet_area_m2"]
    u={"inlet":f"type fixedValue; value uniform (0 0 -{speed:.12g});",
       "outlet":"type pressureInletOutletVelocity; value uniform (0 0 0);",
       "walls":"type noSlip;"}
    p={"inlet":"type zeroGradient;","outlet":"type fixedValue; value uniform 0;",
       "walls":"type zeroGradient;"}
    control=(f"""application simpleFoam;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime {spec['max_iterations']};
deltaT 1;
writeControl timeStep;
writeInterval {spec['output_interval']};
writeFormat ascii;
writePrecision 10;
runTimeModifiable no;"""
        if openfoam_version == "v10" else f"""solver incompressibleFluid;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime {spec['max_iterations']};
deltaT 1;
writeControl timeStep;
writeInterval {spec['output_interval']};
writeFormat ascii;
writePrecision 10;
runTimeModifiable no;""")
    schemes="""ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes
{
    default none;
    div(phi,U) bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
fluxRequired { default no; p; }"""
    solution="""solvers
{
  p { solver GAMG; tolerance 1e-8; relTol 0.05; smoother GaussSeidel; }
  U { solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.1; }
}
SIMPLE { nNonOrthogonalCorrectors 0; residualControl { p 1e-5; U 1e-6; } }
relaxationFactors { fields { p 0.3; } equations { U 0.7; } }"""
    constant_properties={
      "constant/physicalProperties":_header("dictionary","physicalProperties",
        f'viscosityModel constant;\nnu {spec["kinematic_viscosity_m2_s"]:.12g};',"constant"),
      "constant/momentumTransport":_header("dictionary","momentumTransport",
        "simulationType laminar;","constant"),
    }
    u_dimensions="[0 1 -1 0 0 0 0]" if openfoam_version == "v10" else "[velocity]"
    p_dimensions="[0 2 -2 0 0 0 0]" if openfoam_version == "v10" else "[kinematicPressure]"
    files={
      "system/blockMeshDict":mesh,
      "system/controlDict":_header("dictionary","controlDict",control,"system"),
      "system/fvSchemes":_header("dictionary","fvSchemes",schemes,"system"),
      "system/fvSolution":_header("dictionary","fvSolution",solution,"system"),
      **constant_properties,
      "0/U":_field("U",u_dimensions,"(0 0 0)",u,vector=True),
      "0/p":_field("p",p_dimensions,"0",p)
    }
    metadata={"configuration":configuration,"layout":CONFIGURATIONS[configuration],
              "mesh_cells":math.prod(spec["mesh_cells"]),"mesh":info,
              "inlet_normal_speed_m_s":speed,"requested_inlet_flow_m3_s":flow,
              "model":"steady incompressible isothermal laminar air (SIMPLE)",
              "openfoam_release":f"OpenFOAM Foundation {openfoam_version[1:]}",
              "solver_command":"simpleFoam" if openfoam_version == "v10" else "foamRun",
              "target":("OpenFOAM Foundation v10 / simpleFoam" if openfoam_version == "v10"
                        else "OpenFOAM Foundation v14 / foamRun -solver incompressibleFluid"),
              "limitations":["no underfloor plenum","no scalar or particle transport",
                  "no turbulence or buoyancy","no mesh convergence proof","empty rectangular room"]}
    return files,metadata

def export_openfoam_cases(spec,directory,*,openfoam_version="v10"):
    validate_openfoam_spec(spec)
    if openfoam_version not in {"v10", "v14"}:
        raise ValueError("openfoam_version must be 'v10' or 'v14'")
    root=Path(directory)
    if root.exists(): raise FileExistsError(f"Refusing overwrite of {root}")
    generated={}
    evidence={}
    for cfg in (1,2,3):
        files,meta=build_openfoam_files(spec,cfg,openfoam_version=openfoam_version)
        generated[cfg]=files
        evidence[str(cfg)]=meta
    canonical=json.dumps(spec,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    manifest={"schema_version":SCHEMA,"openfoam_release":f"OpenFOAM Foundation {openfoam_version[1:]}",
              "spec_sha256":hashlib.sha256(canonical.encode()).hexdigest(),
              "evidence":evidence,"files":{}}
    root.mkdir(parents=True,exist_ok=False)
    try:
        for cfg,files in generated.items():
            for relative,content in files.items():
                filename=root/f"configuration_{cfg}"/relative
                filename.parent.mkdir(parents=True,exist_ok=True)
                with filename.open("x",encoding="utf-8",newline="\n") as fp: fp.write(content)
                manifest["files"][f"configuration_{cfg}/{relative}"]=hashlib.sha256(content.encode()).hexdigest()
        with (root/"manifest.json").open("x",encoding="utf-8") as fp:
            json.dump(manifest,fp,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)
    except BaseException:
        shutil.rmtree(root)
        raise
    return manifest

def _utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _publish_run_manifest(path, payload, *, create=False):
    """Write one run record atomically; never replace a prior run's record."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    if create:
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise FileExistsError(f"Refusing to overwrite existing OpenFOAM run manifest: {path}")
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        return
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _foundation_v10_banner(log_text):
    """Extract and identify the Foundation v10 banner from an OpenFOAM log."""
    version = re.search(r"^.*\bVersion:\s*(\S+)\s*$", log_text, re.MULTILINE)
    website = re.search(r"Website:\s*(https://\S+)", log_text)
    build = re.search(r"^Build\s*:\s*(\S+)\s*$", log_text, re.MULTILINE)
    info = {
        "version": version.group(1) if version else None,
        "website": website.group(1) if website else None,
        "build": build.group(1) if build else None,
    }
    info["is_foundation_v10"] = (
        info["version"] == "10"
        and info["website"] == "https://openfoam.org"
        and bool(info["build"])
    )
    return info


def run_openfoam_cases(directory,*,timeout_seconds=3600,openfoam_version=None):
    """Run a matching Foundation release and preserve execution provenance.

    A successful process exit remains execution evidence only; this function
    never labels solver output converged or physically validated.
    """
    if type(timeout_seconds) is not int or not 60<=timeout_seconds<=86400:
        raise ValueError("timeout_seconds must be an integer in [60,86400]")
    root=Path(directory).resolve(strict=True)
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version")!=SCHEMA or set(manifest.get("evidence",{}))!={"1","2","3"}:
        raise ValueError("Incomplete OpenFOAM bundle")
    release=manifest.get("openfoam_release","OpenFOAM Foundation 10")
    versions={"OpenFOAM Foundation 10":"v10","OpenFOAM Foundation 14":"v14"}
    if release not in versions:
        raise ValueError("Unsupported OpenFOAM release in case manifest")
    if openfoam_version is not None and openfoam_version != versions[release]:
        raise ValueError("requested OpenFOAM release does not match the generated case bundle")
    expected_version = versions[release][1:]
    active_project = os.environ.get("WM_PROJECT")
    active_version = os.environ.get("WM_PROJECT_VERSION")
    if active_project != "OpenFOAM" or active_version != expected_version:
        project_label = active_project if active_project is not None else "unset"
        version_label = active_version if active_version is not None else "unset"
        raise RuntimeError(
            f"active OpenFOAM environment mismatch: expected Foundation v{expected_version} "
            f"(WM_PROJECT=OpenFOAM, WM_PROJECT_VERSION={expected_version}), "
            f"got WM_PROJECT={project_label}, WM_PROJECT_VERSION={version_label}"
        )
    solver = "simpleFoam" if release == "OpenFOAM Foundation 10" else "foamRun"
    for relative,sha in manifest["files"].items():
        f=(root/relative).resolve(strict=True)
        if not f.is_relative_to(root) or hashlib.sha256(f.read_bytes()).hexdigest()!=sha:
            raise ValueError("Tampered generated solver file: "+relative)
    run_manifest_path = root / "run_manifest.json"
    if run_manifest_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing OpenFOAM run manifest: {run_manifest_path}")
    existing_logs = [
        f"configuration_{cfg}/{name}.log"
        for cfg in (1, 2, 3)
        for name in ("blockMesh", "checkMesh", solver)
        if (root / f"configuration_{cfg}" / f"{name}.log").exists()
    ]
    if existing_logs:
        raise FileExistsError(f"Refusing to overwrite existing OpenFOAM solver log: {existing_logs[0]}")
    executables = {}
    for name in ("blockMesh", "checkMesh", solver):
        resolved = shutil.which(name)
        if resolved is None:
            raise RuntimeError(name+" not found; install the targeted OpenFOAM release")
        executables[name] = str(Path(resolved).resolve())

    # The active shell variables identify the sourced release. The executable
    # banner independently guards against a mixed or manually altered PATH.
    probe_command = [executables[solver], "-help"]
    probe = subprocess.run(probe_command, capture_output=True, text=True, timeout=30, check=False)
    probe_output = (probe.stdout or "") + "\n" + (probe.stderr or "")
    expected_banner = f"OpenFOAM-{expected_version}"
    banner_lines = [line.strip() for line in probe_output.splitlines() if "OpenFOAM-" in line]
    banner_pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(expected_banner)}(?![0-9])")
    if probe.returncode != 0 or banner_pattern.search(probe_output) is None:
        raise RuntimeError(
            f"{solver} version probe did not identify {release}; "
            f"expected a successful {expected_banner} banner, "
            f"got exit code {probe.returncode} and {banner_lines or 'no OpenFOAM version banner'}"
        )

    input_manifest_bytes = (root / "manifest.json").read_bytes()
    run_record = {
        "schema_version": "cleanroomx.openfoam.run.v1",
        "status": "running",
        "openfoam_release": release,
        "timeout_seconds": timeout_seconds,
        "started_utc": _utc_timestamp(),
        "completed_utc": None,
        "input_manifest_sha256": hashlib.sha256(input_manifest_bytes).hexdigest(),
        "generated_input_sha256": dict(sorted(manifest["files"].items())),
        "active_environment": {
            key: os.environ.get(key)
            for key in ("WM_PROJECT", "WM_PROJECT_VERSION", "WM_PROJECT_DIR")
            if os.environ.get(key) is not None
        },
        "python_version": sys.version.split()[0],
        "platform": {"os_name": os.name, "sys_platform": sys.platform},
        "executables": executables,
        "foundation_build": None,
        "version_probe": {
            "command": probe_command,
            "returncode": probe.returncode,
            "expected_banner": expected_banner,
            "observed_banner_lines": banner_lines,
        },
        "cases": {},
        "warning": "Process execution does not establish convergence or physical validity.",
    }
    _publish_run_manifest(run_manifest_path, run_record, create=True)

    results={}
    expected_build=None

    def fail_case(cfg, stages, stage, case_status):
        results[str(cfg)]={"status":case_status,"stages":stages}
        run_record["cases"] = results
        run_record["status"] = "incomplete"
        run_record["failure"] = {"configuration": cfg, "stage": stage}
        run_record["completed_utc"] = _utc_timestamp()
        _publish_run_manifest(run_manifest_path, run_record)
        return {"status":"incomplete","cases":results,
                "run_manifest":str(run_manifest_path.relative_to(root)),
                "warning":"Review command logs, release identity, build consistency and physical validity"}

    for cfg in (1,2,3):
        stages=[]
        workdir=root/f"configuration_{cfg}"
        for executable in ("blockMesh","checkMesh",solver):
            log=workdir/f"{executable}.log"
            with log.open("x",encoding="utf-8") as output:
                command = [executables[executable]]
                try:
                    result=subprocess.run(command,cwd=workdir,stdout=output,
                                          stderr=subprocess.STDOUT,timeout=timeout_seconds,check=False)
                    returncode = result.returncode
                    error = None
                except (OSError, subprocess.TimeoutExpired) as exc:
                    returncode = None
                    error = f"{type(exc).__name__}: {exc}"
            log_bytes = log.read_bytes()
            stage = {
                "program": executable,
                "command": command,
                "working_directory": str(workdir.relative_to(root)),
                "returncode": returncode,
                "log": str(log.relative_to(root)),
                "log_size_bytes": len(log_bytes),
                "log_sha256": hashlib.sha256(log_bytes).hexdigest(),
            }
            if error is not None:
                stage["error"] = error
            identity_failure=None
            if release == "OpenFOAM Foundation 10":
                banner=_foundation_v10_banner(log_bytes.decode("utf-8",errors="replace"))
                stage["openfoam"]=banner
                if returncode == 0:
                    if not banner["is_foundation_v10"]:
                        stage["error"] = "stage log does not identify OpenFOAM Foundation v10"
                        identity_failure="unsupported_release"
                    elif expected_build is None:
                        expected_build=banner["build"]
                        run_record["foundation_build"]=expected_build
                    elif banner["build"] != expected_build:
                        stage["error"] = f"stage build {banner['build']} differs from {expected_build}"
                        identity_failure="inconsistent_build"
            stages.append(stage)
            if returncode != 0 or identity_failure:
                case_status=identity_failure or ("solver_failed" if error is None else "execution_error")
                return fail_case(cfg,stages,stage,case_status)
        results[str(cfg)]={"status":"executed_requires_convergence_review","stages":stages}
        run_record["cases"] = results
        _publish_run_manifest(run_manifest_path, run_record)
    run_record["status"] = "executed_requires_convergence_review"
    run_record["completed_utc"] = _utc_timestamp()
    _publish_run_manifest(run_manifest_path, run_record)
    return {"status":"executed_requires_convergence_review","cases":results,
            "solver_release":release,
            "solver_build":expected_build,
            "executables":executables,
            "run_manifest":str(run_manifest_path.relative_to(root)),
            "warning":"Review residuals, mass conservation, mesh sensitivity and physical validity"}
