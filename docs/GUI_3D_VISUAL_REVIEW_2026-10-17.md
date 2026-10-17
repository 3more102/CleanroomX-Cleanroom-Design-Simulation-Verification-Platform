# CleanroomX 3D GUI legibility review — 2026-10-17

## Screenshot baseline

The user-provided **CleanroomX 0.103.0.dev0** screenshot is a 1917 × 1011 PNG
with SHA-256:

`cfafd38c3386a02199267f54b4808df6eb6f58190dd12a39fe074ebfa9e07058`

Source image: provided directly in the development conversation as
`image(20261017-191240).png`. The original screenshot is preserved with
the associated development handoff artifact; it is **not** represented as
a generated simulator screenshot or stored in this repository by this PR.

## Observations grounded in the screenshot

- The Split workspace is usable and already presents a navigable project tree,
  synchronized 2D plan, and 3D model with translucent design-zone walls.
- Multi-line room annotations display the room name, classification,
  and pressure on top of each other as the camera projects three adjacent rooms.
- Numeric axis rulers, free-floating axis titles, pressure relation arrows,
  and crowded room text all compete for the same 3D pixels.
- The 3D toolbar puts projection, section height, X-ray, zone tint,
  orbit, tilt, and reset on one row; some controls are clipped at narrower widths.
- The right-side Properties pane is visually very narrow in the captured layout.
  Use the new **Balance panels** button to restore a readable 235–330 px
  inspector and allocate around 42% of the remaining view to the 2D plan.
  This is an explicit reset action, not an automatic persisted sash migration.

## Changes in this enhancement PR

- Split the 3D toolbar into two lines. Camera mode and Reset stay on the
  first row; Section, height, X-Ray, Zone tint, rotate and tilt are on the second.
- Replace all-in-one multi-line 3D room labels with individually positioned
  **name chips** that use collision avoidance, priority for selected/hovered rooms,
  and bounded positioning inside the viewport.
- Move long engineering details to a compact **selected / hovered room HUD**.
  It shows canonical geometry, project classification and the exact available
  engineering overlay label. The HUD hides at small viewport sizes.
- Anchor X/Y/Z caption titles to a fixed corner rather than geometry coordinates.
  Coordinate ticks and the reference cage are still in real model units.
- Preserve ACH, Airflow and Status evidence in the compact labels when enabled,
  and keep the existing 2D label contents unchanged.
- Preserve engineering pressure-cascade arrows without midpoint text spilling
  over adjacent 3D volumes. Never infer missing pressure or airflow values.
- Add **Balance panels** to recover from an accidentally collapsed Properties
  pane while keeping the geometry and engineering results unchanged.

## Verification targets

- Collision-free labels remain clickable and reference the same stable room IDs.
- Hide/show Labels and existing zone/engineering overlay selectors still work.
- Selected room details do not alter persisted design or verified results.
- Tests exercise tiny viewports, identical anchors, invalid coordinates,
  screen-space axis captions, and GUI rendering of a selected room.
- The screenshot is a visual review baseline, not a claim of screenshot-perfect
  regression matching or ISO cleanroom compliance.

## Manual review

1. Launch `start-cleanroomx.cmd` and open the bundled GUI demo project.
2. Select **Design** and **Split**, then orbit and zoom around the three rooms.
3. Toggle **Labels**, **Zone tint**, **X-Ray**, and engineering overlays.
4. Select and hover Process, Preparation and Ante / Airlock;
   verify the inspector HUD and unique short name chips.
5. Click **Balance panels** and verify the 2D/3D split and Properties
   inspector return to usable sizes without editing the model.
6. Reduce the window width: the 3D toolbar has two rows and the detailed
   HUD automatically hides when its available width is too small.

## Responsive GUI follow-up (PR #1336)

The first real Tk CI pass exposed two narrow-screen failures: a clipped
**Pull from analysis** button at 1050×680 and a room-label visibility test
that relied on a too-small initial viewport. The follow-up keeps both
**Pull from analysis** and **Push to analysis** on their own full-width row.

The design-zone legend now switches to a compact, clearly labeled
non-CFD badge when the 3D canvas is below 530 px wide or 335 px tall.
The collision-aware label layout reserves only the badge's actual bounds.
At larger sizes the existing colored multi-room legend remains visible.
Viewport label placements remain presentation-only and are never written
into the project model.

3D keyboard shortcuts (click inside the canvas first):

- **F:** fit visible 3D room geometry into the viewport
- **R:** reset the 3D camera
- **I:** isometric camera
- **Shift + left-drag:** orbit
- **Mouse wheel:** zoom

The shortcuts do not change rooms, pressure fields, or CFD evidence.
The regression suite checks a readable full-width 3D view separately from
small-view legend layout; failures are not treated as proof of CFD validation.

## Detailed inspector and viewport recovery

The next iteration addresses a measured regression in the prior development
branch on Linux Python 3.13: the 3D canvas was only **1037×25 px** in a real Tk
test. The old Properties sidebar stacked all editable sections at their full
natural height and competed vertically with the viewer.

The Properties pane now contains a vertically scrollable field editor with a
constant-height canvas. The **Apply properties** button remains outside the
scrolling area. A read-only selection summary reports exact floor area,
geometric room volume and the number of placed devices; all values come from
existing design geometry. A **Fit** button frames the selected room/device.

The full-width action toolbar also keeps **Validate** visible at 1050×680.
The prior compact legend, 3D camera shortcuts and zone-color display stay
unchanged.

The 3D HUD now displays:
- For rooms: name, project classification, L/W/H dimensions, computed floor
  area, computed geometric volume, room-device count and the *supplied* overlay.
- For devices: name, type, assigned room, X/Y/Z placement and available
  dimensions. It does not infer CFD supply rate, air-change rate or
  verified cleanliness from placement geometry.
- Hover can temporarily inspect a different visible room/device; leaving
  the canvas restores the selected object's information.

### Regression and acceptance

- Check minimum 1050×680 window: **Validate**, **Pull from analysis**, and
  **Push to analysis** remain mapped; 3D camera and a useful viewport remain
  available; property rows scroll with the mouse wheel.
- Check real Tk tests on supported Python 3.11–3.13 and full CLI suite.
- Changing viewport, scrolling the inspector, using Fit, and selecting a
  device must not alter the saved CAD room geometry or CFD evidence.
- Exact area and volume use lengths in meters from the canonical layout,
  not OpenFOAM mesh cells or any solver data.

### Focus 3D when working at 1050×680

The lower Output / Verification notebook can consume the remaining vertical
space if users previously dragged its sash upwards or saved a small main-window
layout. The application already provides a reversible **Focus Workspace** mode.
A dedicated **Focus 3D** button now opens the 3D-only view and toggles that
existing mode. On first use it temporarily hides the Project Navigator,
Output/Verification panel, and Properties pane to prioritize model inspection,
then fits the visible model into the viewport. Press the button again to
restore the prior panel visibility.

For detailed property editing instead, show the Inspector and optionally hide
Output/Verification from the View menu. The Inspector is scrollable. Small,
intentionally minimized canvases below the legibility thresholds do not draw
overlapping labels or HUD cards; focused viewport tests must allocate enough
pixels to inspect those features.

This mode does not save new pressure results, silently discard edits, or
overwrite the model. Focused Tk tests explicitly exercise the reversible
panel layout instead of assuming a 25-pixel canvas can display a full legend.

### Searchable 3D scene finder

From the 3D **Views** menu, choose **Find room or device…** (keyboard
shortcut **/** after clicking the canvas). The floating window searches all
room IDs/names, device types, device IDs/names and assigned room names.
Double-click an object or press **Open and fit** to select and fit it in the
current 3D view; Esc closes the finder. Results are sorted deterministically,
rooms first, and limited to 250 rows for responsive large projects.

This is an inspection action: it changes only selection and camera view.
It does not create airflow values, alter geometry, save pressure measurements,
or automatically assign rooms to unassigned equipment.

### Verification boundary

The last observed real-Tk failure on the predecessor PR resulted from a
deliberately narrow/short viewport that remained below the 3D HUD threshold.
The separate **Focus 3D** mode explicitly allocates visible canvas space;
the scrollable Properties editor is tested with the Inspector shown and
Output/Verification hidden. Do not treat tiny canvases as permission to
draw illegible text; the dedicated compact mode stays intentional.


## SVG vector export for design reviews

The **3D MODEL → Views → Export current 3D view… (SVG)** action writes a
standalone, scalable vector snapshot of *the currently drawn 3D canvas*. It
preserves the camera angle, floor and axis cage, room volumes, color legend,
labels, devices, pressure relationships and supplied engineering overlays
that are visible at export time.

Use it to embed a clean design image in a report or manual. The export:
- Does not need Pillow, OpenFOAM, a render server or a new 3D geometry model.
- Emits standards-based SVG polygons, lines, rectangles, ellipses and text.
- Preserves the current visible draw order, arrowheads and common stipple
  transparency approximately; normal Tk/SVG font differences can occur.
- Includes an accessible description that distinguishes design colors
  from CFD solver values or regulatory compliance.
- Writes atomically, refusing unsupported shapes and non-finite geometry
  rather than silently omitting elements or overwriting a valid prior file.
- Does not mutate CAD geometry, engineering inputs, selections or undo history.

The user must expand the 3D pane to at least 100×100 pixels before export.
Tiny, minimized or otherwise unreadable views are rejected. For a full-image
export, click **Focus 3D**, then use **Views → Export current 3D view… (SVG)**.

This is an image of the existing design GUI, not CFD visualization data
provenance, numerical solver output, a manufacturing drawing, or an
ISO 14644-1 / EU GMP compliance certificate.

## Reusable 3D camera bookmarks

In **Design → 3D → Views → Camera bookmarks**, choose **Save current
as View 1 / 2 / 3**. After orbiting, zooming, panning or switching between
orthographic and perspective views, use **Recall View 1 / 2 / 3** to return
to the saved camera. Empty slots are visibly disabled.

Bookmarks capture only azimuth, elevation, zoom, screen pan and projection.
They do **not** capture a CFD result, alter room/device geometry, take
an undo/redo action or infer cleanroom classification. Each slot is an
independent copy. Bookmarks belong to the active project in the current
application session and are cleared when another project object is loaded.
They are intentionally **not serialized** into the project file.

Use these to prepare consistent camera angles, then export individual
design illustrations from **Views → Export current 3D view… (SVG)**.
SVG remains a presentation image, not an engineering verification record.

Regression tests cover capture/recall, copying, invalid slots, invalid
camera parameters, stored-view isolation, and actual Tk menu state when
the project is reloaded.
