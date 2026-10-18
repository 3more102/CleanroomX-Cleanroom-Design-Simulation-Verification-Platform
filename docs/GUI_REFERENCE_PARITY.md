# CleanroomX Design Studio — reference parity ledger

## Scope and provenance

- Parent implementation: [PR #1344](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/pull/1344) (`feat/real-design-studio-20261018`).
- Follow-up: `chatgpt/design-studio-nav-sync-20261019`.
- Running application: Tkinter `CleanroomXApp` and canonical `SpatialDesignWorkspace`. `gui_design_studio.py` does not own a separate engineering model.
- GUI baseline/source of truth: genuine screenshot artifacts from the parent PR's **Design Studio Real Tk Preview** workflows. No pixel-identical claim is made.
- Limitation: editing via GitHub alone does not verify a Windows-local checkout, user-specific UI state, or graphical appearance. Review CI screenshots and the Windows app before final sign-off.

## Changes in this continuation

| Area | Change | Evidence required |
| --- | --- | --- |
| Room navigator invalidation | Its signature includes room X/Y positions and length/width, not just name/area | Pure snapshot test and real Tk relocation/redraw test |
| Visibility controls | An explicit **Restore all rooms** command clears isolation and refits the camera | Real Tk isolation/restore test |
| Pressure provenance | Studio labels project-model pressure as **Configured pressure**, not a computed CFD result | Real Tk panel assertion |
| Screenshots | Real app capture supports dimensions; CI requests 1920x1080 and 1536x960 on virtual displays | Two uploaded PNGs, job logs and image dimensions |

## Functional acceptance matrix

| Requirement | Verification method | Status |
| --- | --- | --- |
| Real CleanroomX demo loads | Tk integration test / capture process | Await latest CI |
| Live room count, area, volume, device count | `studio_snapshot` unit and Tk tests | Await latest CI |
| Navigator lists correct room and selection | Tk integration test | Await latest CI |
| Navigator updates on relocation or equal-area footprint change | New regression tests | Await latest CI |
| 3D room geometry and projected devices are rendered | Tk canvas tags and screenshots | Await latest CI |
| Focus / isolate / restore all rooms | Tk integration test | Await latest CI |
| Inspector reports configured pressure provenance | Tk assertion plus manual inspection | Await latest CI |
| 2D / 3D / split, save/reload, validation, reports | Broader application regression | Not requalified by this continuation |
| OpenFOAM native execution and field provenance | Independent OpenFOAM execution receipts | Not requalified by this continuation |
| Reference visual parity | Human review of actual screenshots vs provided reference | Not yet independently reviewed |
| Windows desktop behavior | Local Windows app review | Not accessible through GitHub-only execution |

## Completion denominator policy

No category is assigned a percentage until its complete, enumerated acceptance matrix is executed and independently reviewed.

- **Visual parity:** individually review layout, commandbars, fonts, colors, cards, 3D scene, mini-plan, inspector, device panel, navigation, responsive sizes, and labels (12 items); pass only after a real screenshot comparison.
- **GUI functionality:** count passing user-action scenarios divided by the total enumerated actionable scenarios, not merely visible buttons.
- **3D interaction:** count passing orbit, pan, zoom, camera presets, focus, isolation, reset and selection scenarios, with explicit tests.
- **Room/device synchronization:** count passing create, edit, delete, select, save/reload and linked-view update scenarios.
- **OpenFOAM:** separate native case generation, mesh validation, execution, solver logs, receipt verification, field parsing and analysis evidence; absence of execution receipts is *not verified*, not 100%.
- **Automated verification:** separately disclose passed/failed/skipped/errors and tested vs required scenarios; skips do not count as passes.

## Commands and review

On Windows, without changing the existing checkout:

```powershell
git fetch origin
git worktree add "..\CleanroomX-Studio-Parity" origin/chatgpt/design-studio-nav-sync-20261019
cd "..\CleanroomX-Studio-Parity"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q tests/test_gui_design_studio.py tests/test_spatial_editing_gui.py
.\.venv\Scripts\cleanroomx-gui.exe --demo
```

For actual 1920x1080 CI capture, review the latest **Design Studio Real Tk Preview** run on the follow-up pull request and open its image artifacts; verify image sizes and visually inspect overlays and 3D geometry.

**Release/merge gate:** Do not claim pixel-level parity, total GUI completeness or 100% OpenFOAM integration from these changes alone. Require successful focused/full regression, genuine screenshot review, and available native-solver evidence appropriate to each claim.
