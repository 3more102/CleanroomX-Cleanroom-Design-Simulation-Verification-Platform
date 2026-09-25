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
`^[a-z][a-z0-9_]*$` and therefore should never be renamed after projects use
them.

## Discovery and failure behavior

Discovery runs once when `cleanroomx.application` is imported. Restart
CleanroomX after installing, removing, or upgrading a plugin.

CleanroomX sorts entry points deterministically before discovery. A plugin is
disabled when it:

- cannot be imported or constructed;
- declares an unsupported API version;
- has invalid metadata or non-callable parser/runner/reporter bindings;
- collides with a built-in analysis key; or
- duplicates another installed plugin key. For duplicate plugin keys, every
  contender is disabled rather than selecting one based on installation order.

A broken plugin does not remove built-in workflows. Run
`cleanroomx-gui --check` for machine-readable discovery diagnostics. Normal GUI
startup also reports disabled plugins. If a project references an unavailable
plugin analysis, project loading fails closed with an actionable error rather
than silently substituting a different workflow.

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
