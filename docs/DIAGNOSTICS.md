# Local diagnostics and support bundles

CleanroomX desktop diagnostics are local-only. The application does not transmit telemetry, logs, crash information, project content, or diagnostic bundles to an external service.

## Structured local log

Normal desktop startup configures a bounded rotating JSON Lines log named `cleanroomx.jsonl`. Each record contains a versioned schema, UTC timestamp, severity, event name, process/thread identity, explicitly supplied context fields, and exception traceback evidence when applicable.

Default locations are:

- Windows: `%LOCALAPPDATA%\\CleanroomX\\Diagnostics`
- macOS: `~/Library/Application Support/CleanroomX/Diagnostics`
- Linux: `$XDG_STATE_HOME/cleanroomx/diagnostics`, or `~/.local/state/cleanroomx/diagnostics`

Set `CLEANROOMX_DIAGNOSTICS_DIR` to use another directory. CleanroomX attempts owner-only permissions on POSIX systems. The active log is capped at 2 MiB with five rotated generations by default.

The logger records application lifecycle, project open/save failures and write conflicts, recovery restore/scan failures, autosave failures, and uncaught Tk callback exceptions. Logging is an observability aid; it is not a substitute for project/recovery persistence and it does not change engineering calculations.

## Uncaught GUI exceptions

Tk callback exceptions are captured at the application boundary. CleanroomX writes the exception type, message, and traceback to the local structured log and shows an actionable error dialog instead of relying only on Tk's console traceback behavior.

This boundary does not suppress the failed operation or claim that the application state is valid. Recovery autosave remains the mechanism for preserving dirty work.

## Diagnostic bundle export

Use **File → Export Diagnostic Bundle JSON...** to create a support bundle. The bundle contains:

- CleanroomX and Python/runtime version information;
- a bounded tail of the current structured log;
- project identity/path and active-analysis identity/kind;
- dirty/running state and current autosave status;
- an explicit privacy marker stating that no network transmission occurred.

The export intentionally does **not** attach analysis input JSON, solver results, reports, recovery artifacts, environment variables, or arbitrary project metadata. File paths and exception messages can still contain organization-specific information, so review a bundle before sharing it.

The log tail is bounded to 256 KiB and 500 records to prevent diagnostic export from becoming an unbounded memory operation on long-running sessions.

## Failure behavior

If the diagnostics directory cannot be created or opened, CleanroomX reports the diagnostics setup failure on stderr and continues launching. Observability must not become an application-availability dependency.

If diagnostic-bundle export fails, the existing atomic GUI export path surfaces the error and does not report success.

## Test coverage

`tests/test_diagnostics.py` verifies strict JSON serialization, non-finite-value sanitization, idempotent logger setup, traceback capture, bounded tail extraction, bundle generation, and the diagnostics-directory override.
