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
