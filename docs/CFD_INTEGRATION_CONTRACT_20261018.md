# Two-room CFD integration contract — 18 October 2026

## Status

The sibling interfaces are reconciled in the desktop integration branch, together
with the polished Design Studio. This does not assert a merge to main. Scientific
validation remains BLOCKED. The current desktop workflow and verification
procedure are documented in [Desktop solver workflow](DESKTOP_SOLVER_WORKFLOW.md).
The table below preserves the original interface differences for reference.

## Verified divergent interfaces

| Surface | PR #1328 | PR #1340 |
| --- | --- | --- |
| CLI | `two-room-analyze CASE_DIRECTORY RECEIPT OUTPUT_DIRECTORY` | `two-room-analyze CASE_DIRECTORY RECEIPT --output OUTPUT_DIRECTORY` |
| Backend | `cfd_two_room_analysis.export_two_room_analysis` and `cfd_analysis_bundle.verify_analysis_bundle` | `cfd_result_analysis.analyze_two_room_results` and ProofGraph |
| GUI | subprocess command builders `build_two_room_analysis_command` and `build_two_room_analysis_audit_command` | asynchronous explorer using `gui_cfd_analysis.open_analysis_explorer` |

## Reconciliation acceptance criteria

1. Preserve the existing PR #1340 native and standalone result-store explorer and receipt verification.
2. Decide whether to support both CLI forms; do not silently change positional output arguments or reuse a flag with different semantics.
3. Preserve the PR #1328 verified probe/flux/room-field diagnostic SVG exports, without treating unverified room labels as spatial masks.
4. Preserve a single documented GUI entry point for verified two-room analysis; retain asynchronous behavior and explicit missing-data states.
5. Reconcile `.github/workflows/cfd-vtk.yml`, `docs/CFD_TWO_ROOM.md`, `src/cleanroomx/cfd_pipeline_cli.py`, and `src/cleanroomx/gui_openfoam.py` with tests for both paths.
6. Require green CFD VTK, real Tk display, Windows, and OpenFOAM Foundation v10 CI on the reconciled commit.
7. For scientific release, attach genuine two-room solver output, convergence and mesh-independence review, boundary flux evidence, and provenance. Synthetic fixtures and screenshot tests are not physical validation.

## Reconciliation

The explorer uses `two-room-analyze CASE RECEIPT --output DIRECTORY`; the separate
receipt-bound SVG export uses `two-room-verified-bundle CASE RECEIPT DIRECTORY`.
Both paths remain tested. The desktop integration adds a selected-room case
runner, native/WSL connection settings, real log progress, process stopping,
automatic result loading and execution-receipt-bound whole-domain flux/ACH.
Release review still requires combined CI and independent scientific evidence.
