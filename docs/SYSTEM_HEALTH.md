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
cleanroomx-doctor --fail-on-warnings
```

The command emits strict JSON with schema `cleanroomx.system-health` by default. Each check includes a `remediation` field; warnings and failures use it for a concrete next action while passing checks leave it null. Use `--format text` for a concise operator-readable summary; remediation appears as an indented `Action:` line and exit-code semantics are identical in both formats. Use `--fail-on-warnings` when automation must reject advisory drift as well as required-readiness failures; the report payload is unchanged and only the process exit policy becomes stricter.

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

## Exit codes

- `0`: all required checks passed. The JSON status is `ready` or `ready_with_warnings`.
- `2`: at least one required readiness check failed. The JSON status is `not_ready`.
- `3`: `--fail-on-warnings` was requested, every required check passed, and at least one advisory warning remains. The JSON status is `ready_with_warnings`.
- `1`: the command itself could not complete an expected OS/value operation, such as publishing the requested output file.

The doctor does not certify a cleanroom, validate project engineering, or replace the release qualification workflows. It reports software/runtime readiness only.
