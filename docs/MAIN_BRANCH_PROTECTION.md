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

The `Required CI Gate` job depends on both production CI surfaces:

- the complete Linux test matrix on Python 3.11, 3.12, and 3.13;
- the Windows PowerShell/CMD launcher smoke job.

The gate uses `if: always()` so it still executes when a dependency fails or is
cancelled, and succeeds only when both dependency jobs report `success`.

## Administrator break-glass

Prefer no bypass actors. If an administrator bypass is retained for incident
recovery, treat it as break-glass only:

1. record the reason in the affected issue or pull request;
2. do not use bypass to merge a known failing required gate;
3. immediately run CI on the resulting `main` commit;
4. revert or repair the bypassed change if current-main CI is not successful.

## Release-publisher invariant

The immutable release publishers remain downstream of the `CI` workflow on
`main`. The current v0.102.1 publisher requires a successful `workflow_run`,
checks out that exact successful CI SHA, verifies it still equals
`refs/heads/main`, and repeats the current-main check before publication.

Adding `Required CI Gate` therefore strengthens the CI workflow without
changing the existing current-main release-publication identity check.

## Verification after enabling the ruleset

After repository administration applies the ruleset:

1. open a small pull request and confirm GitHub requires `Required CI Gate`;
2. confirm the gate remains pending until both the Python matrix and Windows
   launcher smoke finish;
3. confirm a deliberately failing required dependency makes the gate fail;
4. confirm direct force-push and branch deletion are blocked;
5. confirm a successful current-main CI run remains the only eligible input to
   the immutable release publisher.
