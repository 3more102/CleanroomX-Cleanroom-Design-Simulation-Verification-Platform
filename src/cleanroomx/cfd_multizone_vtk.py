"""Interactive 3D VTK review of recorded, non-certified OpenFOAM multizone data.

The scene plots actual cell-centred p/U, modeled room bounds and bounded
streamlines derived from the *same* recorded SIMPLE iteration. It never
manufactures interior samples, transient frames or physical particle physics.
VTK is an optional dependency; the core CleanroomX GUI remains usable without it.
"""
from __future__ import annotations

import math

from .cfd_particles import (
    PARTICLE_SCHEMA, MAX_PARTICLES, trace_screening_particle,
    export_screening_particles,
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
                                 particles=None):
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
        + " | GOLD=steady U | GREEN=one-way particle screening (not certified)")
    annotation.SetDisplayPosition(15, 16)
    annotation.GetTextProperty().SetColor(.98,.98,.98)
    annotation.GetTextProperty().SetFontSize(15)
    renderer.AddViewProp(annotation)
    renderer.ResetCamera()
    return renderer


def open_multizone_vtk_window(parent, report, traces):
    """Open interactive 3D with robust support for pip wheels lacking VTK/Tk.

    Prefer embedded vtkTkRenderWindowInteractor when the native Tk plugin is
    installed. Otherwise open a genuine *independent* VTK render window and
    keep Tk controls responsive by polling native events via Tk's event loop.
    This fallback does not require libvtkRenderingTk.
    """
    import tkinter as tk
    from tkinter import ttk

    vtk = _vtk()
    # Validate the complete recorded scene *before* opening a native window.
    renderer = build_multizone_vtk_renderer(report, traces)
    window = tk.Toplevel(parent)
    window.title("CleanroomX | Recorded CFD 3D controls")
    window.geometry("1120x760")
    window.minsize(620, 260)
    render_window = vtk.vtkRenderWindow()
    render_window.SetMultiSamples(0)
    render_window.SetWindowName("CleanroomX | Computed OpenFOAM 3D")
    field_var = tk.StringVar(value="speed")
    arrows_var = tk.BooleanVar(value=True)
    click_seed_var = tk.BooleanVar(value=False)
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
        ttk.Label(selection,textvariable=view_status).pack(side="right")
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
            window.geometry("1050x225")
            window.minsize(760,200)
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
                    room_id=room_var.get(),plane_axis=axis,plane_position_m=pos)
            except (ValueError,OverflowError) as exc:
                view_status.set(f"Selection rejected: {exc}")
                return
            render_window.RemoveRenderer(old)
            render_window.AddRenderer(new)
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

        def seed_display_point(x,y):
            if len(traces)>=MAX_3D_TRACES:
                view_status.set("Maximum 20 traces; clear 3D traces before adding more")
                return False
            try:
                point_id=pick_recorded_solver_point(
                    window._cleanroomx_vtk_renderer,x,y)
                trace=seed_streamline_from_displayed_point(
                    report,traces,point_id,**displayed_selection)
                traces.append(trace)
                refresh_scene()
            except (ValueError,OverflowError) as exc:
                view_status.set(f"3D seed rejected: {exc}")
                return False
            view_status.set(
                f"Trace {len(traces)}: {len(trace['points'])} computed points, "
                f"{trace['termination']}; steady streamline, NOT particle tracking")
            return True

        def on_vtk_click(_caller,_event):
            if click_seed_var.get():
                x,y=interactor.GetEventPosition()
                seed_display_point(x,y)

        interactor.AddObserver("LeftButtonPressEvent",on_vtk_click,1.0)
        field_control.bind("<<ComboboxSelected>>",refresh_scene)
        arrows_control.configure(command=refresh_scene)
        window._cleanroomx_vtk_widget=widget
        window._cleanroomx_vtk_render_window=render_window
        window._cleanroomx_vtk_mode=mode
        window._cleanroomx_field_var=field_var
        window._cleanroomx_arrows_var=arrows_var
        window._cleanroomx_room_var=room_var
        window._cleanroomx_plane_var=plane_var
        window._cleanroomx_plane_position_var=plane_position_var
        window._cleanroomx_view_status=view_status
        window._cleanroomx_click_seed_var=click_seed_var
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
            pending=getattr(window,"_cleanroomx_vtk_after",None)
            if pending is not None:
                try:
                    window.after_cancel(pending)
                except tk.TclError:
                    pass
            if mode=="native":
                interactor.TerminateApp()
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
