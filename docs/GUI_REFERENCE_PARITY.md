# CleanroomX Design Studio — Reference parity register

**Source branch:** `feat/real-design-studio-20261018` (PR #1344)  
**Follow-up branch:** `chatgpt/design-studio-navigator-parity-20261019`  
**Status:** engineering work in progress; reference parity and OpenFOAM integration are **not certified**.

## Implemented and code-inspected features

| Acceptance criterion | Status | Evidence / qualification |
|---|---|---|
| Actual model-backed room, area, volume, device cards | Implemented in branch | `studio_snapshot` in `src/cleanroomx/gui_design_studio.py`; GUI tests |
| Interactive room navigator and miniature plan | Implemented in branch | Real `select_item(..., notify=True)` callbacks |
| Refresh plan after translation or same-area reshape | Fixed in follow-up | `studio_navigator_signature` tracks room X/Y, length, width and labels |
| Selected Room dimensions, classification and ownership | Implemented in branch | Inspector reads current spatial layout |
| Pressure provenance | Clarified in follow-up | Studio displays **Configured pressure**, not a claimed CFD result |
| Focus, isolate, restore visibility | Restore action added | Existing `focus_room_3d`, `isolate_selected` and `show_all` |
| 3D room canvas and camera presets | Implemented in branch | Existing Tk canvas projection; NOT genuine translucent GPU mesh |
| Real OpenFOAM result ingestion in this branch | Unverified / separate development | Do not infer this from GUI panels or other unmerged PRs |
| Exact visual match to reference | Unverified | Requires inspection of actual application screenshots |
| Full GUI regression on this follow-up commit | Pending CI evidence | See design-studio-preview GitHub Actions workflow |

## Screenshot evidence procedure

The GUI preview workflow launches **real Tk under Xvfb** at a `1920 × 1080` virtual
display, loads the bundled demo and captures the running application. It first
asserts that 3D room canvas items exist. The artifact is named
`real-cleanroomx-design-studio`. Capturing a screenshot alone does not prove
pixel or interaction parity. A reviewer must compare it to the actual
reference screenshot and record the resulting differences.

The Windows desktop GUI cannot be observed or asserted from a repository
API fetch. No local Windows screenshot, OpenFOAM run, or full-suite result
is claimed here.

## Acceptance scoring contract (no invented percentages)

Store criterion-level evidence in `reports/gui_reference_parity/` when available.
For each row, specify `criterion_id`, `passed`, `tested_at`, `commit`,
`test_or_screenshot_path` and `reviewer`. A missing or unverified criterion
is **not** a pass.

| Category | Denominator and pass rule |
|---|---|
| Visual parity | Number of reference screenshot elements enumerated in a reviewed visual checklist; pass each only after side-by-side visual comparison of the same demo and resolution |
| GUI functionality | Number of specified GUI commands; pass only after invocation and correct resulting state |
| 3D interactions | Number of declared navigation, selection and visibility behaviors; pass only from automated interaction or witnessed execution |
| Room/device synchronization | Number of create/move/resize/delete, selection and save/reload scenarios; pass only if model, mini-plan, 3D and inspector agree |
| OpenFOAM integration | Number of explicitly defined solver-to-UI scenarios including failure cases; pass only with version-pinned solver outputs and validated receipts |
| Automated verification | Number of required tests, with each result categorized as pass/fail/skip/error; skipped or nonexecuted tests do not count as passed |

The only admissible percentage is `100 * verified_passes / declared_total`
once a fixed, nonzero denominator is documented; report it alongside the
counts and test commit. Otherwise report **Not measured**, not `0%` or `100%`.

## Next verification gates

1. Obtain the latest CI run and inspect actual test failures, skips and artifacts.
2. Review the 1920 × 1080 screenshot against the original screenshot, noting
   sidebars, controls, spacing, room proportions and interactions.
3. Confirm the navigator redraw behavior when room coordinates or aspect ratio
   change, including actual mouse-driven edits and undo/redo.
4. Run focused tests on Windows and then the full test suite.
5. Exercise Foundation v10 OpenFOAM end-to-end separately; distinguish
   configured inputs from solver-computed outputs in the user interface.

Do not mark this report complete until those evidence gates are satisfied.
