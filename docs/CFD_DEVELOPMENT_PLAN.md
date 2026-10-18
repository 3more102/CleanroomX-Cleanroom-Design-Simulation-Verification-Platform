# CFD development checkpoint — 18 October 2026

## Current GUI and spatial-analysis continuation

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

1. Add an adapter for `sync-vtk` v3 snapshot stores. Validate their distinct
   state/snapshot schemas and field metadata; do not treat them as native v2
   manifests or claim native source-field verification.
2. Bind verified room masks and per-room boundary-flux assignments to solver
   geometry before computing doorway transfer or per-room ACH. Current user
   boxes are descriptive cell selections, not verified room boundaries.
3. Connect CAD room identities only through an explicit, checked transformation
   into the mesh frame; do not infer room identity from a region/case label.
4. Execute the complete explorer workflow against real Foundation v10 outputs
   on new runs. The existing coarse-grid output has now been replayed through
   region selection, export and the actual Tk viewer. Optional native-case log
   binding refused a configuration-hash mismatch; reconcile that identity before
   joining grid-family logs. Review the overlapping two-room CLI with PR #1328
   before integrating the feature branches.

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

## Current verification checkpoint

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
- Native-case log binding was refused on configuration-hash mismatch; those
  logs were not added to the replay. Scientific validation remains `BLOCKED`.
