# CFD development checkpoint — 18 October 2026

## Native doorway transfer continuation

- New two-room runs bind native topology and face `phi` in the receipt, replay
  room-cell/doorway geometry and signed fluxes through ProofGraph, and display
  gross transfer in both directions plus net transfer and room balances.
- Legacy receipts retain an explicit unavailable doorway view. The new graph
  is included in two-room CLI exports and exercised through real Tk widgets.
- Offline replay of the hash-verified Foundation v10 archive produced the
  diagnostic values documented in [CFD_NATIVE_ROOM_FLUX.md](CFD_NATIVE_ROOM_FLUX.md).
- This closes the missing interface-face diagnostic for the supported generated
  fixture. General room-mask ingestion, per-room ventilation ACH, convergence,
  mesh independence and independent physical validation remain outstanding.
- Final display-enabled Python 3.12 regression: **2,836 passed, 1 skipped**
  (optional native IFC/BIM dependency), 166.85 seconds. The original archive
  receipt and full ZIP digest were verified before the offline native replay.

## Manifest-derived two-room field analysis

- The two-room result analyzer imports the unique receipt-hash-bound main VTK volume dataset and checks its solver time against the native phi receipt.
- Room masks are derived from the verified generated case dimensions, not freehand labels; the actual VTK domain bounds, each room's summed cell volume, and exactly-once cell assignment must pass before room field statistics are exposed.
- The analysis GUI has a dedicated per-room field comparison view for the final recorded time. This provides volume-weighted speed, velocity-component and kinematic-pressure diagnostics.
- Per-room flux and ACH remain unavailable: cell-center masks are not interface-face flux evidence. Scientific/physical validation remains BLOCKED.

## sync-vtk v3 snapshot analysis adapter

- Added an analysis adapter for the separate `sync-vtk` v3 state/snapshot schema, routed through the existing GUI selection path and `analyze-results` CLI.
- The adapter verifies state/snapshot/source hashes, reconstructs explicit field-map identity, re-imports VTK and compares the imported payload hash with the immutable snapshot before calculating diagnostics.
- The original VTK tree must remain available for geometry; native OpenFOAM fields, solver logs, convergence and physical cleanroom validation are not established by this VTK-only store.
- Synthetic regression coverage and the focused GitHub Actions gate are added with this checkpoint; results are pending CI.

## Native OpenFOAM grid integration continuation

Continues the published GUI/region head `fdd35aa` on PR #1341.

- The analysis adapter now loads all nine configuration/resolution cases from
  the native runtime-sync grid layout, preserving missing-case findings and
  strict manifest/receipt/VTK identity checks.
- Reconciled the input-hash boundary: the grid runner binds eight generated
  inputs per case, while a standalone case hash includes generated polyMesh.
  Grid analysis verifies the original eight-input scope explicitly.
- Matching grid execution receipts bind solver and checkMesh log bytes to the
  selected synchronized manifests; mismatched receipts or changed logs fail.
- GUI checkbox / CLI `--verify-native-fields` verify original time/field bytes.
  Reports preserve verification scope, and export rechecks those original files.
- Replayed the archived Foundation v10 run across **9 cases / 27 snapshots**:
  **81 original fields / 15,902,254 bytes**, 72 generated inputs, nine solver logs
  and nine mesh logs verified. The exact new CI analysis/export step passed on
  that archive; no solver was started locally.
- Captured the actual Tk field/residual views and source hashes under
  `docs/screenshots/cfd-analysis-native-grid-v10/`. This supersedes the earlier
  coarse-only replay's unavailable grid log join, without changing that
  historical capture or its provenance.
- Fixed residual equation selection resetting after drawing and made full
  nine-case comparison labels readable with horizontal bars.
- Final focused GUI/region/native-grid/result analysis: **68 passed** on a
  virtual display. Python compilation, workflow YAML/inline Python parsing,
  screenshot hashes and whitespace checks passed.
- Full display-enabled Python 3.12 regression: **2,792 passed, 1 skipped**
  (optional native IFC/BIM dependency), 173.63 seconds. The focused rerun above
  covers the final comparison-layout and residual-filter adjustments.
- Foundation v10 CI now analyzes 27 fresh snapshots with native field and
  execution-log checks, then exports its diagnostic figures, CSV and ProofGraph.

Convergence, mesh independence and physical cleanroom validation remain
`BLOCKED`. The new adapter verifies original field hashes but does not rerun
native-to-VTK numerical parity or a complete generated-mesh audit.

## Earlier GUI and spatial-analysis continuation

Continues `work/cfd-integration-reconciliation-20261018` from `6ff519a` (PR #1341).

- Explicit half-open mesh-coordinate boxes select full cells for histories,
  comparisons, slabs and 3D views. Empty selections retain unavailable statistics.
- Summary cards and a scrollable table report selected count/volume, whole-mesh
  volume coverage, weighted mean/range and exact solver times.
- Signed native U_x/U_y/U_z are available alongside speed. Run selection drives
  case/field/time choices and spatial data; it never silently uses the first run.
- Exports replay the region and preserve bounds, source/cell-index hashes,
  `selections.csv`, per-cell volumes and full selected-cell data before sampling.
- Failed source refresh removes stale plots, statistics and sessions; successful
  retry restores the workflow. Compact Matplotlib layout redraws on resize.
- Display-enabled regression reproduced two baseline GUI blockers: Fit selected
  returned no success value and ProofGraph tree selection continuously rebuilt
  its own selection. Both are fixed. The existing search test now checks its six
  visible match/context nodes, consistent with the documented search behavior.
- Corrected two further baseline display-test fixtures: revision records now
  include the required artifact identity and run-history filtering waits for a
  real completed GUI analysis rather than expecting a smoke preview to persist.
- The current environment runs real Tk tests on a virtual display. Focused
  region/result-store checks passed **59 tests**; expanded GUI/editing checks
  passed **89 tests**; revision/history dialog checks passed **7 tests**.
  These separate commands overlap in coverage.
- Actual widget screenshots, explicitly using a synthetic 576-cell fixture, are
  in `docs/screenshots/cfd-analysis-regions/`; reproduction instructions and
  selection semantics are in [CFD_RESULT_ANALYSIS.md](CFD_RESULT_ANALYSIS.md).

## Earlier result-store adapter work

- Preserved the existing solver-result explorer from branch
  `feat/solver-analysis-graphs-20261017` at base `669474f`.
- Connected standalone native `sync-case` stores to the analysis loader, GUI
  comparison picker and `analyze-results` CLI. Original case/region names are
  retained. A named case is a solver-domain identifier, not a verified room mask.
- Shared the existing manifest/receipt/asset verification and ProofGraph
  builder between standalone and three-configuration stores. Legacy
  configuration findings retain their identifiers and missing-case behavior.
- Bound optional standalone native-case logs to the case configuration and,
  when present, the recorded solver-log hash. Legacy unbound logs retain an
  explicit limitation.
- Fixed exact decimal solver-time selection in spatial CSV export and retained
  source time strings in history/comparison CSV. GUI time choices sort by
  decimal value rather than rounded floating-point value.
- Added the new parser/integration regressions to CFD VTK CI.

## Next implementation steps

1. Re-run native-to-VTK numerical parity and complete generated-mesh audits against fresh Foundation v10 outputs.
2. Extend the generated fixture's native room-face analysis to independently sourced room geometries and explicit ventilation allocations before enabling per-room ventilation ACH.
3. Add a bounded adapter that joins v3 VTK snapshots to native solver receipts only when the run/configuration identities match; never infer a native link from matching time labels alone.
4. Keep independent measured-data correlation and competent engineering review as the release gate for physical validation.

## Earlier adapter verification

Local verification completed before the follow-on virtual-display CI change:

- Full repository regression: **2,611 passed, 90 skipped, 0 failures**.
- Exact CFD VTK workflow test command: **338 passed**.
- Focused analysis/ProofGraph/runtime/GUI checks: **79 passed, 2 skipped**.
- Python compilation, workflow YAML and whitespace checks passed. The six
  preserved screenshot file hashes and dimensions match their existing manifest.

The follow-on CFD VTK workflow installs a virtual display and runs all explorer
Tk tests explicitly, including standalone-store comparison through the actual
folder picker callback. These three tests skip locally because no display is
available; their display-enabled CI result must be checked separately.

That earlier adapter checkpoint used synthetic parser fixtures and local tests;
OpenFOAM and a GUI display were unavailable then. Its preserved screenshots belong
to the earlier explorer checkpoint. The current region continuation has a virtual
display and new captures, but no installed OpenFOAM executable.
Scientific validation remains `BLOCKED`; process completion, file integrity,
graph generation and descriptive statistics do not establish solver convergence,
mesh independence or physical cleanroom performance.

## Earlier spatial verification checkpoint

- Full display-enabled repository regression on Python 3.12: **2,778 passed,
  1 skipped, 0 failures**, in 143.97 seconds. The skip is the optional native
  IFC/BIM dependency, not CFD or Tk coverage.
- Command: `python -m pytest -q -ra -o faulthandler_timeout=40`, executed on a
  virtual display with VTK/Matplotlib installed.
- Python compilation, CLI help, workflow YAML and `git diff --check` passed.
- Replayed actual Foundation v10 output from [base-branch CI run
  39118048747](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/39118048747).
  The archive matched its published SHA-256. The synchronized manifests,
  receipts and VTK assets passed source verification and export reconstruction.
- Case `configuration_1/coarse`, solver time `150`, west-half box: **108/216
  cells, 6/12 m³, 50% volume coverage**. Mean signed U_z was
  **-0.02691447064199798 m/s**. This is a recorded diagnostic result, not a
  physically validated room prediction. No solver was started locally.
- Native screenshots and source/hash provenance are in
  `docs/screenshots/cfd-analysis-native-v10/replay-evidence.json`.
- At that earlier checkpoint, native-case log binding was refused on a
  configuration-hash mismatch and logs were excluded. The native-grid
  continuation above resolves that identity boundary explicitly.
