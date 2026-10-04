# CleanroomX analysis plugin API

CleanroomX supports trusted installed Python packages that add engineering analysis
workflows to the same application registry used by built-in analyses.

## Contract

The current plugin API version is **2**. API v1 remains supported for installed
plugins that do not use host-managed external dependency declarations. Extensions
register one analysis per Python entry point in the group:

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
- has invalid metadata or non-callable parser/runner/reporter/dependency-resolver bindings;
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

## Installed plugin trust policy

CleanroomX can apply an operator-controlled trust gate before an installed
analysis entry point is imported. The policy is selected with
`CLEANROOMX_PLUGIN_MODE`:

- `disabled` is the default and blocks every external analysis entry point before import;
- `trusted` is an explicit compatibility opt-in that preserves the historical installed-plugin behavior;
- `allowlist` imports only distributions named by
  `CLEANROOMX_PLUGIN_ALLOWLIST`.

The allowlist is a comma-separated set of distribution names with optional exact
version pins, for example:

```text
CLEANROOMX_PLUGIN_MODE=allowlist
CLEANROOMX_PLUGIN_ALLOWLIST=cleanroomx-example,approved-hvac-plugin==2.4.1
```

Distribution names are matched case-insensitively, and runs of `-`, `_`, and
`.` are treated as equivalent separators. A malformed mode or allowlist, a
missing distribution identity, a non-allowlisted distribution, a missing version
required by a pin, or a version mismatch fails closed for that external entry
point. A denied entry point is rejected before CleanroomX calls
`entry_point.load()`.

The effective policy is included in application-registry diagnostics, including
`cleanroomx-gui --check`, so automation and operators can see the mode,
allowlist, validity, and configuration error when present.

This gate controls whether CleanroomX imports a discovered plugin through its
analysis entry point. It is not a sandbox, package-signature verifier, publisher
authentication system, or proof that an allowed package is safe.

## Execution boundary

Registered plugin analyses use the normal CleanroomX application execution path:

1. for API v2 plugins with `external_dependencies`, the host asks the resolver
   for explicit `(field, path)` references from an isolated submitted-input copy;
2. declared files are fingerprinted and copied into verified private snapshots
   before the parser runs, and the execution-only payload is rewritten to those
   snapshots while the durable input identity remains the original submitted JSON;
3. the parser validates the execution payload; if the dependency resolver or
   parser mutates its input snapshot, CleanroomX rejects the run before the runner;
4. the runner receives the parser result, and private dependency snapshots are
   re-verified before the run can be accepted;
5. the live declared files are fingerprinted again after execution; a change,
   disappearance, instability, or size-limit violation discards the result;
6. the result must normalize to strict JSON through the existing application
   result boundary, and exact private snapshot path strings are restored to their
   original declared paths before durable result/provenance storage;
7. the optional reporter receives an isolated deep copy of the normalized
   result and must return Markdown text as a string;
8. normal result status, diagnostics, plotting discovery, input SHA-256 identity,
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

### API v2 host-managed external dependencies

API v2 adds the optional `external_dependencies` registration callable. It must
be a structural, deterministic resolver: it receives an isolated JSON payload and
returns an iterable of `(field, path)` pairs. Each `field` must name either a
top-level string field such as `"data_file"` or one list entry such as
`"source_files[0]"`, and the returned path must exactly match the value stored at
that field in the submitted payload.

For example:

```python
def dependencies(payload: dict):
    source = payload.get("measurement_file")
    return [] if source is None else [("measurement_file", source)]


registration = AnalysisPlugin(
    api_version=PLUGIN_API_VERSION,
    key="measurement_check",
    title="Measurement check",
    category="Extensions",
    description="Example file-backed analysis.",
    parser=parse,
    runner=run,
    reporter=report,
    external_dependencies=dependencies,
)
```

The host applies the same stable-file fingerprint/snapshot authority used by
built-in file-backed analyses. Each declared file is currently limited to the
shared 64 MiB application dependency ceiling. The private execution filename
preserves a safe source suffix (for example `.csv` or `.ifc`) so format-aware
parsers can operate on the snapshot. The resolver itself must not read, modify,
create, or delete the dependency; its job is only to declare identity from the
JSON payload.

API v1 remains accepted unchanged, but it cannot set `external_dependencies`.
A v1 plugin that consumes external files remains responsible for its own file
provenance and revalidation. Upgrading that plugin to API v2 is the path to the
host-managed snapshot/revalidation contract.

## Security boundary

Plugins are trusted executable Python packages. Install them only from sources
you trust and review. CleanroomX does not sandbox plugin code, authenticate plugin
publishers, or treat a distribution version as proof of source authenticity.

The plugin identity recorded in run provenance supports reproducibility and
diagnostics; it is not a digital signature or certification statement.
