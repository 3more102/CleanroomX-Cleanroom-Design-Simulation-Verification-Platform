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
