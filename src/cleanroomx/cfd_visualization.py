"""Render actual external CFD VTK cell-center samples in three aligned panels.

Plots finite-thickness slabs, not interpolated CFD contours or CFD validation.
"""
from __future__ import annotations
import math
from pathlib import Path

from .cfd_vtk import _read_vtk

def render_cfd_cross_section(sources,output,*,axis,position_m,slab_thickness_m,field="speed"):
    if set(sources)!={1,2,3}: raise ValueError("Three VTK configurations required")
    if axis not in ("x","y","z"): raise ValueError("axis must be x, y or z")
    if field not in ("speed","contaminant"): raise ValueError("field must be speed or contaminant")
    if (type(position_m) not in (int,float) or not math.isfinite(position_m)
        or type(slab_thickness_m) not in (int,float)
        or not math.isfinite(slab_thickness_m) or slab_thickness_m<=0):
        raise ValueError("Finite slice coordinate and positive finite slab thickness required")
    try:
        import vtk
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("Plotting requires pip install vtk matplotlib") from exc
    dim="xyz".index(axis)
    other=[i for i in range(3) if i!=dim]
    datasets=[]
    for cfg in (1,2,3):
        grid=_read_vtk(Path(sources[cfg]))
        centers=vtk.vtkCellCenters()
        centers.SetInputData(grid)
        centers.Update()
        points=centers.GetOutput().GetPoints()
        fields=grid.GetCellData()
        arr=fields.GetArray("U" if field=="speed" else "T")
        expected=3 if field=="speed" else 1
        if arr is None or arr.GetNumberOfComponents()!=expected:
            raise ValueError(f"Configuration {cfg}: required field missing or invalid")
        samples=[]
        for i in range(grid.GetNumberOfCells()):
            p=points.GetPoint(i)
            if abs(p[dim]-position_m)>slab_thickness_m/2: continue
            v=math.sqrt(sum(x*x for x in arr.GetTuple3(i))) if field=="speed" else float(arr.GetTuple1(i))
            if not math.isfinite(v): raise ValueError("Non-finite visualized field")
            samples.append((p[other[0]],p[other[1]],v))
        if not samples: raise ValueError(f"No cells within requested slab for Configuration {cfg}")
        datasets.append(samples)
    vmin=min(row[2] for samples in datasets for row in samples)
    vmax=max(row[2] for samples in datasets for row in samples)
    destination=Path(output)
    if destination.exists(): raise FileExistsError("Plot output already exists")
    if destination.suffix.lower()!=".png": raise ValueError("Plot must be PNG")
    fig,axes=plt.subplots(1,3,figsize=(13,4),constrained_layout=True)
    try:
        for cfg,(ax,points) in enumerate(zip(axes,datasets),start=1):
            dots=ax.scatter([p[0] for p in points],[p[1] for p in points],
                            c=[p[2] for p in points],vmin=vmin,vmax=vmax,s=17)
            ax.set_title(f"Configuration {cfg} | {len(points)} cells")
            ax.set_xlabel("xyz"[other[0]]+" (m)")
            ax.set_ylabel("xyz"[other[1]]+" (m)")
            ax.set_aspect("equal",adjustable="box")
        fig.colorbar(dots,ax=axes,
                     label="Speed (m/s)" if field=="speed" else "T (user-defined units)")
        fig.suptitle(f"Sampled CFD cell-centers: {axis}={position_m:g} m, slab {slab_thickness_m:g} m")
        destination.parent.mkdir(parents=True,exist_ok=True)
        fig.savefig(destination,dpi=160)
    finally:
        plt.close(fig)
    return {"status":"sampled_cells_visualized_not_cfd_validation","path":str(destination),
            "field":field,"axis":axis,"position_m":position_m,"slab_thickness_m":slab_thickness_m,
            "sample_count":{str(i):len(s) for i,s in enumerate(datasets,1)},
            "range":[vmin,vmax]}
