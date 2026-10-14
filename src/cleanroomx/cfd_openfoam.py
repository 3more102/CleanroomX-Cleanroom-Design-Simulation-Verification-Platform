"""OpenFOAM v10 case generation for the three cleanroom CFD layouts.

This models steady isothermal laminar flow; it is NOT CFD validation,
ISO certification, particle transport, turbulence or underfloor plenum CFD.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

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

def build_openfoam_files(spec, configuration):
    validate_openfoam_spec(spec)
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
    control=f"""application simpleFoam;
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
    schemes="""ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes { default none; div(phi,U) bounded Gauss upwind; div((nuEff*dev2(T(grad(U))))) Gauss linear; }
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
    files={
      "system/blockMeshDict":mesh,
      "system/controlDict":_header("dictionary","controlDict",control,"system"),
      "system/fvSchemes":_header("dictionary","fvSchemes",schemes,"system"),
      "system/fvSolution":_header("dictionary","fvSolution",solution,"system"),
      "constant/physicalProperties":_header("dictionary","physicalProperties",
        f'viscosityModel constant;\nnu [0 2 -1 0 0 0 0] {spec["kinematic_viscosity_m2_s"]:.12g};',"constant"),
      "constant/momentumTransport":_header("dictionary","momentumTransport",
        "simulationType laminar;","constant"),
      "0/U":_field("U","[0 1 -1 0 0 0 0]","(0 0 0)",u,vector=True),
      "0/p":_field("p","[0 2 -2 0 0 0 0]","0",p)
    }
    metadata={"configuration":configuration,"layout":CONFIGURATIONS[configuration],
              "mesh_cells":math.prod(spec["mesh_cells"]),"mesh":info,
              "inlet_normal_speed_m_s":speed,"requested_inlet_flow_m3_s":flow,
              "model":"steady incompressible isothermal laminar air (SIMPLE)",
              "target":"OpenFOAM Foundation v10 / simpleFoam",
              "limitations":["no underfloor plenum","no scalar or particle transport",
                  "no turbulence or buoyancy","no mesh convergence proof","empty rectangular room"]}
    return files,metadata

def export_openfoam_cases(spec,directory):
    validate_openfoam_spec(spec)
    root=Path(directory)
    if root.exists(): raise FileExistsError(f"Refusing overwrite of {root}")
    generated={}
    evidence={}
    for cfg in (1,2,3):
        files,meta=build_openfoam_files(spec,cfg)
        generated[cfg]=files
        evidence[str(cfg)]=meta
    canonical=json.dumps(spec,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    manifest={"schema_version":SCHEMA,
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

def run_openfoam_cases(directory,*,timeout_seconds=3600):
    """Opt-in external execution; never imply CFD convergence from process exit."""
    if type(timeout_seconds) is not int or not 60<=timeout_seconds<=86400:
        raise ValueError("timeout_seconds must be an integer in [60,86400]")
    root=Path(directory).resolve(strict=True)
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version")!=SCHEMA or set(manifest.get("evidence",{}))!={"1","2","3"}:
        raise ValueError("Incomplete OpenFOAM bundle")
    for relative,sha in manifest["files"].items():
        f=(root/relative).resolve(strict=True)
        if not f.is_relative_to(root) or hashlib.sha256(f.read_bytes()).hexdigest()!=sha:
            raise ValueError("Tampered generated solver file: "+relative)
    for name in ("blockMesh","checkMesh","simpleFoam"):
        if shutil.which(name) is None:
            raise RuntimeError(name+" not found; install the targeted OpenFOAM release")
    results={}
    for cfg in (1,2,3):
        stages=[]
        workdir=root/f"configuration_{cfg}"
        for executable in ("blockMesh","checkMesh","simpleFoam"):
            log=workdir/f"{executable}.log"
            with log.open("x",encoding="utf-8") as output:
                result=subprocess.run([executable],cwd=workdir,stdout=output,
                                      stderr=subprocess.STDOUT,timeout=timeout_seconds,check=False)
            stages.append({"program":executable,"returncode":result.returncode,
                           "log":str(log.relative_to(root)),
                           "log_sha256":hashlib.sha256(log.read_bytes()).hexdigest()})
            if result.returncode:
                results[str(cfg)]={"status":"solver_failed","stages":stages}
                return {"status":"incomplete","cases":results,
                        "warning":"Check logs and convergence; execution is not validation"}
        results[str(cfg)]={"status":"executed_requires_convergence_review","stages":stages}
    return {"status":"executed_requires_convergence_review","cases":results,
            "warning":"Review residuals, mass conservation, mesh sensitivity and physical validity"}
