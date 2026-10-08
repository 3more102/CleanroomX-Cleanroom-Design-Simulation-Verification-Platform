# Multi-agent orchestration

CleanroomX supports an explicit, deterministic multi-agent orchestration layer for
project analyses. The feature coordinates existing application workflows; it does
not create a second engineering solver stack and it does not grant agents hidden
authority to invent requirements, standards limits, or engineering evidence.

## Project contract

The orchestration plan is stored under
`project.metadata.agent_orchestration`:

```json
{
  "schema_version": 1,
  "agents": [
    {
      "id": "requirements-agent",
      "analysis_id": "requirements"
    },
    {
      "id": "air-system-agent",
      "analysis_id": "air-system",
      "depends_on": ["requirements-agent"],
      "handoffs": [
        {
          "source_agent": "requirements-agent",
          "source_path": ["result", "recommended_airflow_m3_h"],
          "target_path": ["design", "airflow_m3_h"]
        }
      ]
    }
  ]
}
```

The plan `schema_version` must be the JSON integer `1` (not `1.0` or
`true`). Agent `depends_on` and `handoffs` arrays may be omitted, in which
case they are empty; explicitly setting either field to `null` or any other
non-array value is rejected.

Each agent binds to one existing project analysis. Agent IDs and referenced
analysis IDs must be unique. Dependencies form a directed acyclic graph. Ready
agents are scheduled deterministically in declaration order, so identical project
bytes produce the same plan order.

## Explicit handoffs

A handoff copies one strict-JSON value from a completed upstream run bundle into
the downstream analysis input immediately before execution.

- `source_agent` must also be present in `depends_on`.
- `source_path` addresses keys and non-negative list indexes inside the upstream
  run bundle.
- `target_path` addresses object keys inside the downstream analysis input.
- duplicate or ancestor/descendant-overlapping target paths are rejected at plan
  validation, regardless of declaration order.
- missing source paths and attempts to descend through existing non-object target
  values (including JSON `null`) fail closed. A missing intermediate object key
  may be created, but an explicit `null` is never treated as a missing key.

Every applied handoff records the upstream run SHA-256 and a canonical SHA-256 of
the transferred value. The downstream canonical application run still records its
complete post-handoff input snapshot and input SHA-256 through the normal
`run_analysis()` provenance boundary.

## Failure and revision semantics

The project is loaded once with an exact file revision. The source revision is
checked before and after every executing agent. If the project file changes, no
further agents are scheduled and the orchestration run reports the exact boundary.

By default execution is fail-fast. With continue-on-error behavior, independent
agents may still run after an error while agents whose dependencies did not
complete are recorded as `blocked`. A blocked agent is never invoked.

## CLI

```text
cleanroomx-project-agents project.cleanroomx.json
cleanroomx-project-agents project.cleanroomx.json --format markdown
cleanroomx-project-agents project.cleanroomx.json --continue-on-error
```

The command writes to stdout. Shell redirection can be used when a file is
required. This initial interface intentionally avoids introducing another
project-output write path before the existing protected-publication rules are
shared by the orchestration CLI.

## Scope

This layer is an execution and provenance foundation for specialized agents such
as requirement, design, simulation, verification, compliance, reviewer, and
dossier agents. It is deliberately not an autonomous LLM boundary. Any future
AI-backed agent should remain behind the same explicit input, dependency,
provenance, and fail-closed contracts rather than bypassing them.
