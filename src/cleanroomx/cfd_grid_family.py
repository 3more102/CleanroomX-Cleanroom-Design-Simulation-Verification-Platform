"""Build a three-resolution, three-ventilation-design OpenFOAM grid family.

Generation only: never labels case files as converged physical simulations.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil

from .cfd_openfoam import MAX_CELLS, build_openfoam_files, validate_openfoam_spec

SCHEMA="cleanroomx.cfd-grid-family.v1"
LEVELS=("coarse","medium","fine")


def validate_family_spec(data):
    if type(data) is not dict or set(data)!={"schema_version","base_case","mesh_levels"}:
        raise ValueError("Grid family requires schema_version, base_case, mesh_levels")
    if data["schema_version"]!=SCHEMA:
        raise ValueError("Unsupported grid family schema")
    validate_openfoam_spec(data["base_case"])
    levels=data["mesh_levels"]
    if type(levels) is not dict or set(levels)!=set(LEVELS):
        raise ValueError("mesh_levels must contain coarse, medium and fine")
    for name in LEVELS:
        mesh=levels[name]
        if type(mesh) is not list or len(mesh)!=3 or any(
            type(value) is not int or not 6<=value<=80 for value in mesh
        ) or math.prod(mesh)>MAX_CELLS:
            raise ValueError(f"{name}: mesh axis 6..80 and total <= {MAX_CELLS} required")
    for smaller,larger in zip(LEVELS,LEVELS[1:]):
        if any(x>=y for x,y in zip(levels[smaller],levels[larger])):
            raise ValueError("All three mesh axes must increase strictly coarse to fine")
    return data


def generate_grid_family(data, directory):
    """Create all nine deterministic cases and SHA-256 bind generated inputs."""
    validate_family_spec(data)
    output=Path(directory)
    if output.exists():
        raise FileExistsError("Refuse to overwrite existing grid family")
    canonical=json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    manifest={
        "schema_version":SCHEMA,
        "family_spec_sha256":hashlib.sha256(canonical.encode()).hexdigest(),
        "status":"generated_not_executed",
        "case_inputs":{},
        "files":{},
    }
    cases={}
    for cfg in (1,2,3):
        for level in LEVELS:
            case_spec=dict(data["base_case"],mesh_cells=list(data["mesh_levels"][level]))
            files,meta=build_openfoam_files(case_spec,cfg)
            directory_name=f"configuration_{cfg}/{level}"
            cases[directory_name]=files
            manifest["case_inputs"][directory_name]=meta
    output.mkdir(parents=True,exist_ok=False)
    try:
        for dirname,files in cases.items():
            for relative,content in files.items():
                target=output/dirname/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                with target.open("x",encoding="utf-8",newline="\n") as file:
                    file.write(content)
                manifest["files"][f"{dirname}/{relative}"]=hashlib.sha256(content.encode()).hexdigest()
        with (output/"manifest.json").open("x",encoding="utf-8") as file:
            json.dump(manifest,file,indent=2,sort_keys=True,allow_nan=False)
    except BaseException:
        shutil.rmtree(output)
        raise
    return manifest
