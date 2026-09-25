# Rollback Procedure

## Code rollback

For the shared repository, prefer a Git revert of the release-changing commit or merge rather than rewriting shared history.

Before rollback:

1. Record the current commit SHA and CI run.
2. Preserve affected project files and exported reports.
3. Identify the last known validated CleanroomX baseline.
4. Revert the required release commit(s) through normal review/CI.
5. Run the full CI matrix and representative GUI/CLI smoke checks before declaring the rollback complete.

Do not force-reset shared `main` unless repository policy explicitly permits it and collaborators understand the history rewrite.

## Project-file rollback

Schema version 1 is the current desktop project format. Supported legacy formats are migrated in memory on load and are rewritten as schema version 1 only when the operator saves the project.

If a migrated project must return to its original legacy representation, restore the archived original file. CleanroomX does not synthesize reverse migrations to historical legacy shapes.

## Result rollback

Generated JSON/Markdown results are derived artifacts. If the application version changes, regenerate results from preserved source inputs using the selected validated version rather than editing generated evidence by hand.

## Acceptance

A rollback is complete only when the selected baseline installs successfully, its CI/regression checks pass, and required project files can be opened and validated with that baseline.


## v0.100 release anchor

The validated v0.100.0 merge commit is `fa02c71f990790089cb9c64eb2e009cd984eb5db`. Its exact PR head `d8965090ee86713919079d9ee5e8a3b1d8f95e3b` passed CI run #822 before merge. Use repository history and normal revert/CI flow rather than rewriting shared history.

## v0.101.0 Release 2 anchor

The verified Release 2 code baseline on `main` is `0f487a7e11ad81c8bcd54eb91b6420a1d46523ea`.
Its final consolidation PR #431 head `993a2803e1af6a37af05ac0036948cc9f7fb3fce`
passed CI run #1463 / `36162913321`, and the post-merge `main` run #1464 /
`36163451603` also passed. The immutable `v0.101.0` tag and GitHub Release are
published from the final release-closure commit by
`.github/workflows/publish-v0101-release.yml`. Preserve that tag and use normal
revert/CI flow for any rollback from Release 2.


## v0.101.0 final launcher integration

The final repository-checkout launcher integration is PR #434, merged as `1acbaa1b67f624ae495590f78d5bccfc038fbd82` after CI run #1472 / `36164491604` passed on Python 3.11, 3.12, and 3.13 with **961 passed** per interpreter plus the Windows PowerShell/CMD launcher smoke. Treat this commit as part of the v0.101.0 release closure; roll back through normal revert and CI rather than moving the release tag.

## v0.102.0 synchronized spatial closure anchor

The final synchronized spatial baseline is merged at `2c8d0696170080d5c333ff1fc809f671aec1ac1d`.
Its exact tested PR #442 head `db9169555127b1799f261f31113d18cdaf2518ed` and
the merged commit share Git tree `af3c534599ee0921f8f21c8a14bd7b6b3e209258`.
PR CI run #1503 / `36168565655` passed 985 tests on Python 3.11, 3.12, and
3.13 plus Windows launcher, clean-wheel, CLI, and Tk/Xvfb GUI smoke gates.
Preserve published v0.100.0, v0.101.0, and v0.102.0 tags; rollback through normal
revert and CI rather than moving release history.


## v0.102.1 final spatial production closure anchor

The final post-v0.102 spatial code baseline is `f595aaba6e7b8704beb62acc04f0eb4d036d8f09`.
It includes PR #467 (tested head `4be4fb840480df7a5f1e0313a73830313150d9dd`,
CI #1540 / `36170548238`) and PR #472 (tested head
`8a34c3d649aee54c377b4194a6d619559d219421`, CI #1551 / `36171758793`).
Both pull-request CI runs succeeded. Publish v0.102.1 as a new immutable tag only
from a successful current-main CI commit; do not move v0.102.0 or any earlier tag.

