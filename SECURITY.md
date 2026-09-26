# Security Notes

## Scope

CleanroomX v0.102.1 is a local Python desktop/CLI engineering application. It is not a network service, authentication system, secret store, or sandbox for hostile code. The Python package declares no third-party runtime dependencies; the development/test extra adds pytest.

## Input and registry handling

Desktop project and analysis inputs use strict JSON. Project loading rejects malformed JSON and non-finite constants such as `NaN` and `Infinity`. Project schema, version, analysis kinds, ids, and active-analysis references are validated before use.

Application workflow bindings are fixed in `src/cleanroomx/application.py`. The v0.100 registry check rejects duplicate workflow keys, requires parser/runner targets for ordinary workflows, preserves explicit custom adapters for consistency and dossier, and verifies that every declared target resolves to a callable. Project files select a declared analysis kind rather than arbitrary Python modules or function names.

Installed analysis plugins remain trusted executable Python packages, but plugin
discovery is fail-isolated: malformed identity metadata, import/factory
exceptions, and plugin-triggered `SystemExit` disable the affected extension
instead of terminating built-in application startup. `KeyboardInterrupt`
remains an operator cancellation signal and is not swallowed by discovery.

## File access

Some workflows, including dossier and consistency, resolve user-supplied file references relative to the saved project directory. Treat project files and referenced engineering data as trusted local inputs and review their paths before execution.

Project saving uses a temporary file followed by replacement to reduce the chance of leaving a partially written project after an interrupted save.

## Operational guidance

- Run CleanroomX with normal user privileges.
- Keep engineering source files and exported reports under normal OS access controls.
- Do not place credentials, API keys, or unrelated secrets in project JSON.
- Back up source project files before migration or bulk editing.
- Review generated engineering reports before using them in downstream controlled documentation.

## Boundary

Automated correctness/regression coverage is not a formal independent security audit, penetration test, or hostile-input sandbox certification. Security-sensitive deployment requires organization-specific controls.


## v0.100 file-integrity evidence

Successful application runs record a canonical SHA-256 identity for the submitted input. File-backed consistency and dossier workflows record before/after SHA-256 plus byte-size evidence for referenced files so changes during a run are visible in Diagnostics and exported run bundles. These hashes are integrity/provenance evidence, not authentication or a digital signature.
