# Security Notes

## Scope

CleanroomX v0.98.0 is a local Python desktop/CLI engineering application. It is not a network service, authentication system, secret store, or sandbox for hostile code. The Python package declares no third-party runtime dependencies; development/test installation adds pytest.

## Input handling

Desktop project and analysis inputs use strict JSON. Project loading rejects malformed JSON and non-finite constants such as `NaN` and `Infinity`. Project schema, version, analysis kinds, ids, and active-analysis references are validated before use.

Application workflow bindings are fixed in `src/cleanroomx/application.py`; project files select a declared analysis kind rather than arbitrary Python modules or function names.

## File access

Some workflows, including dossier and consistency workflows, can resolve user-supplied file references relative to the saved project directory. Treat project files and referenced engineering data as trusted local inputs and review their paths before execution.

Project saving uses a temporary file followed by replacement to reduce the chance of leaving a partially written project after an interrupted save.

## Operational guidance

- Run CleanroomX with normal user privileges.
- Keep engineering source files and exported reports under normal OS access controls.
- Do not place credentials, API keys, or unrelated secrets in project JSON.
- Back up source project files before migration or bulk editing.
- Review generated engineering reports before using them in downstream controlled documentation.

## Boundary

The current release has automated correctness/regression coverage, but this repository does not claim a formal independent security audit, penetration test, or hostile-input sandbox certification. Security-sensitive deployment should add the organization-specific controls required by its environment.
