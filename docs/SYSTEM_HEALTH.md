# CleanroomX System Health Doctor

`cleanroomx-doctor` is a non-mutating workstation/readiness check for operators, support, and CI.

## Usage

```bash
cleanroomx-doctor
cleanroomx-doctor --format text
cleanroomx-doctor --output cleanroomx-health.json
cleanroomx-doctor --require-bim
cleanroomx-doctor --deep
```

The command emits strict JSON with schema `cleanroomx.system-health` by default. Use `--format text` for a concise operator-readable summary; exit-code semantics are identical in both formats.

Required checks cover:

- the package's Python runtime requirement;
- the application analysis registry;
- Tkinter import availability plus headless Tcl interpreter initialization for the desktop application;
- the packaged demonstration project's ability to load;
- an atomic local persistence create/read probe.

Advisory checks cover the current Python release-qualification matrix, isolated plugin discovery issues, and native IfcOpenShell availability. By default, missing IFC/BIM support is a warning because it is an optional dependency. `--require-bim` promotes that check to required.

`--deep` adds a required end-to-end execution probe. It reloads the packaged demo, selects its configured active analysis, executes that analysis through the normal CleanroomX application runner against the packaged companion files, verifies that a result payload is produced, and confirms the loaded project input was not mutated. The engineering pass/fail status of the demo result is reported as diagnostic context; the health check is concerned with successful execution of the software path, not with treating the demo as certification evidence.

## Exit codes

- `0`: all required checks passed. The JSON status is `ready` or `ready_with_warnings`.
- `2`: at least one required readiness check failed. The JSON status is `not_ready`.
- `1`: the command itself could not complete an expected OS/value operation, such as publishing the requested output file.

The doctor does not certify a cleanroom, validate project engineering, or replace the release qualification workflows. It reports software/runtime readiness only.
