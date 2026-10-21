# CFD solver-log identity and bounded reads

This is an input-integrity hardening change; it does **not** alter OpenFOAM
physics, convergence, mesh quality, pressure control or the engineering HOLD.

`audit_openfoam_log` and `audit_project_room_cases` both use the same
`read_bounded_regular_log` reader:

- Reject missing, symlink, nonregular and greater-than-32-MiB files.
- Open one bounded file descriptor, using `O_NOFOLLOW` where available.
- Compare device, inode, size, modification/change times before open,
  on the opened descriptor, after reading, and at the final path.
- Read no more than 32 MiB + 1 byte, then hash the exact bytes parsed.

On platforms without `O_NOFOLLOW` the identity checks are best-effort;
this is not an atomic no-symlink guarantee. Metadata races beyond the
checks, maliciously fabricated logs and forged local SHA-256 receipts
remain outside the protection. There is no trusted signature or remote
attestation.

Synthetic regression tests cover a symlink swap between check and open,
nonregular/oversized logs, and matching source-byte hashes. These tests
are not evidence of CFD convergence or cleanroom qualification.

## Project-room input manifest coverage

The independent-room CFD audit also uses the project's strict JSON snapshot
reader for `manifest.json` (4 MiB bound). Duplicate keys, nonfinite JSON
constants and changed file identities are rejected. The audit's reported
manifest SHA-256 is calculated from the **same parsed snapshot**, not a second
potentially changed file read.

Every named room case must include receipts for all eight inputs required
by the room-case execution path: `blockMeshDict`, `controlDict`,
`fvSchemes`, `fvSolution`, `0/U`, `0/p`, `transportProperties`,
and `turbulenceProperties`. If any receipt is missing, the numerical audit
fails before reading solver logs.

This detects missing receipts and altered source snapshots; it does not
authenticate the manifest author or demonstrate physical validation.

## Residual sequence and terminal evidence (follow-up)

`simpleFoam.log` now must have `End` as its last non-whitespace
line, not merely somewhere inside the log. The same rule is applied
to `blockMesh.log` and `checkMesh.log`. This prevents appended
incomplete or contradictory data from being ignored after a prior End.

For each explicitly selected field, the numerical audit also retains
`recent_initial_residual_samples` and
`recent_final_residual_samples` from the inspected tail window.
Values use the order of the actual captured solver log, identified by
`residual_sample_axis = linear_solver_log_order_not_simple_iterations`.

These series are intended for numerical trend review and subsequent
charting; they are **not** indexed by saved SIMPLE iterations, are not
an independent convergence criterion, and cannot establish cleanroom
compliance. Thresholds remain supplied by the operator. Existing
JSON reports gain fields but preserve the established screening status.

## Interactive residual dashboard from the captured OpenFOAM log

The audit-log command can render an interactive **offline HTML** graph of actual
captured solver residuals. No external plotting service, chart screenshots,
synthetic values or re-read of the source file are involved.

```bash
cleanroomx-cfd-pipeline audit-log /path/to/simpleFoam.log \
  --fields p Ux Uy Uz \
  --max-initial-residual 0.00001 \
  --max-final-residual 0.000001 --window 3 \
  --interactive-html /path/to/new-residuals.html \
  --output /path/to/new-numerical-audit.json
```

Open the generated HTML file in a browser. Change field, Initial/Final residual,
linear/log10 y-axis and recent-sample count without needing a server or web
connection. All values are from the same bounded, SHA-256-recorded OpenFOAM
log snapshot inspected by audit-log. The latest **1000** entries per field are
retained with their original one-based, matching-field linear-solver log
sample indices. A linear-solver entry is **not** a SIMPLE iteration or elapsed
physical time; graphs are diagnostic, not convergence or ISO qualification.

Generation rejects incomplete or fatal logs, absent field samples, altered
plot evidence and inconsistent audited tails. A numerical threshold failure
may still be plotted, but retains its original `incomplete_or_failed` status.
HTML and JSON outputs cannot refer to the source log or to each other.
