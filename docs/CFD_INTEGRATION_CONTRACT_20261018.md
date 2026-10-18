# Two-room CFD integration contract — 18 October 2026

## Status

INTEGRATION IN PROGRESS. Scientific validation remains BLOCKED. This document records actual interface differences between sibling draft PRs #1328 and #1340; it does not assert they have been merged or tested together.

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

## Current blocker

The two draft PRs are sibling branches stacked on #1326. Do not mark this branch merged or scientifically validated until the implementations are reconciled and the combined CI passes.
