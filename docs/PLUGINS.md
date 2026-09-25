# CleanroomX Analysis Plugin API v1

CleanroomX can discover optional trusted engineering workflows without modifying the core solver package. The public contract is intentionally narrow: a plugin contributes parser/runner/reporter callables to the existing application service path. It does not receive access to private GUI objects, persistence internals, autosave state, or solver globals.

## Trust and execution boundary

Analysis plugins are installed Python packages and execute with the same local process permissions as CleanroomX. Install plugins only from sources you trust. Discovery validates software contracts and prevents a malformed descriptor from partially changing the application registry; it is not a security sandbox.

A plugin failure during discovery is isolated from the core workflow catalog. `cleanroomx-gui --check` reports the failure and exits non-zero, while valid core workflows remain registered. Interactive startup reports the degraded plugin state in the status line.

## Entry point

Plugin packages register one or more descriptor factories in the `cleanroomx.analysis_plugins` entry-point group:

```toml
[project.entry-points."cleanroomx.analysis_plugins"]
acme = "acme_cleanroomx:plugin"
```

The entry point may resolve directly to an `AnalysisPlugin` instance or to a zero-argument callable returning one.

## API contract

```python
from cleanroomx.plugin_api import AnalysisPlugin, PluginAnalysisSpec


def parse_input(payload: dict) -> dict:
    if set(payload) != {"value"}:
        raise ValueError("input must contain exactly 'value'")
    value = float(payload["value"])
    if value < 0:
        raise ValueError("value must be non-negative")
    return {"value": value}


def run_model(model: dict) -> dict:
    return {
        "status": "complete",
        "value": model["value"],
        "doubled": 2.0 * model["value"],
    }


def render_report(result: dict) -> str:
    return f"# ACME Example\n\nDoubled value: {result['doubled']}\n"


def plugin() -> AnalysisPlugin:
    return AnalysisPlugin(
        name="acme.engineering",
        version="1.2.0",
        analyses=(
            PluginAnalysisSpec(
                key="plugin.acme.engineering.double",
                title="ACME deterministic double",
                category="Extensions",
                parser=parse_input,
                runner=run_model,
                reporter=render_report,
                description="Example deterministic plugin workflow.",
            ),
        ),
    )
```

API v1 requires:

- `api_version == 1`;
- a lowercase plugin name using letters, digits, `.`, `_`, or `-`;
- a non-empty plugin version string;
- a non-empty tuple of `PluginAnalysisSpec` values;
- every analysis key under `plugin.<plugin-name>.`;
- non-empty title, category, and description;
- callable parser and runner; reporter is optional but must be callable when supplied;
- no key collision with core workflows or another successfully loaded plugin.

The entire descriptor is validated before any of its analyses are registered. A plugin with one invalid analysis therefore contributes zero workflows.

## Runtime contracts

The parser receives the analysis input JSON object and should validate all plugin-specific engineering assumptions. The runner receives the parser output. The reporter, when supplied, receives CleanroomX's normalized result dictionary.

Runner results must be a dictionary, dataclass, or expose `to_dict()`. CleanroomX converts the result to a dictionary and verifies that it is strict JSON with no NaN or Infinity before publishing it. The existing application result, diagnostic, plotting, export, and background execution behavior remains in force.

Plugins should keep engineering units explicit in field names, reject invalid/non-finite numerical inputs, document tolerances and assumptions, avoid mutable module-global run state, and make deterministic calculations where technically possible.

## Reproducibility and project compatibility

Every plugin run records `analysis_provider="plugin"` plus a `plugin_identity` containing the plugin name, plugin version, and plugin API version. Cached-run ownership requires that identity to still match the active registry, so changing the installed plugin version invalidates reuse of prior in-memory evidence.

The CleanroomX project schema remains version 1. Plugin analysis kinds are persisted exactly like core analysis kinds. Opening a project that references a missing or incompatible plugin fails closed with an actionable error; CleanroomX does not reinterpret the unknown workflow as a core analysis.

Changing a plugin implementation without changing its declared version defeats the version-level provenance signal. Plugin publishers should change `version` whenever behavior that can affect analysis results changes.

## Validation

Run:

```bash
cleanroomx-gui --check
```

The JSON output includes `plugin_api_version`, the deterministic plugin-discovery report, registry counts, and the full analysis catalog. A clean installation with no plugins reports zero discovered plugins and status `ok`.
