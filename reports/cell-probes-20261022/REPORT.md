# Recorded cell inspection — 22 October 2026

Baseline: `ab8ff2656427839dcc5efe5ef3ec01aa1d867072`, existing branch
`feat/doors-5pa-ceiling-downflow-demo-20261020`, PR #1363.

## Implemented behaviour

The native **Computed sections** panel now has a separate **Probe cell** click
mode and numerical **Probe XYZ** inputs. The table/readout retains the actual
zero-based OpenFOAM cell index, room, cell centre, p, Ux/Uy/Uz, speed, saved
SIMPLE iteration, density and reporting pressure reference. The selected cell
is marked in cyan only on a matching section/room. Existing streamline clicks
remain the default. The panel now scrolls in both directions at 850 × 600.

The occupied-voxel lookup never interpolates or substitutes a nearby cell for
a wall/missing voxel. JSON export retains full numerical values, requested
coordinates, source cell centres, manifest and execution-receipt hashes. It
recomputes the selection against the current imported field, rejects stale or
changed values/density/reference, limits selection to 100 probes and never
overwrites an existing file. New imports/cases/runs clear cached probes.

## Executed local checks

| Check | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Probe logic, original archive arrays, streamline/result/VTK compatibility | 65 | 0 | 0 |
| Actual Tk probe, responsive section/residual panels, live monitor, cancellation and WSL contracts | 37 | 0 | 0 |

The archive checks reimported the original 13,210-cell case through its normal
hash/input/log/field verification. All 52,840 cell-centre readings across saved
iterations **25, 50, 75 and 100** matched their original p/U arrays and preserved
the original row indices. Checks also reject reuse after changing air density
or the reporting reference room while keeping the same run receipt.

The native GUI tests use an explicitly synthetic field to check software
behaviour, including actual mouse events, row selection, empty coordinates,
marker filtering, source resets, export, small-window scrolling and execution
guards. They are not CFD or physical validation. Local Tk testing used an
unpacked Xvfb dependency over an isolated local TCP display because Unix-domain
display sockets are unavailable in this environment.

[Actual 1230 × 940 widget pixels and capture identity](../../docs/cell-probes-20261022/README.md)
use the original hash-checked, **unconverged** iteration-100 archive, with zero
GUI callback errors. [Example exported probes](archived-probe-examples.json)
and [implementation/evidence hashes](validation.json) are retained.

The updated Linux VTK workflow includes the probe logic, archive and actual
Tk tests. The Windows CI job also executes probe and archive checks on native
Tk. The actual Foundation v10 execution suite includes a fresh p/U-array and
GUI probe check; no local new solver execution is claimed. Complete-suite and
current-head remote workflow outcomes are pending at this publication stage.

**Engineering release remains HOLD.** This work verifies access to recorded
cell values. It does not establish numerical convergence, mesh independence,
closed-door leakage/5 Pa performance, physical particle qualification or actual
Windows-to-WSL workstation operation.
