# CleanroomX System Health Doctor

`cleanroomx-doctor` is a non-mutating workstation/readiness check for operators, support, and CI.

## Usage

```bash
cleanroomx-doctor
cleanroomx-doctor --format text
cleanroomx-doctor --output cleanroomx-health.json
cleanroomx-doctor --require-bim
cleanroomx-doctor --require-desktop
cleanroomx-doctor --deep
cleanroomx-doctor --baseline known-good-health.json
cleanroomx-doctor --baseline known-good-health.json --fail-on-regression
```

The command emits strict JSON with schema `cleanroomx.system-health` by default. Each check includes a `remediation` field; warnings and failures use it for a concrete next action while passing checks leave it null. Use `--format text` for a concise operator-readable summary; remediation appears as an indented `Action:` line and exit-code semantics are identical in both formats.

From the desktop application, use **Help → System Health…** or the command palette action **Run System Health Check** to run the standard non-destructive readiness checks. Warning and failure entries include the same actionable remediation guidance as the CLI report. The desktop surface intentionally runs the bounded shallow check; use `cleanroomx-doctor --deep` when an end-to-end analysis execution probe is required.

Required checks cover:

- the package's Python runtime requirement;
- the application analysis registry;
- Tkinter import availability plus headless Tcl interpreter initialization for the desktop application;
- the packaged demonstration project's ability to load;
- an atomic local persistence create/read probe.

Advisory checks cover the current Python release-qualification matrix, isolated plugin discovery issues, and native IfcOpenShell availability. By default, missing IFC/BIM support is a warning because it is an optional dependency. `--require-bim` promotes that check to required.

`--require-desktop` adds a required real-Tk display lifecycle probe. It creates a hidden Tk root, withdraws it, settles idle layout work, and destroys it. Use this on operator workstations or packaged desktop qualification when headless Tcl availability alone is not sufficient. A missing display server, broken native Tk library, or failed root lifecycle makes required readiness fail.

`--deep` adds a required end-to-end execution probe. It reloads the packaged demo, selects its configured active analysis, executes that analysis through the normal CleanroomX application runner against the packaged companion files, verifies that a result payload is produced, and confirms the loaded project input was not mutated. The engineering pass/fail status of the demo result is reported as diagnostic context; the health check is concerned with successful execution of the software path, not with treating the demo as certification evidence.

## Baseline drift detection

A previously captured JSON doctor report can be used as a known-good baseline:

```bash
cleanroomx-doctor --output known-good-health.json
cleanroomx-doctor --baseline known-good-health.json
```

When a baseline is supplied, the current report gains a deterministic `comparison` object with schema `cleanroomx.system-health-comparison`. It reports per-check status regressions and improvements, added/removed checks, required-readiness transitions, and required/advisory policy changes. A check that was required in the baseline but becomes advisory is a coverage regression even if its status still passes; promoting an advisory check to required is reported as coverage expansion.

Before comparison, both reports are checked for internal consistency. Their `required_ready`, aggregate `status`, and summary counts must agree with the actual check array. This rejects malformed or manually altered baselines instead of using contradictory readiness evidence.

The baseline must use the same probe profile as the current run: `--require-bim`, `--require-desktop`, and `--deep` must match. This prevents a shallow workstation report from being compared as though it were a deep or BIM-qualified probe.

Use `--fail-on-regression` for CI or deployment gates. A current machine can still be operationally ready while a previously passing advisory check has degraded to a warning; this option makes that drift visible through exit code 3. Required readiness failures continue to take precedence with exit code 2.

For evidence safety, `--output` cannot point to the same path as the supplied baseline.

## Exit codes

- `0`: all required checks passed. The JSON status is `ready` or `ready_with_warnings`.
- `2`: at least one required readiness check failed. The JSON status is `not_ready`.
- `3`: `--fail-on-regression` was requested and the compatible baseline comparison detected health regression while required readiness still passed.
- `1`: the command itself could not complete an expected OS/value operation, such as invalid baseline input, incompatible probe profiles, or publishing the requested output file.

The doctor does not certify a cleanroom, validate project engineering, or replace the release qualification workflows. It reports software/runtime readiness only.
