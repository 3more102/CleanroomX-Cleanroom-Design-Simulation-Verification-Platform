# Security Notes

## Scope

CleanroomX v0.102.1 is a local Python desktop/CLI engineering application. It is not a network service, authentication system, secret store, or sandbox for hostile code. The Python package declares no third-party runtime dependencies; the development/test extra adds pytest.

## Input and registry handling

Desktop project and analysis inputs use strict JSON. Project loading rejects malformed JSON and non-finite constants such as `NaN` and `Infinity`. Normal project JSON is limited to 64 MiB before parsing and revision hashing; saves use the same ceiling so CleanroomX does not create a normal project it cannot reopen. Desktop analysis-input file imports now reuse the canonical 64 MiB bounded, revision-stable strict-JSON reader, including invalid-UTF-8, duplicate-key, non-finite-number, excessive-nesting, and live-path replacement/change rejection before the project is mutated. Invalid UTF-8 project bytes fail closed as a project-format error, saved revision envelopes are bounded before decoding, and portable-bundle project members reuse the same project-size authority. Project schema, version, analysis kinds, ids, and active-analysis references are validated before use.

Application workflow bindings are fixed in `src/cleanroomx/application.py`. The v0.100 registry check rejects duplicate workflow keys, requires parser/runner targets for ordinary workflows, preserves explicit custom adapters for consistency and dossier, and verifies that every declared target resolves to a callable. Project files select a declared analysis kind rather than arbitrary Python modules or function names.

Installed analysis plugins remain executable Python packages rather than a
sandbox boundary. External plugin loading is disabled by default. Operators may
explicitly set `CLEANROOMX_PLUGIN_MODE=trusted` for the historical trust-all-
installed behavior, or use `CLEANROOMX_PLUGIN_MODE=allowlist` with
`CLEANROOMX_PLUGIN_ALLOWLIST` to permit named distributions with optional exact
version pins. Denied plugins are rejected before `entry_point.load()`; malformed
policy configuration, missing allowlist identity, and version mismatch fail
closed. This trust gate is execution control, not package signing, publisher
authentication, or proof of package authenticity.

For plugins that pass the trust gate, discovery remains fail-isolated: malformed
identity metadata, import/factory exceptions, and plugin-triggered `SystemExit`
disable the affected extension instead of terminating built-in application
startup. `KeyboardInterrupt` remains an operator cancellation signal and is not
swallowed by discovery.

## File access

Some workflows, including dossier and consistency, resolve user-supplied file references relative to the saved project directory. Treat project files and referenced engineering data as trusted local inputs and review their paths before execution.

Project saving uses a temporary file followed by replacement to reduce the chance of leaving a partially written project after an interrupted save.

Portable project bundles are treated as untrusted archive input. Inspection rejects unsafe paths, duplicate or undeclared members, encryption, unsupported compression, integrity mismatches, and explicit resource-limit violations before extraction is published. Bundle extraction uses a private staging directory and never calls `ZipFile.extractall()`.

## Recovery report presentation safety

Portable Markdown reporting escapes user-controlled recovery-test traceability metadata before rendering. Newlines are kept inside the field as HTML line breaks and Markdown/HTML control characters are escaped so project input cannot forge report headings, list items, tables, or raw HTML through those metadata fields.

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


### CLI output/input separation

Standalone engineering commands that accept both file-backed inputs and
`--output` reject output destinations that alias their source engineering files,
including resolved path aliases and existing same-file aliases. Publication uses
the shared durable atomic writer with a second identity check immediately before
replacement. Multi-file consistency and dossier workflows protect every declared
source dependency in addition to their primary input/manifest.
