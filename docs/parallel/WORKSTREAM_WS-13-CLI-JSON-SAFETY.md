# WORKSTREAM WS-13-CLI-JSON-SAFETY

- Worker ID: WS-13-CLI-JSON-SAFETY
- Branch: dev/WS-13-CLI-JSON-SAFETY
- Starting SHA: 2cccdbacff36e609cf9d39996cd36886bd574f35
- Assigned scope: Harden strict JSON result serialization for the stable HVAC, recovery-test, duct-flow, and dossier CLIs only.
- Production files intentionally modified: src/cleanroomx/cli_output.py, src/cleanroomx/hvac_cli.py, src/cleanroomx/recovery_cli.py, src/cleanroomx/duct_flow_cli.py, src/cleanroomx/dossier_cli.py
- Tests added: tests/test_cli_strict_json_output.py
- Documentation: docs/CLI_JSON_OUTPUT.md
- Shared interfaces changed: one additive internal helper, cleanroomx.cli_output.dumps_strict_json
- Schema/migration changes: none
- Solver/tolerance/engineering-rule changes: none
- Integration order: independent of current reporting, bundle, diagnostics, project-IO, air-balance, and design-consistency workstreams.
