# CFD development checkpoint — 18 October 2026

## Implemented in this continuation

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
2. Define explicit room cell selections, coverage checks and per-room boundary
   flux assignments before computing room pressure statistics, doorway
   transfer or per-room ACH. Preserve missing-data states until inputs exist.
3. Extend GUI selection controls for those regions and available fields,
   reusing the current asynchronous explorer and graph/export renderer.
4. Execute the complete explorer workflow against real Foundation v10 outputs
   and review the resulting plots and source links. Run real Tk checks on a
   display-enabled machine. Review the overlapping two-room CLI with PR #1328
   before integrating the feature branches.

## Evidence boundary

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

This continuation uses synthetic parser fixtures and local automated tests.
OpenFOAM and a GUI display are unavailable in the current environment. Preserved
screenshots belong to the earlier explorer checkpoint, not this update.
Scientific validation remains `BLOCKED`; process completion, file integrity,
graph generation and descriptive statistics do not establish solver convergence,
mesh independence or physical cleanroom performance.
