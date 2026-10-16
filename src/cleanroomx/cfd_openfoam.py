"""OpenFOAM v10 case generation for the three cleanroom CFD layouts.

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
import stat
import subprocess
import uuid

from .cfd_study import CONFIGURATIONS
from .persistence import stable_file_sha256, stable_file_snapshot
from .strict_json import load_strict_json_snapshot

SCHEMA = "cleanroomx.openfoam.v1"
MAX_CELLS = 20_000
FOUNDATION_RELEASE = "10"
MAX_CASE_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_CASE_INPUT_BYTES = 8 * 1024 * 1024
MAX_CASE_INPUT_TOTAL_BYTES = 64 * 1024 * 1024

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

def _parenthesized_section(text, name):
    match=re.search(rf"(?m)^\s*{re.escape(name)}\s*\(",text)
    if not match:
        raise ValueError(f"Missing {name} section in blockMeshDict")
    start=match.end()
    depth=1
    for position in range(start,len(text)):
        if text[position]=="(":
            depth+=1
        elif text[position]==")":
            depth-=1
            if depth==0:
                return text[start:position]
    raise ValueError(f"Unclosed {name} section in blockMeshDict")

def _face_area_vector(face, vertices):
    points=[vertices[index] for index in face]
    if len(points)<3 or len(set(face))!=len(face):
        raise ValueError("Boundary face must contain distinct vertex indices")
    vector=[0.0,0.0,0.0]
    for current,following in zip(points,points[1:]+points[:1]):
        vector[0]+=current[1]*following[2]-current[2]*following[1]
        vector[1]+=current[2]*following[0]-current[0]*following[2]
        vector[2]+=current[0]*following[1]-current[1]*following[0]
    vector=[component*0.5 for component in vector]
    area=math.sqrt(sum(component*component for component in vector))
    if not math.isfinite(area) or area<=0:
        raise ValueError("Boundary face has zero or invalid area")
    return vector,area

def _hex_exterior_face_signatures(block_text, vertex_count):
    """Return the complete exterior-face set for generated hex blocks."""
    matches=list(re.finditer(
        r"\bhex\s*\(\s*([^()]*)\)\s*\(\s*([^()]*)\)\s*simpleGrading\s*\(\s*([^()]*)\)",
        block_text,
    ))
    declarations=len(re.findall(r"\bhex\s*\(",block_text))
    if not matches or len(matches)!=declarations:
        raise ValueError("blockMeshDict must contain only supported generated hex blocks")
    face_uses={}
    for match in matches:
        raw_ids=match.group(1).split()
        if len(raw_ids)!=8 or any(not re.fullmatch(r"[+-]?\d+",value) for value in raw_ids):
            raise ValueError("blockMeshDict hex block has invalid vertex indices")
        ids=tuple(int(value) for value in raw_ids)
        if len(set(ids))!=8 or any(index<0 or index>=vertex_count for index in ids):
            raise ValueError("blockMeshDict hex block has invalid vertex indices")
        a,b,c,d,e,f,g,h=ids
        for face in ((a,d,c,b),(e,f,g,h),(a,e,h,d),(b,c,g,f),(a,b,f,e),(d,h,g,c)):
            signature=tuple(sorted(face))
            face_uses[signature]=face_uses.get(signature,0)+1
    if any(count>2 for count in face_uses.values()):
        raise ValueError("blockMeshDict hex topology contains a non-manifold face")
    return {signature for signature,count in face_uses.items() if count==1}

def _field_patch_block(field_text, patch):
    blocks=re.findall(
        rf"(?ms)^\s*{re.escape(patch)}\s*\{{(.*?)^\s*\}}",
        field_text,
    )
    if len(blocks)!=1:
        raise ValueError(f"Expected exactly one {patch} boundary entry")
    return blocks[0]

def audit_openfoam_boundary_inputs(files, metadata):
    """Audit generated patch geometry and prescribed inlet volume flow.

    The outlet flow is solver-derived and is intentionally reported as
    unmeasured; this input audit does not claim mass balance or validation.
    """
    if type(files) is not dict or type(metadata) is not dict:
        raise ValueError("case files and metadata must be objects")
    configuration=metadata.get("configuration")
    if type(configuration) is not int or configuration not in (1,2,3):
        raise ValueError("boundary audit requires configuration 1, 2, or 3")
    try:
        mesh_text=files["system/blockMeshDict"]
        velocity_text=files["0/U"]
        pressure_text=files["0/p"]
        mesh_metadata=metadata["mesh"]
        requested_flow_raw=metadata["requested_inlet_flow_m3_s"]
    except (KeyError,TypeError,ValueError) as error:
        raise ValueError("case is missing boundary audit inputs") from error
    if type(requested_flow_raw) not in (int,float):
        raise ValueError("requested inlet flow must be numeric")
    requested_flow=float(requested_flow_raw)
    if not all(math.isfinite(value) and value>0 for value in (requested_flow,)):
        raise ValueError("requested inlet flow must be finite and positive")

    number=r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    vertex_section=_parenthesized_section(mesh_text,"vertices")
    vertices=[]
    for match in re.finditer(rf"\(\s*({number})\s+({number})\s+({number})\s*\)",vertex_section):
        point=tuple(float(value) for value in match.groups())
        if not all(math.isfinite(value) for value in point):
            raise ValueError("blockMeshDict contains a non-finite vertex")
        vertices.append(point)
    if not vertices:
        raise ValueError("blockMeshDict has no parseable vertices")

    boundary_section=_parenthesized_section(mesh_text,"boundary")
    blocks_section=_parenthesized_section(mesh_text,"blocks")
    exterior_faces=_hex_exterior_face_signatures(blocks_section,len(vertices))
    patch_matches=list(re.finditer(
        r"(?ms)^\s*(inlet|outlet|walls)\s*\{\s*type\s+(\w+)\s*;\s*faces\s*\((.*?)\);\s*\}",
        boundary_section,
    ))
    patches={match.group(1):match for match in patch_matches}
    if set(patches)!={"inlet","outlet","walls"} or len(patch_matches)!=3:
        raise ValueError("blockMeshDict must contain exactly inlet, outlet, and walls patches")
    patch_types={name:match.group(2) for name,match in patches.items()}
    if patch_types!={"inlet":"patch","outlet":"patch","walls":"wall"}:
        raise ValueError("blockMeshDict patch types do not match the generated case")

    face_data={}
    assigned_faces=set()
    for patch,match in patches.items():
        face_text=match.group(3)
        faces=[tuple(int(value) for value in found.groups()) for found in
               re.finditer(r"\(\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*\)",face_text)]
        if not faces:
            raise ValueError(f"{patch} patch has no parseable faces")
        rows=[]
        for face in faces:
            if any(index>=len(vertices) for index in face):
                raise ValueError(f"{patch} patch references a missing vertex")
            signature=tuple(sorted(face))
            if signature in assigned_faces:
                raise ValueError("blockMeshDict boundary face is duplicated across patches")
            if signature not in exterior_faces:
                raise ValueError("blockMeshDict boundary face is not an exterior hex face")
            assigned_faces.add(signature)
            vector,area=_face_area_vector(face,vertices)
            normal=tuple(component/area for component in vector)
            rows.append((normal,area))
        face_data[patch]=rows
    if assigned_faces!=exterior_faces:
        raise ValueError("blockMeshDict boundary patches do not cover every exterior hex face")

    expected_mesh=mesh_metadata
    for patch,count_key,area_key in (
        ("inlet","inlet_face_count","inlet_area_m2"),
        ("outlet","outlet_face_count","outlet_area_m2"),
    ):
        actual_count=len(face_data[patch])
        actual_area=sum(area for _,area in face_data[patch])
        try:
            expected_count=expected_mesh[count_key]
            expected_area=float(expected_mesh[area_key])
        except (KeyError,TypeError,ValueError) as error:
            raise ValueError(f"mesh metadata is missing {patch} geometry") from error
        if type(expected_count) is not int or not math.isfinite(expected_area) or expected_area<=0:
            raise ValueError(f"mesh metadata has invalid {patch} geometry")
        if actual_count!=expected_count or not math.isclose(actual_area,expected_area,rel_tol=1e-10,abs_tol=1e-12):
            raise ValueError(f"{patch} face geometry disagrees with generated metadata")

    expected_inlet=(0.0,0.0,1.0)
    for normal,_ in face_data["inlet"]:
        if sum(a*b for a,b in zip(normal,expected_inlet))<1-1e-9:
            raise ValueError("inlet faces must have upward outward normals")
    expected_outlet=(0.0,0.0,-1.0) if configuration==3 else None
    for normal,_ in face_data["outlet"]:
        if expected_outlet is not None:
            aligned=sum(a*b for a,b in zip(normal,expected_outlet))>1-1e-9
        else:
            aligned=abs(abs(normal[0])-1)<1e-9 and abs(normal[1])<1e-9 and abs(normal[2])<1e-9
        if not aligned:
            raise ValueError("outlet face normal does not match the selected layout")

    inlet_block=_field_patch_block(velocity_text,"inlet")
    if not re.search(r"\btype\s+fixedValue\s*;",inlet_block):
        raise ValueError("inlet velocity must use fixedValue")
    vector_match=re.search(rf"\bvalue\s+uniform\s*\(\s*({number})\s+({number})\s+({number})\s*\)\s*;",inlet_block)
    if not vector_match:
        raise ValueError("inlet velocity must be a uniform vector")
    velocity=tuple(float(value) for value in vector_match.groups())
    if not all(math.isfinite(value) for value in velocity):
        raise ValueError("inlet velocity contains a non-finite value")
    computed_flow=0.0
    for normal,area in face_data["inlet"]:
        inward_speed=-sum(a*b for a,b in zip(normal,velocity))
        if inward_speed<=0:
            raise ValueError("prescribed inlet velocity does not point into the mesh")
        computed_flow+=area*inward_speed
    if not math.isclose(computed_flow,requested_flow,rel_tol=1e-9,abs_tol=1e-12):
        raise ValueError("prescribed inlet velocity and patch geometry do not reproduce requested flow")

    expected_types={"outlet":"pressureInletOutletVelocity","walls":"noSlip"}
    for patch,kind in expected_types.items():
        if not re.search(rf"\btype\s+{kind}\s*;",_field_patch_block(velocity_text,patch)):
            raise ValueError(f"velocity condition on {patch} must use {kind}")
    pressure_types={"inlet":"zeroGradient","outlet":"fixedValue","walls":"zeroGradient"}
    for patch,kind in pressure_types.items():
        block=_field_patch_block(pressure_text,patch)
        if not re.search(rf"\btype\s+{kind}\s*;",block):
            raise ValueError(f"pressure condition on {patch} must use {kind}")
    if not re.search(r"\bvalue\s+uniform\s+0\s*;",_field_patch_block(pressure_text,"outlet")):
        raise ValueError("outlet pressure must be the generated zero-gauge value")

    def rounded(value):
        return float(f"{value:.12g}")
    def direction(normal):
        axis=max(range(3),key=lambda index:abs(normal[index]))
        sign="+" if normal[axis]>=0 else "-"
        return sign+"xyz"[axis]
    normal_areas={}
    for patch in ("inlet","outlet"):
        grouped={}
        for normal,area in face_data[patch]:
            key=direction(normal)
            grouped[key]=grouped.get(key,0.0)+area
        normal_areas[patch]={key:rounded(value) for key,value in sorted(grouped.items())}
    return {
        "schema_version":"cleanroomx.openfoam-boundary-audit.v1",
        "status":"input_geometry_and_inlet_flow_consistent",
        "configuration":configuration,
        "inlet":{
            "face_count":len(face_data["inlet"]),
            "area_m2":rounded(sum(area for _,area in face_data["inlet"])),
            "outward_normal_area_m2":normal_areas["inlet"],
            "velocity_m_s":[rounded(value) for value in velocity],
            "prescribed_inward_volume_flow_m3_s":rounded(computed_flow),
            "requested_volume_flow_m3_s":rounded(requested_flow),
        },
        "outlet":{
            "face_count":len(face_data["outlet"]),
            "area_m2":rounded(sum(area for _,area in face_data["outlet"])),
            "outward_normal_area_m2":normal_areas["outlet"],
            "actual_solver_volume_flow_m3_s":None,
            "actual_solver_flux_status":"not_measured",
        },
        "flow_balance_status":"not_measured",
        "scientific_validation":"BLOCKED",
    }

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
    files={
      "system/blockMeshDict":mesh,
      "system/controlDict":_header("dictionary","controlDict",control,"system"),
      "system/fvSchemes":_header("dictionary","fvSchemes",schemes,"system"),
      "system/fvSolution":_header("dictionary","fvSolution",solution,"system"),
      "constant/physicalProperties":_header("dictionary","physicalProperties",
        f'viscosityModel constant;\nnu {spec["kinematic_viscosity_m2_s"]:.12g};',"constant"),
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
    metadata["boundary_audit"]=audit_openfoam_boundary_inputs(files,metadata)
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


def verify_openfoam_case_bundle(directory):
    """Verify generated case-input hashes and boundary consistency, read-only.

    This is an input-integrity preflight only. It does not execute OpenFOAM,
    assess solver convergence, establish grid independence, or validate the
    model against measured cleanroom data.
    """
    candidate = Path(directory).expanduser()
    if candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("Case bundle must be a regular directory")
    root = candidate.resolve(strict=True)
    manifest_path = root / "manifest.json"
    try:
        manifest_info = manifest_path.lstat()
    except OSError as error:
        raise ValueError("Case bundle manifest is missing or unreadable") from error
    if stat.S_ISLNK(manifest_info.st_mode) or not stat.S_ISREG(manifest_info.st_mode):
        raise ValueError("Case bundle manifest must be a regular file")
    snapshot = load_strict_json_snapshot(
        manifest_path, max_bytes=MAX_CASE_MANIFEST_BYTES
    )
    manifest = snapshot.value
    if type(manifest) is not dict or set(manifest) != {
        "schema_version", "spec_sha256", "evidence", "files"
    }:
        raise ValueError("Case bundle manifest has an unsupported structure")
    if manifest.get("schema_version") != SCHEMA:
        raise ValueError("Case bundle manifest uses an unsupported schema")
    if type(manifest.get("spec_sha256")) is not str or not re.fullmatch(
        r"[0-9a-f]{64}", manifest["spec_sha256"]
    ):
        raise ValueError("Case bundle manifest has an invalid specification digest")

    case_inputs = (
        "system/blockMeshDict",
        "system/controlDict",
        "system/fvSchemes",
        "system/fvSolution",
        "constant/physicalProperties",
        "constant/momentumTransport",
        "0/U",
        "0/p",
    )
    expected_files = {
        f"configuration_{configuration}/{relative}"
        for configuration in (1, 2, 3)
        for relative in case_inputs
    }
    files = manifest.get("files")
    if type(files) is not dict or set(files) != expected_files:
        raise ValueError("Case bundle must bind the exact 24 generated input files")
    evidence = manifest.get("evidence")
    if type(evidence) is not dict or set(evidence) != {"1", "2", "3"}:
        raise ValueError(
            "Case bundle must contain metadata for all three configurations"
        )

    file_records = []
    total_bytes = 0
    boundary_text: dict[str, dict[str, str]] = {"1": {}, "2": {}, "3": {}}
    boundary_files = {
        f"configuration_{configuration}/{relative}"
        for configuration in (1, 2, 3)
        for relative in ("system/blockMeshDict", "0/U", "0/p")
    }
    for relative in sorted(expected_files):
        expected_sha = files[relative]
        if type(expected_sha) is not str or not re.fullmatch(
            r"[0-9a-f]{64}", expected_sha
        ):
            raise ValueError(f"Case manifest has an invalid SHA-256 for {relative}")
        path = root.joinpath(*Path(relative).parts)

        # Check every component without following links. The manifest is an
        # untrusted input, and even a correctly hashed external target is not
        # a file inside the selected case bundle.
        current = root
        components = Path(relative).parts
        checked_components = []
        for index, component in enumerate(components):
            current = current / component
            try:
                info = current.lstat()
            except OSError as error:
                raise ValueError(f"Missing generated solver file: {relative}") from error
            checked_components.append((current, info))
            if stat.S_ISLNK(info.st_mode):
                raise ValueError(
                    f"Symbolic links are not allowed in case inputs: {relative}"
                )
            if index < len(components) - 1:
                if not stat.S_ISDIR(info.st_mode):
                    raise ValueError(f"Invalid case input directory: {relative}")
            elif not stat.S_ISREG(info.st_mode):
                raise ValueError(f"Generated solver input must be a regular file: {relative}")
            elif info.st_size > MAX_CASE_INPUT_BYTES:
                raise ValueError(f"Generated solver input exceeds the size limit: {relative}")

        configuration = relative.split("/", 1)[0].removeprefix("configuration_")
        case_relative = relative.split("/", 1)[1]
        if relative in boundary_files:
            try:
                with stable_file_snapshot(
                    path,
                    max_bytes=MAX_CASE_INPUT_BYTES,
                    suffix=path.suffix,
                ) as (stable_path, metadata, observed_sha):
                    if observed_sha != expected_sha:
                        raise ValueError(f"Tampered generated solver file: {relative}")
                    total_bytes += metadata.st_size
                    if total_bytes > MAX_CASE_INPUT_TOTAL_BYTES:
                        raise ValueError("Case bundle exceeds the total input size limit")
                    boundary_text[configuration][case_relative] = stable_path.read_text(
                        encoding="utf-8"
                    )
            except UnicodeDecodeError as error:
                raise ValueError(
                    f"Generated solver input is not valid UTF-8: {relative}"
                ) from error
        else:
            metadata, observed_sha = stable_file_sha256(
                path, max_bytes=MAX_CASE_INPUT_BYTES
            )
            if observed_sha != expected_sha:
                raise ValueError(f"Tampered generated solver file: {relative}")
            total_bytes += metadata.st_size
            if total_bytes > MAX_CASE_INPUT_TOTAL_BYTES:
                raise ValueError("Case bundle exceeds the total input size limit")

        # Revalidate the exact path components after opening and hashing. A
        # directory replaced with a symlink during the read must not be able
        # to redirect this preflight to an external, hash-matching file.
        for checked_path, checked_info in checked_components:
            try:
                current_info = checked_path.lstat()
            except OSError as error:
                raise ValueError(
                    f"Case input path changed during preflight: {relative}"
                ) from error
            same_identity = (
                current_info.st_dev == checked_info.st_dev
                and current_info.st_ino == checked_info.st_ino
                and stat.S_IFMT(current_info.st_mode)
                == stat.S_IFMT(checked_info.st_mode)
            )
            if stat.S_ISLNK(current_info.st_mode) or not same_identity:
                raise ValueError(
                    f"Case input path changed during preflight: {relative}"
                )
        file_records.append(
            {
                "path": relative,
                "size_bytes": metadata.st_size,
                "sha256": observed_sha,
                "verified": True,
            }
        )

    boundary_audits = {}
    for configuration in (1, 2, 3):
        key = str(configuration)
        metadata = evidence[key]
        if type(metadata) is not dict:
            raise ValueError(
                f"Case bundle metadata for configuration {configuration} is invalid"
            )
        audit = audit_openfoam_boundary_inputs(boundary_text[key], metadata)
        if metadata.get("boundary_audit") != audit:
            raise ValueError(
                f"Boundary audit metadata mismatch for configuration {configuration}"
            )
        boundary_audits[key] = audit

    return {
        "schema_version": "cleanroomx.openfoam-case-input-verification.v1",
        "status": "verified_against_local_manifest",
        "interpretation": "input_integrity_and_boundary_consistency_only",
        "manifest_authentication": "not_signed",
        "manifest_sha256": hashlib.sha256(snapshot.raw_bytes).hexdigest(),
        "spec_sha256": manifest["spec_sha256"],
        "files_checked": len(file_records),
        "files_expected": len(expected_files),
        "total_bytes_checked": total_bytes,
        "files": file_records,
        "boundary_audits_passed": len(boundary_audits),
        "boundary_audits": boundary_audits,
        "scientific_validation": "BLOCKED",
        "limitations": [
            "Input digests are compared with the local manifest, which is not digitally signed.",
            "No solver was executed by this preflight.",
            "Solver convergence, grid independence, and physical validation were not assessed.",
            "Measured cleanroom data and independent scientific review are still required.",
        ],
    }

def _foundation_v10_banner(log_text):
    """Extract and identify the Foundation banner from an OpenFOAM log."""
    version = re.search(r"^.*\bVersion:\s*(\S+)\s*$", log_text, re.MULTILINE)
    website = re.search(r"Website:\s*(https://\S+)", log_text)
    build = re.search(r"^Build\s*:\s*(\S+)\s*$", log_text, re.MULTILINE)
    info = {
        "version": version.group(1) if version else None,
        "website": website.group(1) if website else None,
        "build": build.group(1) if build else None,
    }
    info["is_foundation_v10"] = (
        info["version"] == FOUNDATION_RELEASE
        and info["website"] == "https://openfoam.org"
        and bool(info["build"])
    )
    return info


def parse_openfoam_checkmesh_log(log_text, source_log_sha256):
    """Extract hash-bound Foundation checkMesh diagnostics without judging quality.

    The report preserves OpenFOAM's printed checks and geometric measurements,
    but deliberately applies no project-specific acceptance thresholds.
    Missing, repeated, malformed, or non-finite records remain explicit.
    """
    if type(log_text) is not str:
        raise ValueError("checkMesh log must be text")
    if type(source_log_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", source_log_sha256):
        raise ValueError("checkMesh log SHA-256 must be 64 lowercase hexadecimal characters")
    if hashlib.sha256(log_text.encode("utf-8")).hexdigest() != source_log_sha256:
        raise ValueError("checkMesh log SHA-256 does not match the supplied text")

    report = {
        "schema_version": "cleanroomx.openfoam-checkmesh-diagnostics.v1",
        "parse_status": None,
        "source_log_sha256": source_log_sha256,
        "interpretation": "diagnostic_only",
        "project_acceptance": "not_assessed_no_project_criteria",
        "counts": {"cell_types": {}},
        "geometry": {},
        "reported_checks": {},
        "patch_topology": [],
        "reported_check_failures": [],
        "mesh_result": "unknown",
        "missing_fields": [],
        "ambiguous_fields": [],
        "invalid_fields": [],
    }
    number = r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|[-+]?(?:nan|inf(?:inity)?))"

    def extract(label, pattern, convert, target, key):
        matches = list(re.finditer(pattern, log_text, re.MULTILINE | re.IGNORECASE))
        if not matches:
            report["missing_fields"].append(label)
            return
        if len(matches) != 1:
            report["ambiguous_fields"].append(label)
            return
        try:
            target[key] = convert(matches[0])
        except (TypeError, ValueError, OverflowError):
            report["invalid_fields"].append(label)

    def integer(match):
        return int(match.group(1))

    def finite_float(raw):
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("non-finite metric")
        return value

    def float_group(group):
        return lambda match: finite_float(match.group(group))

    def vector_group(group):
        def convert(match):
            values = [finite_float(item) for item in match.group(group).split()]
            if len(values) != 3:
                raise ValueError("expected three components")
            return values
        return convert

    def check_status(match, group):
        value = match.group(group).rstrip(".").lower()
        if value not in ("ok", "failed"):
            raise ValueError("unrecognized checkMesh status")
        return value

    counts = report["counts"]
    geometry = report["geometry"]
    checks = report["reported_checks"]

    for label, pattern, key in (
        ("points", r"^\s*points:\s*(\d+)\s*$", "points"),
        ("faces", r"^\s*faces:\s*(\d+)\s*$", "faces"),
        ("internal_faces", r"^\s*internal faces:\s*(\d+)\s*$", "internal_faces"),
        ("cells", r"^\s*cells:\s*(\d+)\s*$", "cells"),
        ("faces_per_cell", r"^\s*faces per cell:\s*(\d+)\s*$", "faces_per_cell"),
        ("boundary_patches", r"^\s*boundary patches:\s*(\d+)\s*$", "boundary_patches"),
        ("point_zones", r"^\s*point zones:\s*(\d+)\s*$", "point_zones"),
        ("face_zones", r"^\s*face zones:\s*(\d+)\s*$", "face_zones"),
        ("cell_zones", r"^\s*cell zones:\s*(\d+)\s*$", "cell_zones"),
    ):
        extract(label, pattern, integer, counts, key)

    for label, pattern, key in (
        ("hexahedra", r"^\s*hexahedra:\s*(\d+)\s*$", "hexahedra"),
        ("prisms", r"^\s*prisms:\s*(\d+)\s*$", "prisms"),
        ("wedges", r"^\s*wedges:\s*(\d+)\s*$", "wedges"),
        ("pyramids", r"^\s*pyramids:\s*(\d+)\s*$", "pyramids"),
        ("tet_wedges", r"^\s*tet wedges:\s*(\d+)\s*$", "tet_wedges"),
        ("tetrahedra", r"^\s*tetrahedra:\s*(\d+)\s*$", "tetrahedra"),
        ("polyhedra", r"^\s*polyhedra:\s*(\d+)\s*$", "polyhedra"),
    ):
        extract(label, pattern, integer, counts["cell_types"], key)

    extract(
        "number_of_regions",
        r"^\s*Number of regions:\s*(\d+)\s*\((OK|Failed)\)\.?\s*$",
        integer,
        counts,
        "regions",
    )
    regions_status = list(re.finditer(
        r"^\s*Number of regions:\s*\d+\s*\((OK|Failed)\)\.?\s*$",
        log_text,
        re.MULTILINE | re.IGNORECASE,
    ))
    if len(regions_status) == 1:
        checks["number_of_regions"] = regions_status[0].group(1).lower()
    elif len(regions_status) > 1:
        report["ambiguous_fields"].append("number_of_regions_status")
    else:
        report["missing_fields"].append("number_of_regions_status")

    patch_topology_markers = list(re.finditer(
        r"^\s*Checking patch topology for multiply connected surfaces\.\.\.\s*$",
        log_text,
        re.MULTILINE | re.IGNORECASE,
    ))
    if not patch_topology_markers:
        report["missing_fields"].append("patch_topology_section")
    elif len(patch_topology_markers) != 1:
        report["ambiguous_fields"].append("patch_topology_section")
    else:
        topology_start = patch_topology_markers[0].end()
        geometry_markers = list(re.finditer(
            r"^\s*Checking geometry\.\.\.\s*$",
            log_text[topology_start:],
            re.MULTILINE | re.IGNORECASE,
        ))
        if len(geometry_markers) != 1:
            report["missing_fields" if not geometry_markers else "ambiguous_fields"].append(
                "patch_topology_section_end"
            )
        else:
            topology_text = log_text[topology_start:topology_start + geometry_markers[0].start()]
            table_headers = list(re.finditer(
                r"^\s*Patch\s+Faces\s+Points\s+Surface topology\s*$",
                topology_text,
                re.MULTILINE | re.IGNORECASE,
            ))
            if not table_headers:
                report["missing_fields"].append("patch_topology_header")
                patch_rows = []
            elif len(table_headers) != 1:
                report["ambiguous_fields"].append("patch_topology_header")
                patch_rows = []
            else:
                table_text = topology_text[table_headers[0].end():]
                patch_rows = list(re.finditer(
                    r"^\s*([A-Za-z0-9_.-]+)\s+(\d+)\s+(\d+)\s+(OK|Failed)"
                    r"(?:\s*\(([^)]*)\))?\s*$",
                    table_text,
                    re.MULTILINE | re.IGNORECASE,
                ))
            report["patch_topology"] = [
                {
                    "name": match.group(1),
                    "faces": int(match.group(2)),
                    "points": int(match.group(3)),
                    "status": match.group(4).lower(),
                    "description": match.group(5),
                }
                for match in patch_rows
            ]
            patch_names = [row["name"] for row in report["patch_topology"]]
            if not patch_rows:
                report["missing_fields"].append("patch_topology_rows")
            if len(patch_names) != len(set(patch_names)):
                report["ambiguous_fields"].append("patch_topology_names")
            expected_patch_count = counts.get("boundary_patches")
            if expected_patch_count is not None and len(patch_rows) != expected_patch_count:
                report["invalid_fields"].append("patch_topology_count")
            if patch_rows:
                checks["patch_topology"] = (
                    "failed" if any(row["status"] != "ok" for row in report["patch_topology"])
                    else "ok"
                )

    bbox_pattern = (
        rf"^\s*Overall domain bounding box\s*\(\s*([^)]*)\)\s*\(\s*([^)]*)\)\s*$"
    )
    def parse_bbox(match):
        lower = [finite_float(value) for value in match.group(1).split()]
        upper = [finite_float(value) for value in match.group(2).split()]
        if len(lower) != 3 or len(upper) != 3:
            raise ValueError("expected two 3D points")
        return [lower, upper]
    extract("domain_bounding_box", bbox_pattern, parse_bbox, geometry, "domain_bounding_box")

    for label, pattern, key in (
        ("geometric_directions", r"^\s*Mesh has \d+ geometric .* directions\s*\(([^)]*)\)\s*$", "geometric_directions"),
        ("solution_directions", r"^\s*Mesh has \d+ solution .* directions\s*\(([^)]*)\)\s*$", "solution_directions"),
    ):
        def parse_directions(match):
            values = [int(value) for value in match.group(1).split()]
            if len(values) != 3 or any(value not in (0, 1) for value in values):
                raise ValueError("expected three direction flags")
            return values
        extract(label, pattern, parse_directions, geometry, key)

    for label, pattern, key in (
        ("max_cell_openness", rf"^\s*Max cell openness\s*=\s*{number}\s+(OK|Failed)\.?\s*$", "max_cell_openness"),
        ("max_aspect_ratio", rf"^\s*Max aspect ratio\s*=\s*{number}\s+(OK|Failed)\.?\s*$", "max_aspect_ratio"),
        ("max_skewness", rf"^\s*Max skewness\s*=\s*{number}\s+(OK|Failed)\.?\s*$", "max_skewness"),
    ):
        extract(label, pattern, float_group(1), geometry, key)
        status_key = label.removeprefix("max_")
        status_matches = list(re.finditer(pattern, log_text, re.MULTILINE | re.IGNORECASE))
        if len(status_matches) == 1:
            checks[status_key] = check_status(status_matches[0], 2)
        elif len(status_matches) > 1:
            report["ambiguous_fields"].append(label + "_status")
        else:
            report["missing_fields"].append(label + "_status")

    face_area_pattern = (
        rf"^\s*Minimum face area\s*=\s*{number}\.\s*Maximum face area\s*=\s*{number}\.\s*"
        r"Face area magnitudes (OK|Failed)\.?\s*$"
    )
    def parse_face_areas(match):
        return [finite_float(match.group(1)), finite_float(match.group(2))]
    extract("face_area_range", face_area_pattern, parse_face_areas, geometry, "face_area_range_m2")
    area_matches = list(re.finditer(face_area_pattern, log_text, re.MULTILINE | re.IGNORECASE))
    if len(area_matches) == 1:
        checks["face_area_magnitudes"] = check_status(area_matches[0], 3)
    elif len(area_matches) > 1:
        report["ambiguous_fields"].append("face_area_magnitudes_status")
    else:
        report["missing_fields"].append("face_area_magnitudes_status")

    volume_pattern = (
        rf"^\s*Min volume\s*=\s*{number}\.\s*Max volume\s*=\s*{number}\.\s*"
        rf"Total volume\s*=\s*{number}\.\s*Cell volumes (OK|Failed)\.?\s*$"
    )
    def parse_volumes(match):
        return [finite_float(match.group(1)), finite_float(match.group(2)), finite_float(match.group(3))]
    extract("cell_volume_range", volume_pattern, parse_volumes, geometry, "cell_volume_range_m3")
    volume_matches = list(re.finditer(volume_pattern, log_text, re.MULTILINE | re.IGNORECASE))
    if len(volume_matches) == 1:
        checks["cell_volumes"] = check_status(volume_matches[0], 4)
    elif len(volume_matches) > 1:
        report["ambiguous_fields"].append("cell_volumes_status")
    else:
        report["missing_fields"].append("cell_volumes_status")

    nonorth_pattern = rf"^\s*Mesh non-orthogonality Max:\s*{number}\s+average:\s*{number}\s*$"
    def parse_nonorth(match):
        return [finite_float(match.group(1)), finite_float(match.group(2))]
    extract("non_orthogonality", nonorth_pattern, parse_nonorth, geometry, "non_orthogonality_deg_max_average")

    for label, pattern, key in (
        ("boundary_openness", rf"^\s*Boundary openness\s*\(([^)]*)\)\s+(OK|Failed)\.?\s*$", "boundary_openness"),
        ("non_orthogonality_check", r"^\s*Non-orthogonality check (OK|Failed)\.?\s*$", "non_orthogonality"),
        ("boundary_definition", r"^\s*Boundary definition (OK|Failed)\.?\s*$", "boundary_definition"),
        ("cell_to_face_addressing", r"^\s*Cell to face addressing (OK|Failed)\.?\s*$", "cell_to_face_addressing"),
        ("point_usage", r"^\s*Point usage (OK|Failed)\.?\s*$", "point_usage"),
        ("upper_triangular_ordering", r"^\s*Upper triangular ordering (OK|Failed)\.?\s*$", "upper_triangular_ordering"),
        ("face_vertices", r"^\s*Face vertices (OK|Failed)\.?\s*$", "face_vertices"),
    ):
        target = geometry if label == "boundary_openness" else checks
        def parse_status_line(match, key=key, label=label):
            if label == "boundary_openness":
                values = [finite_float(value) for value in match.group(1).split()]
                if len(values) != 3:
                    raise ValueError("expected three components")
                checks[key] = match.group(2).lower()
                return values
            return match.group(1).lower()
        output_key = "boundary_openness_vector" if label == "boundary_openness" else key
        extract(label, pattern, parse_status_line, target, output_key)

    extract(
        "face_pyramids",
        r"^\s*Face pyramids (OK|Failed)\.?\s*$",
        lambda match: match.group(1).lower(),
        checks,
        "face_pyramids",
    )
    coupled_point_pattern = (
        rf"^\s*Coupled point location match\s*\(average\s+{number}\)\s+(OK|Failed)\.?\s*$"
    )
    def parse_coupled_point_location(match):
        geometry["coupled_point_location_average"] = finite_float(match.group(1))
        return match.group(2).lower()
    extract(
        "coupled_point_location",
        coupled_point_pattern,
        parse_coupled_point_location,
        checks,
        "coupled_point_location",
    )

    mesh_ok = list(re.finditer(r"^\s*Mesh OK\.\s*$", log_text, re.MULTILINE | re.IGNORECASE))
    failures = list(re.finditer(
        r"^\s*Failed\s+(\d+)\s+mesh checks?\.\s*$",
        log_text,
        re.MULTILINE | re.IGNORECASE,
    ))
    if len(mesh_ok) + len(failures) == 1:
        if mesh_ok:
            report["mesh_result"] = "mesh_ok"
        else:
            report["mesh_result"] = "checks_failed"
            report["failed_check_count"] = int(failures[0].group(1))
    elif len(mesh_ok) + len(failures) == 0:
        report["missing_fields"].append("mesh_result_marker")
    else:
        report["ambiguous_fields"].append("mesh_result_marker")

    failed_reported_checks = sorted(
        name for name, status in checks.items() if status == "failed"
    )
    if report["mesh_result"] == "mesh_ok" and failed_reported_checks:
        report["mesh_result"] = "unknown"
        report["ambiguous_fields"].append("mesh_result_consistency")
    elif report["mesh_result"] == "checks_failed" and "failed_check_count" in report:
        if report["failed_check_count"] == 0:
            report["invalid_fields"].append("failed_check_count")
        elif failed_reported_checks and len(failed_reported_checks) > report["failed_check_count"]:
            report["ambiguous_fields"].append("failed_check_count")

    for count_key in ("points", "faces", "cells", "boundary_patches", "regions"):
        value = counts.get(count_key)
        if value is not None and value <= 0:
            report["invalid_fields"].append(count_key)
    if counts.get("internal_faces") is not None and counts.get("faces") is not None:
        if counts["internal_faces"] > counts["faces"]:
            report["invalid_fields"].append("internal_faces")
    for key in ("max_cell_openness", "max_aspect_ratio", "max_skewness"):
        value = geometry.get(key)
        if value is not None and not math.isfinite(value):
            report["invalid_fields"].append(key)
    if "face_area_range_m2" in geometry:
        low, high = geometry["face_area_range_m2"]
        if low <= 0 or high < low:
            report["invalid_fields"].append("face_area_range_m2")
    if "cell_volume_range_m3" in geometry:
        low, high, total = geometry["cell_volume_range_m3"]
        if low <= 0 or high < low or total <= 0:
            report["invalid_fields"].append("cell_volume_range_m3")
    if "domain_bounding_box" in geometry:
        lower, upper = geometry["domain_bounding_box"]
        if any(low > high for low, high in zip(lower, upper)):
            report["invalid_fields"].append("domain_bounding_box")
    if counts.get("cells") is not None and all(
        cell_type in counts["cell_types"]
        for cell_type in ("hexahedra", "prisms", "wedges", "pyramids", "tet_wedges", "tetrahedra", "polyhedra")
    ):
        if sum(counts["cell_types"].values()) != counts["cells"]:
            report["invalid_fields"].append("cell_type_total")

    for key in ("missing_fields", "ambiguous_fields", "invalid_fields"):
        report[key] = sorted(set(report[key]))
    report["reported_check_failures"] = sorted(
        key for key, status in checks.items() if status == "failed"
    )
    if report["ambiguous_fields"]:
        report["parse_status"] = "ambiguous"
    elif report["missing_fields"] or report["invalid_fields"]:
        report["parse_status"] = "incomplete"
    else:
        report["parse_status"] = "complete"
    return report

def run_openfoam_cases(directory,*,timeout_seconds=3600,sync_results_directory=None,
                       simulation_id=None,sync_poll_interval_seconds=1.0,
                       sync_timeout_seconds=600,sync_max_field_bytes=256*1024*1024,
                       sync_max_snapshot_bytes=512*1024*1024,
                       sync_max_output_bytes=2*1024*1024*1024,sync_max_retries=3):
    """Opt-in external execution; never imply CFD convergence from process exit.

    When ``sync_results_directory`` is supplied, stable solver writes are
    exported and imported while ``simpleFoam`` runs. The result manifest is
    diagnostic data-integrity evidence and does not qualify convergence.
    """
    if type(timeout_seconds) is not int or not 60<=timeout_seconds<=86400:
        raise ValueError("timeout_seconds must be an integer in [60,86400]")
    root=Path(directory).resolve(strict=True)
    sync_root=None
    if sync_results_directory is not None:
        from .cfd_openfoam_runtime_sync import _SIMULATION_ID
        if simulation_id is None:
            simulation_id="run-"+uuid.uuid4().hex
        if type(simulation_id) is not str or _SIMULATION_ID.fullmatch(simulation_id) is None:
            raise ValueError("simulation_id must be a safe 1..128 character identifier")
        sync_candidate=Path(sync_results_directory)
        if sync_candidate.is_symlink() or (sync_candidate.exists() and not sync_candidate.is_dir()):
            raise ValueError("Synchronization output must be a regular directory")
        sync_root=sync_candidate.resolve(strict=False)
        if sync_root==root or sync_root.is_relative_to(root):
            raise ValueError("Synchronization output cannot be inside the OpenFOAM case bundle")
        if not (type(sync_poll_interval_seconds) in (int,float)
                and math.isfinite(sync_poll_interval_seconds)
                and 0.1<=sync_poll_interval_seconds<=60):
            raise ValueError("sync_poll_interval_seconds must be finite and in [0.1,60]")
        if type(sync_timeout_seconds) is not int or not 1<=sync_timeout_seconds<=3600:
            raise ValueError("sync_timeout_seconds must be an integer in [1,3600]")
        for name,value in (("sync_max_field_bytes",sync_max_field_bytes),
                           ("sync_max_snapshot_bytes",sync_max_snapshot_bytes),
                           ("sync_max_output_bytes",sync_max_output_bytes)):
            if type(value) is not int or value<=0:
                raise ValueError(f"{name} must be a positive integer")
        if type(sync_max_retries) is not int or not 1<=sync_max_retries<=10:
            raise ValueError("sync_max_retries must be an integer in [1,10]")
    elif simulation_id is not None:
        raise ValueError("simulation_id requires sync_results_directory")
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version")!=SCHEMA or set(manifest.get("evidence",{}))!={"1","2","3"}:
        raise ValueError("Incomplete OpenFOAM bundle")
    case_inputs=("system/blockMeshDict","system/controlDict","system/fvSchemes",
                 "system/fvSolution","constant/physicalProperties",
                 "constant/momentumTransport","0/U","0/p")
    expected_files={f"configuration_{cfg}/{relative}" for cfg in (1,2,3) for relative in case_inputs}
    if not isinstance(manifest.get("files"),dict) or set(manifest["files"])!=expected_files:
        raise ValueError("OpenFOAM bundle must bind the exact 24 generated case inputs")
    for relative,sha in manifest["files"].items():
        f=(root/relative).resolve(strict=True)
        if not f.is_relative_to(root) or hashlib.sha256(f.read_bytes()).hexdigest()!=sha:
            raise ValueError("Tampered generated solver file: "+relative)
    boundary_audits={}
    for cfg in (1,2,3):
        metadata=manifest["evidence"][str(cfg)]
        case_files={relative:(root/f"configuration_{cfg}"/relative).read_text(encoding="utf-8")
                    for relative in ("system/blockMeshDict","0/U","0/p")}
        audit=audit_openfoam_boundary_inputs(case_files,metadata)
        recorded=metadata.get("boundary_audit")
        if recorded is not None and recorded!=audit:
            raise ValueError(f"Boundary audit metadata mismatch for configuration {cfg}")
        boundary_audits[str(cfg)]=audit
    executables={}
    for name in ("blockMesh","checkMesh","simpleFoam"):
        path=shutil.which(name)
        if path is None:
            raise RuntimeError(name+" not found; install the targeted OpenFOAM release")
        executables[name]=path
    project=os.environ.get("WM_PROJECT")
    version=os.environ.get("WM_PROJECT_VERSION")
    if project!="OpenFOAM" or version!=FOUNDATION_RELEASE:
        raise RuntimeError(
            "Expected the OpenFOAM Foundation v10 environment "
            "(WM_PROJECT=OpenFOAM, WM_PROJECT_VERSION=10); source its etc/bashrc"
        )
    if sync_root is not None:
        if shutil.which("foamToVTK") is None:
            raise RuntimeError("foamToVTK not found; install the targeted OpenFOAM release")
        try:
            import vtk  # noqa: F401
        except ImportError as error:
            raise RuntimeError("pip install vtk to synchronize OpenFOAM result fields") from error
    results={}
    synchronization={}
    expected_build=None
    for cfg in (1,2,3):
        stages=[]
        workdir=root/f"configuration_{cfg}"
        for executable in ("blockMesh","checkMesh","simpleFoam"):
            log=workdir/f"{executable}.log"
            if executable=="simpleFoam" and sync_root is not None:
                from .cfd_openfoam_runtime_sync import OpenFOAMResultSynchronizer, run_solver_with_sync
                sync_root.mkdir(parents=True,exist_ok=True)
                case_file_hashes={relative:manifest["files"][f"configuration_{cfg}/{relative}"]
                                  for relative in case_inputs}
                configuration_hash=hashlib.sha256(json.dumps(
                    case_file_hashes,sort_keys=True,separators=(",", ":"),allow_nan=False
                ).encode("utf-8")).hexdigest()
                synchronizer=OpenFOAMResultSynchronizer(
                    workdir,
                    sync_root/simulation_id/f"configuration_{cfg}",
                    simulation_id=simulation_id,
                    configuration_hash=configuration_hash,
                    case_id=f"configuration_{cfg}",
                    expected_build=expected_build,
                    poll_interval_seconds=sync_poll_interval_seconds,
                    timeout_seconds=sync_timeout_seconds,
                    max_field_bytes=sync_max_field_bytes,
                    max_snapshot_bytes=sync_max_snapshot_bytes,
                    max_output_bytes=sync_max_output_bytes,
                    max_retries=sync_max_retries,
                )
                returncode=run_solver_with_sync(
                    [executables[executable]],cwd=workdir,log_path=log,
                    timeout_seconds=timeout_seconds,synchronizer=synchronizer,
                )
                result=subprocess.CompletedProcess([executables[executable]],returncode)
                sync_report=synchronizer.finish(solver_returncode=returncode,solver_log=log)
                synchronization[str(cfg)]=sync_report
            else:
                with log.open("x",encoding="utf-8") as output:
                    result=subprocess.run([executables[executable]],cwd=workdir,stdout=output,
                                          stderr=subprocess.STDOUT,timeout=timeout_seconds,check=False)
            log_bytes=log.read_bytes()
            log_text=log_bytes.decode("utf-8",errors="replace")
            banner=_foundation_v10_banner(log_text)
            stages.append({"program":executable,"returncode":result.returncode,
                           "log":str(log.relative_to(root)),
                           "log_sha256":hashlib.sha256(log_bytes).hexdigest(),
                           "openfoam":banner})
            if executable=="checkMesh":
                stages[-1]["mesh_quality_diagnostics"] = parse_openfoam_checkmesh_log(
                    log_text,
                    stages[-1]["log_sha256"],
                )
            if result.returncode:
                results[str(cfg)]={"status":"solver_failed","stages":stages}
                response={"status":"incomplete","cases":results,"boundary_audits":boundary_audits,
                          "warning":"Check logs and convergence; execution is not validation"}
                if sync_root is not None:
                    response.update({"simulation_id":simulation_id,"result_synchronization":synchronization})
                return response
            if not banner["is_foundation_v10"]:
                results[str(cfg)]={"status":"unsupported_release","stages":stages}
                return {"status":"incomplete","cases":results,"boundary_audits":boundary_audits,
                        "warning":"Expected an OpenFOAM Foundation v10 banner; later stages were not run"}
            if expected_build is None:
                expected_build=banner["build"]
            elif banner["build"]!=expected_build:
                results[str(cfg)]={"status":"inconsistent_build","stages":stages}
                return {"status":"incomplete","cases":results,"boundary_audits":boundary_audits,
                        "warning":"OpenFOAM build changed during the case set; later stages were not run"}
            if executable=="checkMesh":
                diagnostics=stages[-1]["mesh_quality_diagnostics"]
                if (diagnostics["parse_status"]!="complete"
                        or diagnostics["mesh_result"]!="mesh_ok"
                        or diagnostics["reported_check_failures"]):
                    case_status=("checkmesh_failed" if (
                        diagnostics["mesh_result"]=="checks_failed"
                        or diagnostics["reported_check_failures"]
                    )
                                 else "checkmesh_diagnostics_incomplete")
                    results[str(cfg)]={"status":case_status,"stages":stages}
                    response={"status":"incomplete","cases":results,
                              "boundary_audits":boundary_audits,
                              "solver_release":"OpenFOAM Foundation v10",
                              "solver_build":expected_build,
                              "warning":"checkMesh output was not a complete Mesh OK report; no project-specific quality thresholds were applied"}
                    if sync_root is not None:
                        response.update({"simulation_id":simulation_id,"result_synchronization":synchronization})
                    return response
        results[str(cfg)]={"status":"executed_requires_convergence_review","stages":stages}
    response={"status":"executed_requires_convergence_review","cases":results,
              "boundary_audits":boundary_audits,
              "solver_release":"OpenFOAM Foundation v10",
              "solver_build":expected_build,
              "executables":executables,
              "warning":"Review residuals, mass conservation, mesh sensitivity and physical validity"}
    if sync_root is not None:
        response["simulation_id"]=simulation_id
        response["result_synchronization"]=synchronization
        if any(item.get("status")!="results_synced" for item in synchronization.values()):
            response["status"]="incomplete"
            response["warning"]="OpenFOAM execution finished but result synchronization is incomplete; inspect the persisted sync manifests"
    return response
