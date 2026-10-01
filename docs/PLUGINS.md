# CleanroomX analysis plugin API

CleanroomX supports trusted installed Python packages that add engineering analysis
workflows to the same application registry used by built-in analyses.

## Contract

The current plugin API version is **1**. Extensions register one analysis per Python
entry point in the group:

```toml
[project.entry-points."cleanroomx.analysis_plugins"]
example_pressure_check = "cleanroomx_example.plugin:registration"
```

The referenced object must be either a
`cleanroomx.plugins.AnalysisPlugin` instance or a zero-argument factory that
returns one:

```python
from cleanroomx.plugins import AnalysisPlugin, PLUGIN_API_VERSION


def parse(payload: dict):
    # Validate every engineering field and return a domain object.
    ...


def run(model):
    # Return a dict, dataclass, or object exposing to_dict().
    ...


def report(result: dict) -> str:
    return "# Example pressure check\n"


registration = AnalysisPlugin(
    api_version=PLUGIN_API_VERSION,
    key="example_pressure_check",
    title="Example pressure check",
    category="Extensions",
    description="Example versioned engineering analysis.",
    parser=parse,
    runner=run,
    reporter=report,
)
```

Plugin keys are persistent project identifiers. They must match
`^[a-z][a-z0-9_]*$` exactly, with no leading or trailing whitespace, and
therefore should never be renamed after projects use them. `api_version` must
be a real integer value; boolean aliases such as `True` are rejected even
though Python normally compares `True == 1`.

## Discovery and failure behavior

Discovery runs once when `cleanroomx.application` is imported. Restart
CleanroomX after installing, removing, or upgrading a plugin.

CleanroomX sorts entry points deterministically before discovery. A plugin is
disabled when it:

- cannot be imported or constructed, including a plugin import/factory that
  calls `sys.exit()`;
- exposes unreadable or invalid entry-point identity metadata;
- declares an unsupported API version;
- has invalid metadata or non-callable parser/runner/reporter bindings;
- collides with a built-in analysis key; or
- duplicates another installed plugin key. For duplicate plugin keys, every
  contender is disabled rather than selecting one based on installation order.

A broken plugin does not remove built-in workflows. Discovery isolates ordinary
plugin exceptions and `SystemExit`; an operator `KeyboardInterrupt` is still
propagated so explicit cancellation is not swallowed. Run `cleanroomx-gui
--check` for machine-readable discovery diagnostics. Normal GUI startup also
reports disabled plugins. If a project references an unavailable plugin
analysis, project loading fails closed with an actionable error rather than
silently substituting a different workflow.

## Operator trust policy

Plugin code still executes with the same Python/OS privileges as CleanroomX, so
discovery supports a **pre-import trust gate** controlled before process startup. External plugin loading is disabled by default:

- `CLEANROOMX_PLUGIN_MODE=disabled` — secure default; no external analysis
  entry point is imported. Built-in analyses remain available and each blocked
  entry point is reported in plugin diagnostics.
- `CLEANROOMX_PLUGIN_MODE=trusted` — explicit compatibility opt-in that permits
  installed plugin entry points to use the existing validation and
  failure-isolation rules.
- `CLEANROOMX_PLUGIN_MODE=allowlist` — only distributions named in
  `CLEANROOMX_PLUGIN_ALLOWLIST` may be imported. The allowlist is a
  comma-separated set of distribution names with optional exact version pins,
  for example `cleanroomx-example,acme-hvac==2.4.1`.

Distribution names are normalized case-insensitively across `-`, `_`, and
`.` separators before comparison. A version pin uses exact installed metadata
text. Missing distribution identity, a non-matching version pin, malformed
allowlist syntax, or an invalid mode fails closed for external plugins rather
than falling back to trusted loading. `cleanroomx-gui --check` exposes the
effective mode, normalized allowlist, configuration errors, and blocked-plugin
issues.

The policy check occurs before `entry_point.load()`. It therefore prevents
blocked packages from being imported through the CleanroomX plugin entry point.
It is an operator execution-control mechanism, **not** package authentication:
distribution metadata can identify an installed package/version but is not a
digital signature and does not prove publisher authenticity.

## Execution boundary

Registered plugin analyses use the normal CleanroomX application execution path:

1. the parser validates an isolated deep copy of the submitted JSON input; if
   the parser mutates that submitted snapshot, CleanroomX rejects the run before
   backend execution;
2. the runner receives the parser result;
3. the result must normalize to strict JSON through the existing application
   result boundary;
4. the optional reporter receives an isolated deep copy of the normalized
   result and must return Markdown text as a string;
5. normal result status, diagnostics, plotting discovery, input SHA-256 identity,
   and stale-result checks remain active.

The host records plugin API version, entry-point identity, distribution name, and
distribution version in `application_execution_provenance.implementation`.
Built-in analyses record `source: "builtin"` and the CleanroomX version.

The deep-copy boundaries protect normal project/result ownership. They do not
sandbox a plugin or prevent intentionally malicious code from using Python or
operating-system APIs.

## Engineering requirements for plugin authors

A plugin is responsible for the engineering validity of its own model. It should:

- use explicit units and reject dimensionally inconsistent inputs;
- reject NaN, infinity, invalid bounds, and degenerate geometry as applicable;
- use deterministic algorithms where practical;
- make tolerances and assumptions explicit;
- retain enough provenance to reproduce engineering conclusions;
- return strict-JSON-compatible finite results;
- avoid modifying files or external state unless that behavior is an explicit
  documented part of the plugin contract.

Plugin API v1 does not provide host-managed declarations for external file
dependencies. A plugin that consumes external engineering files must record and
revalidate those dependencies itself in its result/provenance. A future API
version can add a host-level dependency contract without changing v1 behavior.

## Security boundary

Plugins are trusted executable Python packages. Install them only from sources
you trust and review. CleanroomX does not sandbox plugin code, authenticate plugin
publishers, or treat a distribution version as proof of source authenticity.

The plugin identity recorded in run provenance supports reproducibility and
diagnostics; it is not a digital signature or certification statement.
