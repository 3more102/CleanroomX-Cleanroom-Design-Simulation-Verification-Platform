"""Interactive 3D VTK review of recorded, non-certified OpenFOAM multizone data.

The scene plots actual cell-centred p/U, modeled room bounds and bounded
streamlines derived from the *same* recorded SIMPLE iteration. It never
manufactures interior samples, transient frames or physical particle physics.
VTK is an optional dependency; the core CleanroomX GUI remains usable without it.
"""
from __future__ import annotations

import copy
import math
import queue
import threading

from .cfd_particle_ensemble import inject_recorded_particle_ensemble
from .cfd_particle_refinement import (
    analyze_particle_timestep_refinement, export_particle_timestep_refinement,
)
from .cfd_particle_diagnostics import (
    analyze_particle_trajectories, export_particle_trajectory_diagnostics,
)
from .cfd_particles import (
    PARTICLE_SCHEMA, MAX_PARTICLES, trace_screening_particle,
    export_screening_particles, particle_positions_at_elapsed,
)
from .cfd_streamlines import (
    ComputedVelocityGrid, SOURCE_SCHEMA, TRACE_SCHEMA, trace_computed_streamline,
    export_computed_streamlines,
)

MAX_3D_CELLS = 100_000
MAX_3D_TRACES = 20


def _vtk():
    try:
        import vtk
    except ImportError as exc:
        raise RuntimeError('Interactive 3D CFD requires: pip install -e ".[cfd]"') from exc
    return vtk


def _report_cells(report):
    if report.get("schema") != SOURCE_SCHEMA:
        raise ValueError("3D viewer requires a recorded computed multizone result")
    cells = report.get("cells")
    if not isinstance(cells, list) or not 0 < len(cells) <= MAX_3D_CELLS:
        raise ValueError("3D viewer requires one to 100000 recorded CFD cells")
    return cells


def _finite_triplet(values, label):
    if not isinstance(values, (tuple, list)) or len(values) != 3:
        raise ValueError(f"{label} requires 3 numeric components")
    if any(type(x) not in (float, int) or not math.isfinite(x) for x in values):
        raise ValueError(f"{label} components must be finite")
    return [float(x) for x in values]


def select_recorded_cells(report, *, room_id="all", plane_axis="all",
                          plane_position_m=None):
    """Filter actual CFD centres; never resample, interpolate, or fill gaps.

    The plane includes exactly the recorded cell layer whose centre lies
    strictly within half a grid pitch of the requested coordinate.
    """
    cells = _report_cells(report)
    grid = ComputedVelocityGrid(report)
    rooms = {cell["room_id"] for cell in cells}
    if type(room_id) is not str or (room_id != "all" and room_id not in rooms):
        raise ValueError("Select an existing computed room or all rooms")
    if plane_axis not in ("all", "x", "y", "z"):
        raise ValueError("Plane axis must be all, x, y, or z")
    if plane_axis == "all":
        if plane_position_m is not None:
            raise ValueError("Plane position must be omitted for all-axis view")
        return [c for c in cells if room_id == "all" or c["room_id"] == room_id]
    if type(plane_position_m) not in (int, float) or not math.isfinite(plane_position_m):
        raise ValueError("Plane position must be a finite coordinate in metres")
    index = "xyz".index(plane_axis)
    half_pitch = grid.pitch[index] / 2
    selected = [
        cell for cell in cells
        if (room_id == "all" or cell["room_id"] == room_id)
        and abs(cell["center_m"][index] - plane_position_m) < half_pitch - 1e-8
    ]
    if not selected:
        raise ValueError("No computed cells on the selected room/plane layer")
    return selected


def seed_streamline_from_displayed_point(
    report, traces, point_id, *, room_id="all", plane_axis="all",
    plane_position_m=None, max_integration_s=20.0,
):
    """Seed only at an actual *displayed* solver-cell centre.

    No arbitrary screen/world location becomes a fluid seed. Existing
    trajectories must match the same run receipt and selected iteration.
    Returns a new provenance-tagged steady streamline without mutating input.
    """
    if type(point_id) is not int:
        raise ValueError("Recorded point ID must be an integer")
    if not isinstance(traces, list) or len(traces) >= MAX_3D_TRACES:
        raise ValueError("At most 20 recorded steady traces may be displayed")
    # Reject stale/mixed-source trajectories before adding another one.
    if traces:
        computed_trace_polydata(report, traces)
    samples=select_recorded_cells(
        report,room_id=room_id,plane_axis=plane_axis,
        plane_position_m=plane_position_m)
    if not 0 <= point_id < len(samples):
        raise ValueError("Picked point is not in the displayed computed field")
    return trace_computed_streamline(
        report,samples[point_id]["center_m"],
        max_integration_s=max_integration_s)


def seed_particle_from_displayed_point(
    report, particles, point_id, *, room_id="all", plane_axis="all",
    plane_position_m=None, diameter_um=5.0, particle_density_kg_m3=1000.0,
    max_time_s=2.0,
):
    """Particle *screening* from an existing displayed fluid cell, not the air line."""
    if type(point_id) is not int:
        raise ValueError("Recorded particle seed ID must be an integer")
    if not isinstance(particles,list) or len(particles)>=MAX_PARTICLES:
        raise ValueError("At most 20 particle screening paths may be displayed")
    if particles:
        computed_particle_polydata(report,particles)
    samples=select_recorded_cells(report,room_id=room_id,
        plane_axis=plane_axis,plane_position_m=plane_position_m)
    if not 0<=point_id<len(samples):
        raise ValueError("Particle seed must be a visible recorded CFD fluid cell")
    return trace_screening_particle(report,samples[point_id]["center_m"],
        diameter_um=diameter_um,particle_density_kg_m3=particle_density_kg_m3,
        max_time_s=max_time_s)


def computed_particle_polydata(report, particles):
    """VTK line geometry from physically parameterized frozen-field screening.

    Distinct from gold steady streamlines: lime paths mark particle screening.
    No new fluid velocity, deposition, or transient solver state is created.
    """
    vtk=_vtk()
    if type(particles) is not list or len(particles)>MAX_PARTICLES:
        raise ValueError("At most 20 particle screening tracks may be visualized")
    grid=ComputedVelocityGrid(report)
    source=report.get("provenance",{})
    points=vtk.vtkPoints()
    points.SetDataTypeToDouble()
    lines=vtk.vtkCellArray()
    elapsed=vtk.vtkDoubleArray()
    elapsed.SetName("Particle frozen-field elapsed time (s)")
    for path in particles:
        if (path.get("schema")!=PARTICLE_SCHEMA or
            path.get("source_iteration")!=report.get("time_name") or
            path.get("source_manifest_sha256")!=source.get("manifest_sha256") or
            path.get("source_run_receipt_sha256")!=source.get("run_receipt_sha256")):
            raise ValueError("Particle screening path does not match recorded CFD run")
        values=path.get("points")
        if not isinstance(values,list) or not 1<=len(values)<=10002:
            raise ValueError("Invalid particle screening trajectory")
        ids=[]
        previous=None
        tprev=-1.0
        for item in values:
            xyz=_finite_triplet(item["xyz_m"],"particle position")
            t=item["elapsed_particle_s"]
            if type(t) not in (float,int) or not math.isfinite(t) or t<tprev:
                raise ValueError("Particle elapsed time must be monotone")
            gas=grid.cell_at(xyz)
            if gas is None or (previous is not None and
                              not grid.connected_segment(previous,xyz)):
                raise ValueError("Particle track crosses an uncomputed or solid cell")
            recorded=_finite_triplet(item["recorded_gas_velocity_m_s"],"recorded gas U")
            if any(not math.isclose(recorded[i],gas[0][i],rel_tol=1e-8,abs_tol=1e-8)
                   for i in range(3)):
                raise ValueError("Particle gas U differs from recorded CFD cell")
            ids.append(points.InsertNextPoint(*xyz))
            elapsed.InsertNextValue(float(t))
            previous=xyz
            tprev=float(t)
        if len(ids)>1:
            lines.InsertNextCell(len(ids))
            for idx in ids:
                lines.InsertCellPoint(idx)
    geometry=vtk.vtkPolyData()
    geometry.SetPoints(points)
    geometry.SetLines(lines)
    geometry.GetPointData().AddArray(elapsed)
    return geometry


def _recorded_cell_actor(renderer):
    """Find the ONLY rendered actor with recorded solver U point arrays."""
    collection=renderer.GetActors()
    collection.InitTraversal()
    found=None
    for _ in range(collection.GetNumberOfItems()):
        actor=collection.GetNextActor()
        mapper=actor.GetMapper() if actor else None
        data=mapper.GetInput() if mapper else None
        if data is None or not data.IsA("vtkPolyData"):
            continue
        if data.GetPointData().GetArray("Computed U (m/s)") is not None:
            if found is not None:
                raise ValueError("Multiple ambiguous computed CFD point actors")
            found=actor
    if found is None:
        raise ValueError("Computed CFD point actor is unavailable")
    return found


def pick_recorded_solver_point(renderer, display_x, display_y):
    """VTK point-pick strictly from colored cell-centre actor, not CAD/wires."""
    vtk=_vtk()
    if (type(display_x) not in (int,float) or
        type(display_y) not in (int,float) or
        not math.isfinite(display_x) or not math.isfinite(display_y)):
        raise ValueError("VTK display coordinates must be finite")
    actor=_recorded_cell_actor(renderer)
    picker=vtk.vtkPointPicker()
    picker.PickFromListOn()
    picker.AddPickList(actor)
    picker.SetTolerance(0.02)
    picked=picker.Pick(float(display_x),float(display_y),0,renderer)
    point_id=picker.GetPointId()
    if not picked or point_id < 0:
        raise ValueError("Click directly on a colored recorded fluid-cell centre")
    return int(point_id)


def computed_field_polydata(report, *, room_id="all", plane_axis="all",
                            plane_position_m=None):
    """Construct actual 3D points with recorded pressure and velocity vectors."""
    vtk = _vtk()
    cells = select_recorded_cells(report,room_id=room_id,plane_axis=plane_axis,
                                  plane_position_m=plane_position_m)
    points = vtk.vtkPoints()
    points.SetDataTypeToDouble()
    verts = vtk.vtkCellArray()
    speeds = vtk.vtkDoubleArray()
    speeds.SetName("Computed speed (m/s)")
    pressures = vtk.vtkDoubleArray()
    pressures.SetName("Computed pressure relative (Pa)")
    velocity = vtk.vtkDoubleArray()
    velocity.SetName("Computed U (m/s)")
    velocity.SetNumberOfComponents(3)
    for cell in cells:
        xyz = _finite_triplet(cell["center_m"], "cell centre")
        uvw = _finite_triplet(cell["velocity_m_s"], "computed velocity")
        p = cell["pressure_pa_relative_to_reference"]
        if type(p) not in (float, int) or not math.isfinite(p):
            raise ValueError("Computed cell pressure must be finite")
        pid = points.InsertNextPoint(*xyz)
        verts.InsertNextCell(1)
        verts.InsertCellPoint(pid)
        velocity.InsertNextTuple(uvw)
        speeds.InsertNextValue(math.sqrt(sum(u*u for u in uvw)))
        pressures.InsertNextValue(float(p))
    output = vtk.vtkPolyData()
    output.SetPoints(points)
    output.SetVerts(verts)
    output.GetPointData().AddArray(velocity)
    output.GetPointData().AddArray(speeds)
    output.GetPointData().AddArray(pressures)
    return output


def computed_trace_polydata(report, traces):
    """Reject traces from other runs/iterations and wall-crossing polylines."""
    vtk = _vtk()
    _report_cells(report)
    if not isinstance(traces, list) or len(traces) > MAX_3D_TRACES:
        raise ValueError("3D viewer accepts at most 20 recorded traces")
    grid = ComputedVelocityGrid(report)
    origin = report.get("provenance", {})
    points = vtk.vtkPoints()
    points.SetDataTypeToDouble()
    lines = vtk.vtkCellArray()
    speed = vtk.vtkDoubleArray()
    speed.SetName("Computed trace speed (m/s)")
    for path in traces:
        if (path.get("schema") != TRACE_SCHEMA or
            path.get("source_iteration") != report.get("time_name") or
            path.get("source_manifest_sha256") != origin.get("manifest_sha256") or
            path.get("source_run_receipt_sha256") != origin.get("run_receipt_sha256")):
            raise ValueError("3D traces must originate in this recorded CFD iteration")
        samples = path.get("points")
        if not isinstance(samples, list) or not 1 <= len(samples) <= 10001:
            raise ValueError("Invalid recorded streamline point count")
        trace_points = []
        last_t = -1.
        previous = None
        for sample in samples:
            xyz = _finite_triplet(sample["xyz_m"], "trace coordinate")
            time = sample["integration_parameter_s"]
            if type(time) not in (float, int) or not math.isfinite(time) or time < last_t:
                raise ValueError("Streamline integration parameter must be monotone")
            record = grid.cell_at(xyz)
            if record is None:
                raise ValueError("Streamline point lies outside computed fluid")
            if previous is not None and not grid.connected_segment(previous, xyz):
                raise ValueError("Streamline segment crosses an unsolved cell")
            actual = math.sqrt(sum(u*u for u in record[0]))
            if not math.isclose(actual, float(sample["speed_m_s"]), rel_tol=1e-8, abs_tol=1e-8):
                raise ValueError("Streamline speed differs from recorded solver cell")
            pid = points.InsertNextPoint(*xyz)
            speed.InsertNextValue(actual)
            trace_points.append(pid)
            previous = xyz
            last_t = float(time)
        if len(trace_points) > 1:
            lines.InsertNextCell(len(trace_points))
            for pid in trace_points:
                lines.InsertCellPoint(pid)
    output = vtk.vtkPolyData()
    output.SetPoints(points)
    output.SetLines(lines)
    output.GetPointData().AddArray(speed)
    return output


def sampled_velocity_glyph_actor(report, *, max_arrows=250,
                                 room_id="all", plane_axis="all", plane_position_m=None):
    """3D glyphs from sampled *recorded* velocity components, never guessed flows.

    A constant visual scale factor makes arrows readable without implying
    physical displacement. Sampling is deterministic and limited for display.
    """
    vtk = _vtk()
    cells = select_recorded_cells(report,room_id=room_id,plane_axis=plane_axis,
                                  plane_position_m=plane_position_m)
    if type(max_arrows) is not int or not 1 <= max_arrows <= 2000:
        raise ValueError("max_arrows must be an integer from 1 to 2000")
    grid = ComputedVelocityGrid(report)
    pitch = grid.pitch
    stride = max(1, math.ceil(len(cells)/max_arrows))
    sampled = vtk.vtkPolyData()
    points = vtk.vtkPoints()
    points.SetDataTypeToDouble()
    vectors = vtk.vtkDoubleArray()
    vectors.SetNumberOfComponents(3)
    vectors.SetName("Computed U (m/s)")
    maximum = 0.0
    for cell in cells[::stride]:
        uvw = _finite_triplet(cell["velocity_m_s"], "computed velocity")
        magnitude = math.sqrt(sum(u*u for u in uvw))
        if magnitude <= 1e-12:
            continue
        points.InsertNextPoint(*_finite_triplet(cell["center_m"], "cell centre"))
        vectors.InsertNextTuple(uvw)
        maximum = max(maximum, magnitude)
    sampled.SetPoints(points)
    sampled.GetPointData().SetVectors(vectors)
    arrow = vtk.vtkArrowSource()
    glyph = vtk.vtkGlyph3D()
    glyph.SetInputData(sampled)
    glyph.SetSourceConnection(arrow.GetOutputPort())
    glyph.SetVectorModeToUseVector()
    glyph.SetScaleModeToScaleByVector()
    glyph.OrientOn()
    glyph.SetScaleFactor(min(pitch)*0.7/max(maximum,1e-12))
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(glyph.GetOutputPort())
    mapper.ScalarVisibilityOff()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(.83, .94, 1.0)
    actor.GetProperty().SetOpacity(.80)
    return actor


def build_multizone_vtk_renderer(report, traces, *, field="speed", vectors=True,
                                 room_id="all", plane_axis="all", plane_position_m=None,
                                 particles=None, field_points=True):
    """VTK renderer with solver-derived field samples, line paths and room outlines.

    No OpenGL context is opened here, so testing does not require a display.
    """
    vtk = _vtk()
    data = computed_field_polydata(report,room_id=room_id,plane_axis=plane_axis,
                                   plane_position_m=plane_position_m)
    trajectories = computed_trace_polydata(report, traces)
    particles_geometry=computed_particle_polydata(report,particles or [])
    if field not in ("speed", "pressure"):
        raise ValueError("Select speed or pressure for the 3D field")
    if type(field_points) is not bool:
        raise ValueError("Field point visibility must be a boolean")
    name = ("Computed speed (m/s)" if field == "speed"
            else "Computed pressure relative (Pa)")
    array = data.GetPointData().GetArray(name)
    low, high = array.GetRange()
    if not math.isfinite(low) or not math.isfinite(high):
        raise ValueError("Computed 3D data range must be finite")
    if high <= low:
        high = low + max(1e-9, abs(low)*1e-9)
    lookup = vtk.vtkLookupTable()
    lookup.SetNumberOfTableValues(256)
    lookup.SetHueRange(0.67, 0.0)
    lookup.SetRange(low, high)
    lookup.Build()
    renderer = vtk.vtkRenderer()
    renderer.SetBackground(0.06, 0.085, 0.13)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(data)
    mapper.SetScalarModeToUsePointFieldData()
    mapper.SelectColorArray(name)
    mapper.SetScalarRange(low, high)
    mapper.SetLookupTable(lookup)
    mapper.ScalarVisibilityOn()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetPointSize(4)
    actor.SetVisibility(field_points)
    renderer.AddActor(actor)

    trajectory_mapper = vtk.vtkPolyDataMapper()
    trajectory_mapper.SetInputData(trajectories)
    trajectory_mapper.ScalarVisibilityOff()
    paths_actor = vtk.vtkActor()
    paths_actor.SetMapper(trajectory_mapper)
    paths_actor.GetProperty().SetColor(1.0, .80, .25)
    paths_actor.GetProperty().SetLineWidth(3.0)
    renderer.AddActor(paths_actor)
    particle_mapper=vtk.vtkPolyDataMapper()
    particle_mapper.SetInputData(particles_geometry)
    particle_mapper.ScalarVisibilityOff()
    particle_actor=vtk.vtkActor()
    particle_actor.SetMapper(particle_mapper)
    particle_actor.GetProperty().SetColor(.30,1.0,.42)
    particle_actor.GetProperty().SetLineWidth(3.0)
    renderer.AddActor(particle_actor)
    if type(vectors) is not bool:
        raise ValueError("vectors must be a boolean")
    if vectors:
        renderer.AddActor(sampled_velocity_glyph_actor(
            report,room_id=room_id,plane_axis=plane_axis,
            plane_position_m=plane_position_m))


    # Room outlines represent input design geometry, never inferred CFD isosurfaces.
    rooms = report.get("geometry", {})
    if not isinstance(rooms, dict):
        raise ValueError("Recorded geometry must contain room bounds")
    for rid, room in rooms.items():
        if room_id != "all" and rid != room_id:
            continue
        values = [room[k] for k in
                  ("x_m", "y_m", "floor_elevation_m", "length_m", "width_m", "height_m")]
        if any(type(v) not in (float, int) or not math.isfinite(v) for v in values):
            raise ValueError(f"Invalid bounds for modeled room {rid}")
        x, y, z, length, width, height = values
        if min(length, width, height) <= 0:
            raise ValueError("Room dimensions must be positive")
        cube = vtk.vtkCubeSource()
        cube.SetBounds(x,x+length,y,y+width,z,z+height)
        outline = vtk.vtkOutlineFilter()
        outline.SetInputConnection(cube.GetOutputPort())
        outline_mapper = vtk.vtkPolyDataMapper()
        outline_mapper.SetInputConnection(outline.GetOutputPort())
        wire = vtk.vtkActor()
        wire.SetMapper(outline_mapper)
        wire.GetProperty().SetColor(.7,.76,.83)
        wire.GetProperty().SetOpacity(.42)
        renderer.AddActor(wire)

    scalar_bar = vtk.vtkScalarBarActor()
    scalar_bar.SetLookupTable(lookup)
    scalar_bar.SetTitle(name)
    scalar_bar.SetNumberOfLabels(5)
    scalar_bar.SetMaximumWidthInPixels(110)
    renderer.AddViewProp(scalar_bar)
    annotation = vtk.vtkTextActor()
    annotation.SetInput(
        f"Recorded {data.GetNumberOfPoints()} cells | iteration {report.get('time_name')} | "
        f"room {room_id} | plane {plane_axis}"
        + ("" if plane_axis=="all" else f"={plane_position_m:g} m")
        + f"\n{len(particles or [])} numerical particle paths"
        + (" | field cells hidden" if not field_points else "")
        + " | GOLD=steady U | GREEN=one-way particle screening (not certified)")
    annotation.SetDisplayPosition(15, 16)
    annotation.GetTextProperty().SetColor(.98,.98,.98)
    annotation.GetTextProperty().SetFontSize(15)
    renderer.AddViewProp(annotation)
    renderer.ResetCamera()
    return renderer


def set_recorded_view_camera(renderer, preset="iso"):
    """Camera-only presets; geometry and all numerical field values are unchanged."""
    if preset not in ("iso","top","front"):
        raise ValueError("Camera preset must be iso, top or front")
    bounds=renderer.ComputeVisiblePropBounds()
    center=[(bounds[2*i]+bounds[2*i+1])/2 for i in range(3)]
    span=max(bounds[2*i+1]-bounds[2*i] for i in range(3))
    direction={"iso":(1.,-1.3,1.),"top":(0.,0.,2.),"front":(0.,-2.,0.)}[preset]
    camera=renderer.GetActiveCamera()
    camera.SetFocalPoint(*center)
    camera.SetPosition(*(center[i]+direction[i]*span for i in range(3)))
    camera.SetViewUp(*( (0.,1.,0.) if preset=="top" else (0.,0.,1.) ))
    renderer.ResetCamera()
    renderer.ResetCameraClippingRange()


def open_multizone_vtk_window(parent, report, traces, *, case_directory=None):
    """Open interactive 3D with robust support for pip wheels lacking VTK/Tk.

    Prefer embedded vtkTkRenderWindowInteractor when the native Tk plugin is
    installed. Otherwise open a genuine *independent* VTK render window and
    keep Tk controls responsive by polling native events via Tk's event loop.
    This fallback does not require libvtkRenderingTk.
    """
    import tkinter as tk
    from tkinter import ttk
    from .gui_lifecycle import protect_tk_lifecycle

    vtk = _vtk()
    # Validate the complete recorded scene *before* opening a native window.
    renderer = build_multizone_vtk_renderer(report, traces)
    set_recorded_view_camera(renderer,"iso")
    window = tk.Toplevel(parent)
    protect_tk_lifecycle(window)
    window.title("CleanroomX | Recorded CFD 3D controls")
    window.geometry("1120x760")
    window.minsize(620, 260)
    render_window = vtk.vtkRenderWindow()
    render_window.SetMultiSamples(0)
    render_window.SetWindowName("CleanroomX | Computed OpenFOAM 3D")
    field_var = tk.StringVar(value="speed")
    arrows_var = tk.BooleanVar(value=True)
    field_points_var = tk.BooleanVar(value=True)
    camera_var = tk.StringVar(value="iso")
    click_seed_var = tk.BooleanVar(value=False)
    particle_mode_var = tk.BooleanVar(value=False)
    particle_diameter_var = tk.StringVar(value="5")
    particle_density_var = tk.StringVar(value="1000")
    particle_time_var = tk.StringVar(value="2")
    ensemble_count_var = tk.StringVar(value="4")
    ensemble_status = tk.StringVar(
        value="Select a room/layer to seed distinct recorded CFD cells (geometric, not statistical).")
    ensemble_state = {"busy":False,"poll_id":None}
    ensemble_events = queue.Queue()
    source_mode_var = tk.BooleanVar(value=False)
    source_panel = [None]
    mesh_var = tk.BooleanVar(value=False)
    mesh_events = queue.Queue()
    mesh_state = {"busy":False,"dataset":None,"poll_id":None}
    playback_var = tk.DoubleVar(value=0.)
    playback_status = tk.StringVar(value="Particle playback shows recorded sample vertices only")
    playback_state = {"playing":False, "after_id":None}
    particles = []
    displayed_selection = {"room_id":"all","plane_axis":"all","plane_position_m":None}
    room_var = tk.StringVar(value="all")
    plane_var = tk.StringVar(value="all")
    plane_position_var = tk.StringVar(value="")
    initial_convergence=("solver-reported convergence" if report.get("solver_reported_convergence")
                         else "NOT CONVERGED - engineering review required")
    view_status = tk.StringVar(value=f"Recorded cells | {initial_convergence}")

    mode = "native"
    widget = None
    after_id = None
    interactor = None
    try:
        heading = ttk.Frame(window,padding=8)
        heading.pack(fill="x")
        ttk.Label(
            heading,text="Recorded solver p/U | 3D room outlines | steady streamlines (not particles)"
        ).pack(side="left")
        controls = ttk.Frame(window,padding=(8,0,8,8))
        controls.pack(fill="x")
        ttk.Label(controls,text="Field:").pack(side="left")
        field_control = ttk.Combobox(
            controls,textvariable=field_var,values=("speed","pressure"),
            state="readonly",width=12)
        field_control.pack(side="left",padx=5)
        arrows_control = ttk.Checkbutton(
            controls,text="Computed U arrows",variable=arrows_var)
        arrows_control.pack(side="left",padx=12)
        field_points_control=ttk.Checkbutton(controls,text="Recorded cells",variable=field_points_var)
        field_points_control.pack(side="left",padx=8)
        ttk.Label(controls,text="Camera:").pack(side="left",padx=(10,3))
        camera_control=ttk.Combobox(controls,textvariable=camera_var,values=("iso","top","front"),state="readonly",width=7)
        camera_control.pack(side="left")
        instructions = tk.StringVar(value="Rotate: drag | zoom: wheel | pan: Shift+drag")
        ttk.Label(controls,textvariable=instructions).pack(side="right")
        selection=ttk.Frame(window,padding=(8,0,8,8))
        selection.pack(fill="x")
        ttk.Label(selection,text="Room:").pack(side="left")
        room_control=ttk.Combobox(
            selection,textvariable=room_var,
            values=("all", *tuple(sorted({c["room_id"] for c in report["cells"]}))),
            state="readonly",width=15)
        room_control.pack(side="left",padx=4)
        ttk.Label(selection,text="Plane:").pack(side="left")
        plane_control=ttk.Combobox(
            selection,textvariable=plane_var,values=("all","x","y","z"),
            state="readonly",width=5)
        plane_control.pack(side="left",padx=4)
        ttk.Label(selection,text="Coordinate (m):").pack(side="left")
        ttk.Entry(selection,textvariable=plane_position_var,width=12).pack(
            side="left",padx=4)
        particle_controls=ttk.Frame(window,padding=(8,0,8,8))
        particle_controls.pack(fill="x")
        ttk.Checkbutton(
            particle_controls,text="One-way particle screening",variable=particle_mode_var
        ).pack(side="left",padx=3)
        ttk.Label(particle_controls,text="Diameter (um):").pack(side="left")
        ttk.Entry(particle_controls,textvariable=particle_diameter_var,width=6).pack(
            side="left",padx=4)
        ttk.Label(particle_controls,text="Particle density (kg/m3):").pack(side="left")
        ttk.Entry(particle_controls,textvariable=particle_density_var,width=7).pack(
            side="left",padx=4)
        ttk.Label(particle_controls,text="Elapsed (s):").pack(side="left")
        ttk.Entry(particle_controls,textvariable=particle_time_var,width=6).pack(
            side="left",padx=4)
        ttk.Label(particle_controls,
            text="Gold: air streamlines | Green: inertial particle screening").pack(
            side="right",padx=3)
        ensemble_controls=ttk.Frame(window,padding=(8,0,8,8))
        ensemble_controls.pack(fill="x")
        ttk.Label(ensemble_controls,text="Recorded-cell multi-injection:").pack(side="left")
        ttk.Label(ensemble_controls,text="New seeds").pack(side="left",padx=(10,3))
        ttk.Entry(ensemble_controls,textvariable=ensemble_count_var,width=5).pack(
            side="left")
        ttk.Label(
            ensemble_controls,textvariable=ensemble_status,
            wraplength=700).pack(side="right",padx=8)
        source_controls=ttk.Frame(window,padding=(8,0,8,8))
        source_controls.pack(fill="x")
        ttk.Checkbutton(source_controls,text="Pick source in 3D",variable=source_mode_var).pack(side="left")
        ttk.Label(source_controls,text="Magenta: enabled sources | Green: full computed paths; markers follow release time").pack(side="right")
        mesh_controls=ttk.Frame(window,padding=(8,0,8,8))
        mesh_controls.pack(fill="x")
        timeline_controls=ttk.Frame(window,padding=(8,0,8,8))
        timeline_controls.pack(fill="x")
        timeline_label=tk.StringVar(value="Particle elapsed time (s):")
        ttk.Label(timeline_controls,textvariable=timeline_label).pack(side="left")
        slider=tk.Scale(
            timeline_controls,from_=0,to=2,resolution=.01,orient="horizontal",
            length=300,showvalue=True,variable=playback_var)
        slider.pack(side="left",padx=5)
        ttk.Label(timeline_controls,textvariable=playback_status).pack(
            side="left",padx=10)
        ttk.Label(window,textvariable=view_status).pack(fill="x",padx=8)
        holder=ttk.Frame(window)
        holder.pack(fill="both",expand=True)

        # PyPI VTK wheels can expose the Python Tk class WITHOUT shipping
        # libvtkRenderingTk. A TclError is a normal capability-detection
        # outcome; it must not make the whole CFD viewer unavailable.
        try:
            from vtkmodules.tk.vtkTkRenderWindowInteractor import vtkTkRenderWindowInteractor
            widget = vtkTkRenderWindowInteractor(
                holder,rw=render_window,width=1050,height=630)
        except (ImportError,tk.TclError):
            widget=None

        if widget is not None:
            mode="embedded"
            widget.pack(fill="both",expand=True)
            interactor=widget.GetRenderWindow().GetInteractor()
        else:
            mode="native"
            holder.destroy()
            window.geometry("1180x430")
            window.minsize(900,400)
            ttk.Label(window,padding=8,
                text="3D scene opens in a separate native VTK window. Controls remain here.").pack(fill="x")
            render_window.SetSize(1100,760)
            interactor=vtk.vtkRenderWindowInteractor()
            interactor.SetRenderWindow(render_window)

        interactor.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())
        render_window.AddRenderer(renderer)
        if widget is not None:
            widget.Initialize()
        else:
            interactor.Initialize()
        render_window.Render()
        window._cleanroomx_vtk_renderer=renderer

        # The animated sphere markers occupy positions from recorded particle
        # integration samples only. Path geometry stays visible separately.
        marker_points=vtk.vtkPoints()
        marker_points.SetDataTypeToDouble()
        marker_data=vtk.vtkPolyData()
        marker_data.SetPoints(marker_points)
        marker_sphere=vtk.vtkSphereSource()
        marker_sphere.SetRadius(0.35*min(report["voxel_pitch_m"]))
        marker_sphere.SetThetaResolution(10)
        marker_sphere.SetPhiResolution(10)
        marker_glyph=vtk.vtkGlyph3D()
        marker_glyph.SetSourceConnection(marker_sphere.GetOutputPort())
        marker_glyph.SetInputData(marker_data)
        marker_glyph.ScalingOff()
        marker_mapper=vtk.vtkPolyDataMapper()
        marker_mapper.SetInputConnection(marker_glyph.GetOutputPort())
        marker_mapper.ScalarVisibilityOff()
        marker_actor=vtk.vtkActor()
        marker_actor.SetMapper(marker_mapper)
        marker_actor.GetProperty().SetColor(.78,1.0,.26)
        renderer.AddActor(marker_actor)
        source_points=vtk.vtkPoints()
        source_points.SetDataTypeToDouble()
        source_data=vtk.vtkPolyData()
        source_data.SetPoints(source_points)
        source_sphere=vtk.vtkSphereSource()
        source_sphere.SetRadius(.5*min(report["voxel_pitch_m"]))
        source_glyph=vtk.vtkGlyph3D()
        source_glyph.SetSourceConnection(source_sphere.GetOutputPort())
        source_glyph.SetInputData(source_data)
        source_glyph.ScalingOff()
        source_mapper=vtk.vtkPolyDataMapper()
        source_mapper.SetInputConnection(source_glyph.GetOutputPort())
        source_actor=vtk.vtkActor()
        source_actor.SetMapper(source_mapper)
        source_actor.GetProperty().SetColor(.95,.35,.85)

        def update_particle_markers(_value=None):
            # No artificial interpolation: hold the latest actual integration
            # vertex until another recorded vertex's elapsed time is reached.
            found=particle_positions_at_elapsed(particles,playback_var.get())
            marker_points.Reset()
            for entry in found:
                marker_points.InsertNextPoint(*entry["xyz_m"])
            marker_points.Modified()
            marker_data.Modified()
            playback_status.set(
                f"{len(found)} visible simulated particles | "
                "frozen steady CFD U, not OpenFOAM transient")
            render_window.Render()
            return found

        def pause_particle_playback():
            playback_state["playing"]=False
            after=playback_state.get("after_id")
            if after is not None:
                try:
                    window.after_cancel(after)
                except tk.TclError:
                    pass
                playback_state["after_id"]=None

        def advance_particle_playback():
            if not playback_state["playing"] or not window.winfo_exists():
                return
            current=playback_var.get()
            maximum=float(slider.cget("to"))
            if current>=maximum:
                pause_particle_playback()
                return
            playback_var.set(min(maximum,round(current+.05,3)))
            update_particle_markers()
            playback_state["after_id"]=window.after(80,advance_particle_playback)

        def play_particle_screening():
            if not particles:
                playback_status.set("Inject a particle screening path first")
                return False
            pause_particle_playback()
            if playback_var.get()>=float(slider.cget("to")):
                playback_var.set(0.)
            playback_state["playing"]=True
            advance_particle_playback()
            return True

        slider.configure(command=update_particle_markers)
        ttk.Button(
            timeline_controls,text="Play samples",command=play_particle_screening
        ).pack(side="left",padx=5)
        ttk.Button(
            timeline_controls,text="Pause",command=pause_particle_playback
        ).pack(side="left",padx=5)

        def refresh_scene(*_ignored):
            """Rebuild from recorded arrays, retaining the operator's camera."""
            old=window._cleanroomx_vtk_renderer
            camera=vtk.vtkCamera()
            camera.DeepCopy(old.GetActiveCamera())
            try:
                axis=plane_var.get()
                pos=None if axis=="all" else float(plane_position_var.get())
                new=build_multizone_vtk_renderer(
                    report,traces,field=field_var.get(),vectors=arrows_var.get(),
                    room_id=room_var.get(),plane_axis=axis,plane_position_m=pos,
                    particles=particles,field_points=field_points_var.get())
            except (ValueError,OverflowError) as exc:
                view_status.set(f"Selection rejected: {exc}")
                return
            render_window.RemoveRenderer(old)
            render_window.AddRenderer(new)
            new.AddActor(marker_actor)
            if source_points.GetNumberOfPoints():
                new.AddActor(source_actor)
            if mesh_var.get() and mesh_state["dataset"] is not None:
                from .cfd_multizone_mesh import recorded_mesh_edge_actor
                new.AddActor(recorded_mesh_edge_actor(
                    mesh_state["dataset"],report,room_id=room_var.get(),
                    plane_axis=axis,plane_position_m=pos))
            new.SetActiveCamera(camera)
            render_window.Render()
            window._cleanroomx_vtk_renderer=new
            displayed_selection.update({
                "room_id":room_var.get(),
                "plane_axis":axis,
                "plane_position_m":pos,
            })
            count=select_recorded_cells(
                report,room_id=room_var.get(),plane_axis=plane_var.get(),
                plane_position_m=pos)
            convergence=("solver-reported convergence" if report.get("solver_reported_convergence")
                         else "NOT CONVERGED - engineering review required")
            view_status.set(f"{len(count)} recorded cells | {convergence}")

        ttk.Button(selection,text="Apply room/plane",command=refresh_scene).pack(
            side="left",padx=8)
        ttk.Checkbutton(
            selection,text="Pick fluid seed in 3D",variable=click_seed_var
        ).pack(side="left",padx=5)
        ttk.Button(
            selection,text="Clear 3D traces",
            command=lambda: (traces.clear(),refresh_scene())
        ).pack(side="left",padx=5)

        def export_paths(destination):
            try:
                saved=export_computed_streamlines(traces,destination)
            except (OSError, ValueError) as exc:
                view_status.set(f"Export rejected: {exc}")
                return False
            view_status.set(f"Saved {len(traces)} provenance-tagged 3D traces: {saved}")
            return True

        def choose_export():
            from tkinter import filedialog
            destination=filedialog.asksaveasfilename(
                parent=window,title="Export recorded 3D steady streamlines",
                defaultextension=".json",filetypes=(("JSON","*.json"),))
            if destination:
                export_paths(destination)

        ttk.Button(selection,text="Export 3D traces",command=choose_export).pack(
            side="left",padx=5)

        def export_particles(destination):
            try:
                saved=export_screening_particles(particles,destination)
            except (ValueError,OSError) as exc:
                view_status.set(f"Particle export rejected: {exc}")
                return False
            view_status.set(f"Saved {len(particles)} screening particle paths: {saved}")
            return True

        def choose_particle_export():
            from tkinter import filedialog
            destination=filedialog.asksaveasfilename(
                parent=window,title="Export frozen-field particle screening",
                defaultextension=".json",filetypes=(("JSON","*.json"),))
            if destination:
                export_particles(destination)

        ttk.Button(
            particle_controls,text="Clear particles",
            command=lambda: (particles.clear(),refresh_scene())
        ).pack(side="left",padx=7)
        ttk.Button(
            particle_controls,text="Export particle paths",
            command=choose_particle_export
        ).pack(side="left",padx=4)

        def open_particle_diagnostics():
            """Analyze ACTUAL recorded screening samples, never concentrations."""
            try:
                summary=analyze_particle_trajectories(report,particles)
            except (ValueError,TypeError,KeyError) as exc:
                view_status.set(f"Particle diagnostics rejected: {exc}")
                return None
            from tkinter import filedialog
            dialogue=tk.Toplevel(window)
            dialogue.title("CleanroomX | Sampled particle trajectory diagnostics")
            dialogue.geometry("1030x625")
            dialogue.minsize(770,440)
            content=ttk.Frame(dialogue,padding=12)
            content.pack(fill="both",expand=True)
            count=summary["number_of_screening_tracks"]
            aggregate=summary["aggregate"]
            ttk.Label(
                content,text=f"{count} frozen-U one-way screening path(s) | "
                f"{aggregate['first_observed_room_transitions']} sampled room-label transition(s) | "
                f"{aggregate['tracks_with_stokes_regime_warning']} Stokes warning(s) | "
                "ENGINEERING HOLD",
                font=("TkDefaultFont",11,"bold"),wraplength=980,
            ).pack(anchor="w",pady=(0,6))
            ttk.Label(
                content,
                text="Recorded vertices only. Paths are polygonal approximations; "
                "room times use left-sample labels (NOT actual crossing instants). "
                "No particle concentration, deposition, physical residence-time "
                "or 5 Pa closed-door acceptance is calculated.",
                wraplength=985,
            ).pack(anchor="w",pady=(0,10))
            headings=(
                ("index","#",40),("start","Start room",115),
                ("end","End room",115),("size","µm",70),
                ("samples","Samples",70),("seconds","Elapsed s",95),
                ("distance","Path m",95),("net","Displacement m",115),
                ("cross","Transitions",95),("stop","Termination",240),
            )
            table_frame=ttk.Frame(content)
            table_frame.pack(fill="both",expand=True)
            table=ttk.Treeview(
                table_frame,columns=[x[0] for x in headings],
                show="headings",height=12)
            for key,label,width in headings:
                table.heading(key,text=label)
                table.column(key,width=width,minwidth=45,stretch=True)
            for item in summary["tracks"]:
                table.insert("","end",values=(
                    item["particle_index"],item["start_room_id"],
                    item["end_room_id"],f"{item['diameter_um']:.4g}",
                    item["sample_count"],
                    f"{item['recorded_sample_elapsed_s']:.5g}",
                    f"{item['polygonal_path_length_m']:.6g}",
                    f"{item['end_to_end_displacement_m']:.6g}",
                    item["first_observed_transition_count"],item["termination"],
                ))
            scrollbar=ttk.Scrollbar(table_frame,orient="vertical",command=table.yview)
            table.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right",fill="y")
            table.pack(side="left",fill="both",expand=True)
            first=table.get_children()[0]
            table.selection_set(first)
            table.focus(first)

            refine_bar=ttk.Frame(content)
            refine_bar.pack(fill="x",pady=(8,0))
            ttk.Label(refine_bar,text="Particle numerical step-size study").pack(side="left")
            ttk.Label(refine_bar,text="Endpoint tolerance (m)").pack(
                side="left",padx=(12,4))
            refine_tolerance=tk.StringVar(value="0.001")
            ttk.Entry(
                refine_bar,textvariable=refine_tolerance,width=9).pack(side="left")
            refine_status=tk.StringVar(
                value="Three fixed-U replays (1x, 1/2x, 1/4x); never a physical convergence PASS.")
            ttk.Label(
                refine_bar,textvariable=refine_status,wraplength=505).pack(
                    side="right",fill="x",expand=True,padx=8)
            refine_queue=queue.Queue()
            refine_state={"busy":False,"after":None,"last":None}

            def show_refinement_result(study):
                result_window=tk.Toplevel(dialogue)
                result_window.title("CleanroomX | Particle timestep sensitivity")
                result_window.geometry("925x420")
                result_window.minsize(750,330)
                result_body=ttk.Frame(result_window,padding=12)
                result_body.pack(fill="both",expand=True)
                ttk.Label(
                    result_body,
                    text=f"Screen: {study['screening_status']} | "
                    f"Baseline/half endpoint Δ {study['endpoint_delta_baseline_to_half_m']:.6g} m | "
                    f"Half/quarter endpoint Δ {study['endpoint_delta_half_to_quarter_m']:.6g} m",
                    wraplength=880,font=("TkDefaultFont",10,"bold")).pack(anchor="w")
                ttk.Label(
                    result_body,
                    text="Numerical endpoint screen ONLY on a fixed recorded CFD snapshot. "
                    "It is not particle physics validation, time-dependent CFD, "
                    "mesh independence, deposition or cleanroom acceptance. "
                    "Engineering release: HOLD.",wraplength=880
                ).pack(anchor="w",pady=8)
                cols=("factor","cap","actual","steps","end","termination")
                table2=ttk.Treeview(
                    result_body,columns=cols,show="headings",height=4)
                for key,label in (
                    ("factor","Cap factor"),("cap","Max cap (s)"),
                    ("actual","Largest actual Δt (s)"),("steps","Segments"),
                    ("end","Endpoint xyz (m)"),("termination","Termination"),
                ):
                    table2.heading(key,text=label)
                    table2.column(key,width=155)
                for row in study["runs"]:
                    table2.insert("","end",values=(
                        row["step_cap_factor"],f"{row['configured_max_step_s']:.6g}",
                        f"{row['largest_recorded_elapsed_step_s']:.6g}",
                        row["integration_segments"],
                        ", ".join(f"{v:.5g}" for v in row["endpoint_xyz_m"]),
                        row["termination"],
                    ))
                table2.pack(fill="both",expand=True,pady=8)
                output_status=tk.StringVar(value="No output is written until export is requested.")
                ttk.Label(result_body,textvariable=output_status).pack(
                    side="left",fill="x",expand=True)
                def save_refinement():
                    destination=filedialog.asksaveasfilename(
                        parent=result_window,
                        title="Export noncertifying particle step refinement",
                        defaultextension=".json",filetypes=(("JSON","*.json"),))
                    if not destination:
                        return
                    try:
                        saved=export_particle_timestep_refinement(study,destination)
                    except (OSError,ValueError) as exc:
                        output_status.set(f"Export rejected: {exc}")
                    else:
                        output_status.set(f"Saved: {saved}")
                ttk.Button(
                    result_body,text="Export refinement JSON",
                    command=save_refinement).pack(side="right",padx=6)
                result_window._cleanroomx_refinement=study
                return result_window

            def start_refinement():
                if refine_state["busy"] or not dialogue.winfo_exists():
                    return False
                try:
                    selection=table.selection()
                    if not selection:
                        raise ValueError("Select a particle row")
                    index=int(table.item(selection[0],"values")[0])-1
                    if index<0 or index>=len(particles):
                        raise ValueError("Selected particle no longer exists")
                    sample=copy.deepcopy(particles[index])
                    tolerance=float(refine_tolerance.get())
                    if not math.isfinite(tolerance) or not 0<tolerance<=1:
                        raise ValueError("Endpoint tolerance must be finite and in (0, 1] m")
                except (ValueError,TypeError,IndexError) as exc:
                    refine_status.set(f"Refinement rejected: {exc}")
                    return False
                refine_state["busy"]=True
                refine_button.configure(state="disabled")
                refine_status.set("Replaying three step caps against recorded U; no solver transient.")
                def work():
                    try:
                        result=analyze_particle_timestep_refinement(
                            report,sample,endpoint_tolerance_m=tolerance)
                        refine_queue.put(("result",result,index,sample))
                    except Exception as exc:
                        refine_queue.put(("error",str(exc),index,sample))
                threading.Thread(target=work,daemon=True).start()
                def poll():
                    refine_state["after"]=None
                    if not dialogue.winfo_exists():
                        return
                    try:
                        kind,result,index,snapshot=refine_queue.get_nowait()
                    except queue.Empty:
                        refine_state["after"]=dialogue.after(100,poll)
                        return
                    refine_state["busy"]=False
                    refine_button.configure(state="normal")
                    if index>=len(particles) or particles[index]!=snapshot:
                        refine_status.set("Particle changed during refinement; stale result rejected")
                    elif kind=="error":
                        refine_status.set(f"Refinement failed: {result}")
                    else:
                        refine_state["last"]=result
                        refine_status.set(f"Screen: {result['screening_status']} | HOLD")
                        show_refinement_result(result)
                refine_state["after"]=dialogue.after(100,poll)
                return True

            refine_button=ttk.Button(
                refine_bar,text="Check step refinement",command=start_refinement)
            refine_button.pack(side="left",padx=8)
            foot=ttk.Frame(content)
            foot.pack(fill="x",pady=(10,0))
            export_status=tk.StringVar(
                value="Diagnostics remain noncertifying; source hashes and SIMPLE iteration are retained.")
            ttk.Label(foot,textvariable=export_status,wraplength=710).pack(
                side="left",fill="x",expand=True)
            def choose_diagnostics_export():
                destination=filedialog.asksaveasfilename(
                    parent=dialogue,title="Export source-checked particle diagnostics",
                    defaultextension=".json",filetypes=(("JSON","*.json"),))
                if not destination:
                    return
                try:
                    saved=export_particle_trajectory_diagnostics(summary,destination)
                except (OSError,ValueError) as exc:
                    export_status.set(f"Export rejected: {exc}")
                    return
                export_status.set(f"Saved noncertifying, provenance-tagged diagnostics: {saved}")
            ttk.Button(foot,text="Export diagnostics JSON",
                       command=choose_diagnostics_export).pack(side="right",padx=6)
            dialogue._cleanroomx_particle_diagnostics=summary
            dialogue._cleanroomx_particle_diagnostics_table=table
            dialogue._cleanroomx_export_diagnostics=choose_diagnostics_export
            dialogue._cleanroomx_start_refinement=start_refinement
            dialogue._cleanroomx_refinement_state=refine_state
            dialogue._cleanroomx_refinement_status=refine_status
            dialogue._cleanroomx_refinement_tolerance=refine_tolerance
            def cancel_refinement_poll(event):
                if event.widget is dialogue:
                    pending=refine_state.get("after")
                    if pending is not None:
                        dialogue.after_cancel(pending)
                        refine_state["after"]=None
            dialogue.bind("<Destroy>",cancel_refinement_poll,add="+")
            view_status.set(
                f"Analyzed {count} recorded sample path(s); no inferred concentration or deposition")
            return dialogue

        ttk.Button(
            particle_controls,text="Analyze particle paths",
            command=open_particle_diagnostics
        ).pack(side="left",padx=5)

        def start_particle_ensemble():
            """Worker-only numerical integration; all Tk scene edits stay on Tk thread."""
            if ensemble_state["busy"]:
                return False
            try:
                count=int(ensemble_count_var.get().strip())
                if count<1 or count>MAX_PARTICLES-len(particles):
                    raise ValueError("Choose 1 to the remaining 20 particle slots")
                selection=dict(displayed_selection)
                recorded_tracks=list(particles)
                diameter=float(particle_diameter_var.get())
                density=float(particle_density_var.get())
                horizon=float(particle_time_var.get())
            except (ValueError,TypeError) as exc:
                ensemble_status.set(f"Selection rejected: {exc}")
                return False
            ensemble_state["busy"]=True
            ensemble_button.configure(state="disabled")
            ensemble_status.set(
                f"Integrating {count} distinct recorded-cell seeds; this is frozen-U screening.")
            def work():
                try:
                    result=inject_recorded_particle_ensemble(
                        report, recorded_tracks,count=count,
                        **selection,diameter_um=diameter,
                        particle_density_kg_m3=density,max_time_s=horizon,
                    )
                    ensemble_events.put(("result",result,selection,recorded_tracks))
                except Exception as exc:
                    ensemble_events.put(("error",str(exc),selection,recorded_tracks))
            threading.Thread(target=work,daemon=True).start()
            def poll_ensemble():
                ensemble_state["poll_id"]=None
                if not window.winfo_exists():
                    return
                try:
                    kind,result,original_selection,old_tracks=ensemble_events.get_nowait()
                except queue.Empty:
                    ensemble_state["poll_id"]=window.after(100,poll_ensemble)
                    return
                ensemble_state["busy"]=False
                ensemble_button.configure(state="normal")
                if kind=="error":
                    ensemble_status.set(f"Batch rejected: {result}")
                    return
                if old_tracks!=particles or original_selection!=displayed_selection:
                    ensemble_status.set(
                        "Selection/particles changed during integration; stale batch discarded")
                    return
                particles.extend(result["new_tracks"])
                horizon_recorded=max(
                    p.get("release_time_s",0.)+p["points"][-1]["elapsed_particle_s"] for p in particles)
                slider.configure(to=max(horizon_recorded,.01))
                playback_var.set(0.)
                refresh_scene()
                update_particle_markers()
                ensemble_status.set(
                    f"Added {len(result['new_tracks'])} computed-cell seeds; "
                    f"{len(particles)}/20 screening paths. NOT a probability or concentration.")
            ensemble_state["poll_id"]=window.after(100,poll_ensemble)
            return True

        ensemble_button=ttk.Button(
            ensemble_controls,text="Inject room/plane seeds",
            command=start_particle_ensemble)
        ensemble_button.pack(side="left",padx=8)

        def show_sources(sources):
            source_points.Reset()
            for source in sources:
                if source["enabled"]:
                    source_points.InsertNextPoint(*source["position_m"])
            source_points.Modified()
            source_data.Modified()
            refresh_scene()

        def apply_source_run(result):
            # Validate before replacing any existing particle collection.
            computed_particle_polydata(report,result["tracks"])
            pause_particle_playback()
            particles[:]=copy.deepcopy(result["tracks"])
            slider.configure(to=result["configuration"]["observation_end_s"])
            timeline_label.set("Source observation time (s):")
            playback_var.set(0.)
            refresh_scene()
            update_particle_markers()
            view_status.set(f"{len(particles)} scheduled numerical paths | frozen U | engineering HOLD")

        def open_particle_sources():
            from .cfd_particle_sources_gui import ParticleSourcesWindow
            if source_panel[0] is None or not source_panel[0].winfo_exists():
                source_panel[0]=ParticleSourcesWindow(
                    window,report,on_run=apply_source_run,on_sources=show_sources,
                    scene_state=lambda:copy.deepcopy(particles))
            source_panel[0].deiconify()
            source_panel[0].lift()
            return source_panel[0]

        ttk.Button(source_controls,text="Particle sources...",command=open_particle_sources).pack(side="left",padx=8)

        def load_verified_mesh():
            if case_directory is None or mesh_state["busy"]:
                return False
            mesh_state["busy"]=True
            mesh_button.configure(state="disabled")
            view_status.set("Reading original polyMesh on a worker; checking recorded C/U/p and source hashes")
            def work():
                try:
                    from .cfd_multizone_mesh import load_recorded_multizone_mesh
                    mesh_events.put(("result",load_recorded_multizone_mesh(case_directory,report)))
                except Exception as exc:
                    mesh_events.put(("error",str(exc)))
            threading.Thread(target=work,daemon=True).start()
            def poll_mesh():
                mesh_state["poll_id"]=None
                try:
                    kind,value=mesh_events.get_nowait()
                except queue.Empty:
                    mesh_state["poll_id"]=window.after(60,poll_mesh)
                    return
                mesh_state["busy"]=False
                mesh_button.configure(state="normal")
                if kind=="error":
                    view_status.set(f"Original mesh rejected: {value}")
                    return
                mesh_state["dataset"]=value
                mesh_var.set(True)
                refresh_scene()
                view_status.set(f"Original OpenFOAM mesh verified: {value.GetNumberOfCells()} cells | engineering HOLD")
            mesh_state["poll_id"]=window.after(60,poll_mesh)
            return True

        mesh_button=ttk.Button(
            mesh_controls,text="Load verified mesh",command=load_verified_mesh,
            state="normal" if case_directory is not None else "disabled")
        mesh_button.pack(side="left",padx=6)
        ttk.Checkbutton(mesh_controls,text="Original mesh edges",variable=mesh_var,command=refresh_scene).pack(side="left")
        ttk.Label(mesh_controls,text="Original polyMesh topology; verified recorded cell centres and U/p. No mesh-independence claim.").pack(side="right")

        def seed_display_point(x,y):
            is_particle=particle_mode_var.get()
            if not source_mode_var.get() and len(particles if is_particle else traces)>=20:
                view_status.set("Maximum 20 paths per type; clear before adding more")
                return False
            try:
                point_id=pick_recorded_solver_point(
                    window._cleanroomx_vtk_renderer,x,y)
                if source_mode_var.get():
                    samples=select_recorded_cells(report,**displayed_selection)
                    if type(point_id) is not int or not 0<=point_id<len(samples):
                        raise ValueError("Source seed must be a visible recorded CFD fluid cell")
                    open_particle_sources().new_source(samples[point_id]["center_m"])
                    view_status.set("Fluid source selected; save its release parameters in Particle sources")
                    return True
                if is_particle:
                    particle=seed_particle_from_displayed_point(
                        report,particles,point_id,**displayed_selection,
                        diameter_um=float(particle_diameter_var.get()),
                        particle_density_kg_m3=float(particle_density_var.get()),
                        max_time_s=float(particle_time_var.get()))
                    particles.append(particle)
                    # Bound the timeline to the actual recorded integration
                    # horizon, not the requested duration if it hit a wall.
                    actual_horizon=max(
                        track.get("release_time_s",0.)+track["points"][-1]["elapsed_particle_s"]
                        for track in particles)
                    slider.configure(to=max(actual_horizon,.01))
                    playback_var.set(0.)
                    update_particle_markers()
                else:
                    trace=seed_streamline_from_displayed_point(
                        report,traces,point_id,**displayed_selection)
                    traces.append(trace)
                refresh_scene()
            except (ValueError,OverflowError) as exc:
                view_status.set(f"3D seed rejected: {exc}")
                return False
            if is_particle:
                warning=(" | Stokes drag regime warning" if
                         particle["stokes_regime_warning"] else "")
                view_status.set(
                    f"Particle {len(particles)}: {len(particle['points'])} positions, "
                    f"{particle['termination']}{warning}; FROZEN steady U, NOT certified")
            else:
                view_status.set(
                    f"Air trace {len(traces)}: {len(trace['points'])} computed points, "
                    f"{trace['termination']}; steady streamline, NOT particle tracking")
            return True

        def on_vtk_click(_caller,_event):
            if click_seed_var.get() or source_mode_var.get():
                x,y=interactor.GetEventPosition()
                seed_display_point(x,y)

        interactor.AddObserver("LeftButtonPressEvent",on_vtk_click,1.0)
        field_control.bind("<<ComboboxSelected>>",refresh_scene)
        arrows_control.configure(command=refresh_scene)
        field_points_control.configure(command=refresh_scene)
        def apply_camera(_event=None):
            set_recorded_view_camera(window._cleanroomx_vtk_renderer,camera_var.get())
            render_window.Render()
        camera_control.bind("<<ComboboxSelected>>",apply_camera)
        window._cleanroomx_vtk_widget=widget
        window._cleanroomx_vtk_render_window=render_window
        window._cleanroomx_vtk_mode=mode
        window._cleanroomx_field_var=field_var
        window._cleanroomx_arrows_var=arrows_var
        window._cleanroomx_field_points_var=field_points_var
        window._cleanroomx_camera_var=camera_var
        window._cleanroomx_apply_camera=apply_camera
        window._cleanroomx_room_var=room_var
        window._cleanroomx_plane_var=plane_var
        window._cleanroomx_plane_position_var=plane_position_var
        window._cleanroomx_view_status=view_status
        window._cleanroomx_click_seed_var=click_seed_var
        window._cleanroomx_particle_mode_var=particle_mode_var
        window._cleanroomx_particle_diameter_var=particle_diameter_var
        window._cleanroomx_particle_density_var=particle_density_var
        window._cleanroomx_particle_time_var=particle_time_var
        window._cleanroomx_particles=particles
        window._cleanroomx_playback_var=playback_var
        window._cleanroomx_playback_status=playback_status
        window._cleanroomx_update_particle_markers=update_particle_markers
        window._cleanroomx_particle_marker_points=marker_points
        window._cleanroomx_play_particle_screening=play_particle_screening
        window._cleanroomx_pause_particle_playback=pause_particle_playback
        window._cleanroomx_export_particles_to_path=export_particles
        window._cleanroomx_analyze_particle_paths=open_particle_diagnostics
        window._cleanroomx_inject_ensemble=start_particle_ensemble
        window._cleanroomx_ensemble_count_var=ensemble_count_var
        window._cleanroomx_ensemble_status=ensemble_status
        window._cleanroomx_ensemble_state=ensemble_state
        window._cleanroomx_source_mode_var=source_mode_var
        window._cleanroomx_open_particle_sources=open_particle_sources
        window._cleanroomx_source_marker_points=source_points
        window._cleanroomx_load_verified_mesh=load_verified_mesh
        window._cleanroomx_mesh_state=mesh_state
        window._cleanroomx_mesh_var=mesh_var
        window._cleanroomx_traces=traces
        window._cleanroomx_seed_display_point=seed_display_point
        window._cleanroomx_export_traces_to_path=export_paths
        window._cleanroomx_refresh_scene=refresh_scene

        def pump_native_events():
            if mode!="native" or not window.winfo_exists():
                return
            interactor.ProcessEvents()
            window._cleanroomx_vtk_after=window.after(30,pump_native_events)

        def cleanup(event):
            if event.widget is not window:
                return
            pause_particle_playback()
            mesh_pending=mesh_state.get("poll_id")
            if mesh_pending is not None:
                window.after_cancel(mesh_pending)
                mesh_state["poll_id"]=None
            ensemble_pending=ensemble_state.get("poll_id")
            if ensemble_pending is not None:
                try:
                    window.after_cancel(ensemble_pending)
                except tk.TclError:
                    pass
                ensemble_state["poll_id"]=None
            pending=getattr(window,"_cleanroomx_vtk_after",None)
            if pending is not None:
                try:
                    window.after_cancel(pending)
                except tk.TclError:
                    pass
            if mode=="native":
                interactor.TerminateApp()
                # VTK 9.3 X11 removes terminated interactors from its shared
                # registry in ProcessEvents(), before closing their displays.
                # Finalizing the render window first leaves a stale display
                # that can terminate Python when the next viewer opens.
                if interactor.IsA("vtkXRenderWindowInteractor"):
                    interactor.ProcessEvents()
            render_window.Finalize()

        window.bind("<Destroy>",cleanup,add="+")
        window.protocol("WM_DELETE_WINDOW",window.destroy)
        if mode=="native":
            window._cleanroomx_vtk_after=window.after(30,pump_native_events)
    except BaseException:
        try:
            render_window.Finalize()
        finally:
            window.destroy()
        raise
    return window
