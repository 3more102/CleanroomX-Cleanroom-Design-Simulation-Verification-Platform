# Main branch protection

CleanroomX treats `main` as the production integration branch. Repository
administrators should enforce the following GitHub ruleset for `main`.

## Required rules

- Target branch: `main`.
- Block branch deletion.
- Block force pushes.
- Require changes to arrive through pull requests.
- Require the status check named `Required CI Gate`.
- Require the branch to be up to date before merging so the required gate runs
  against the current `main` base.
- Do not allow a failing, skipped, or cancelled required gate to merge.

The `Required CI Gate` job depends on all three production CI surfaces:

- the complete Linux test matrix on Python 3.11, 3.12, and 3.13;
- the Windows PowerShell/CMD launcher smoke job;
- the native IfcOpenShell ingestion smoke job on Python 3.12.

The gate uses `if: always()` so it still executes when a dependency fails or is
cancelled, and succeeds only when all three dependency jobs report `success`.

## Administrator break-glass

Prefer no bypass actors. If an administrator bypass is retained for incident
recovery, treat it as break-glass only:

1. record the reason in the affected issue or pull request;
2. do not use bypass to merge a known failing required gate;
3. immediately run CI on the resulting `main` commit;
4. revert or repair the bypassed change if current-main CI is not successful.

## Release-publisher invariant

Historical stable-release publishers are retained as manual `workflow_dispatch`
workflows bound to their immutable validated target SHAs. They do not publish
from the moving Release 3 integration head. Any future Release 3 publisher must
be introduced with its own validated target identity and release gate rather
than reusing a historical stable publisher.

## Verification after enabling the ruleset

After repository administration applies the ruleset:

1. open a small pull request and confirm GitHub requires `Required CI Gate`;
2. confirm the gate remains pending until the Python matrix, Windows launcher,
   and native BIM smoke jobs finish;
3. confirm a deliberately failing required dependency makes the gate fail;
4. confirm direct force-push and branch deletion are blocked;
5. confirm historical release publishers remain manual and fixed to their
   immutable validated target SHAs.
