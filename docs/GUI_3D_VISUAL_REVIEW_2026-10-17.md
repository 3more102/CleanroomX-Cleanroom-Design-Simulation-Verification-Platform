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
