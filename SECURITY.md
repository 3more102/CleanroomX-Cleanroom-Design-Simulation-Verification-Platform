# Security Notes

## Scope

CleanroomX v0.100.0 is a local Python desktop/CLI engineering application. It is not a network service, authentication system, secret store, or sandbox for hostile code. The Python package declares no third-party runtime dependencies; the development/test extra adds pytest.

## Input and registry handling

Desktop project and analysis inputs use strict JSON. Project loading rejects malformed JSON and non-finite constants such as `NaN` and `Infinity`. Project schema, version, analysis kinds, ids, and active-analysis references are validated before use.

Application workflow bindings are fixed in `src/cleanroomx/application.py`. The v0.100 registry check rejects duplicate workflow keys, requires parser/runner targets for ordinary workflows, preserves explicit custom adapters for consistency and dossier, and verifies that every declared target resolves to a callable. Project files select a declared analysis kind rather than arbitrary Python modules or function names.

## File access

Some workflows, including dossier and consistency, resolve user-supplied file references relative to the saved project directory. Treat project files and referenced engineering data as trusted local inputs and review their paths before execution.

Project saving uses a same-directory temporary file, file flush/fsync, atomic replacement, parent-directory fsync where supported, and strict-loader read-back verification. New project files also contain a canonical SHA-256 integrity record, and new recovery artifacts contain a separate SHA-256 envelope digest. Integrity mismatches are rejected instead of being loaded silently. GUI saves also retain the optimistic external-revision checks that protect newer on-disk content.

These digests detect accidental or uncoordinated content modification; they are not authentication, digital signatures, or proof that engineering inputs are physically correct or trustworthy.

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
