# Multi-agent orchestration

CleanroomX multi-agent orchestration is a coordination layer over the existing
engineering, diagnostics, requirements-verification, and ProofGraph services. It
does **not** introduce a second solver, a second compliance authority, or an
agent-generated engineering verdict.

The first implementation is in `cleanroomx.multi_agent`.

## Design goals

The runtime provides:

- explicit named agents and declared capabilities;
- an explicit task DAG instead of hidden or nondeterministic routing;
- parallel execution of independent tasks;
- dependency-aware blocking after upstream failure;
- strict-JSON task inputs and outputs;
- deterministic task ordering in the retained run document;
- SHA-256 identity for the plan, every task result, dependency handoffs, and the
  complete run;
- a verifier that detects changed plans, changed outputs, changed dependency
  links, result reordering, and aggregate-status tampering;
- adapters that delegate to canonical CleanroomX services rather than
  reimplementing engineering logic.

## Authority boundary

An agent may plan, route, summarize, compare, or invoke an existing canonical
service. It must not silently replace that service's authority.

For example:

- an HVAC agent may invoke a registered CleanroomX analysis;
- a diagnostics agent may invoke `analyze_project_diagnostics()`;
- a requirements agent may invoke
  `run_project_requirements_workflow()`, which remains responsible for
  evidence binding, canonical requirement comparison, and ProofGraph projection;
- an AI/LLM agent may propose a corrective action, but that proposal is
  advisory until an existing deterministic CleanroomX service evaluates the
  changed engineering state.

This keeps the current evidence and verification model intact.

## Built-in agents

`built_in_agents()` currently exposes three adapters:

| Agent | Capabilities | Canonical service |
| --- | --- | --- |
| `analysis` | `analysis`, `engineering-service` | `application.run_analysis()` |
| `project-diagnostics` | `project`, `diagnostics` | `project_diagnostics.analyze_project_diagnostics()` |
| `project-requirements` | `project`, `requirements`, `verification`, `proofgraph` | `project_requirements_workflow.run_project_requirements_workflow()` |

Project-facing adapters retain source-revision checks. The requirements adapter
also inherits the existing workflow's before/during execution project-revision
guarding.

## Example

```python
from cleanroomx.multi_agent import (
    AgentPlan,
    AgentTask,
    MultiAgentOrchestrator,
    built_in_agents,
    verify_multi_agent_run,
)

plan = AgentPlan(
    id="room-a-review",
    tasks=(
        AgentTask(
            id="project-health",
            agent="project-diagnostics",
            payload={"project_path": "project.cleanroomx.json"},
            required_capabilities=("diagnostics",),
        ),
        AgentTask(
            id="room-a-verification",
            agent="project-requirements",
            payload={
                "project_path": "project.cleanroomx.json",
                "analysis_id": "room-a",
            },
            depends_on=("project-health",),
            required_capabilities=("verification", "proofgraph"),
        ),
    ),
)

runtime = MultiAgentOrchestrator(built_in_agents())
run = runtime.execute(plan, max_workers=4)
integrity = verify_multi_agent_run(run)
```

The dependency above is deliberate: requirements verification is blocked if the
project-health task fails to execute. A future policy layer may distinguish
execution failure from diagnostic findings, but an agent must never infer that
distinction implicitly.

## Recommended CleanroomX agent topology

The runtime is intentionally generic enough to support a richer set of
specialists without changing canonical engineering semantics:

1. **Supervisor / planner** — decomposes a user goal into explicit tasks and
   dependencies. It has orchestration authority only.
2. **BIM / IFC agent** — resolves model identity, spaces, systems, and IFC
   provenance through the existing BIM/IFC services.
3. **HVAC / airflow agent** — invokes canonical airflow, ACH, duct, fan, thermal,
   psychrometric, and related analyses.
4. **Pressure-network agent** — invokes pressure-network and
   pressure-design-consistency services.
5. **Contamination / recovery agent** — handles particle/recovery studies through
   existing analysis services.
6. **Requirements agent** — maps saved requirements to explicit evidence and
   invokes canonical verification.
7. **Verification critic** — checks completeness, stale evidence, diagnostics,
   assumptions, and run integrity. It may reject a handoff but does not rewrite
   a solver verdict.
8. **Evidence / ProofGraph agent** — projects canonical results into traceable
   evidence structures and validates hashes/provenance.
9. **Report agent** — produces human-readable summaries from already verified
   machine records.

The recommended execution shape is:

```text
                         Supervisor
                             |
          +------------------+------------------+
          |                  |                  |
       BIM/IFC          HVAC/Airflow       Pressure
          |                  |                  |
          +------------------+------------------+
                             |
                    Requirements Agent
                             |
                     Verification Critic
                             |
                    Evidence / ProofGraph
                             |
                         Report Agent
```

Independent engineering analyses can run in the same DAG wave. Verification and
evidence tasks should depend on the exact upstream results they consume.

## AI/LLM backends

The runtime deliberately has no mandatory AI SDK dependency. An AI provider can
be added by implementing the small `Agent` protocol:

```python
class Agent(Protocol):
    spec: AgentSpec

    def run(self, task: AgentTask, context: AgentContext) -> Mapping[str, Any]:
        ...
```

A provider-backed agent should return strict JSON and declare its authority as
`advisory` or `orchestration`. Engineering acceptance remains with the
existing CleanroomX deterministic service invoked by a canonical-service agent.

This separation allows local models, hosted models, or future provider APIs to
be swapped without coupling CleanroomX engineering semantics to one vendor.

## Integrity model

For each task the runtime retains:

- task id and selected agent;
- dependency ids;
- SHA-256 of every dependency result consumed;
- strict-JSON output or normalized failure information;
- task-result SHA-256.

The complete run retains:

- schema and schema version;
- full task plan and plan SHA-256;
- optional caller-supplied source revision;
- exact registered agent specifications;
- ordered task results;
- aggregate execution status;
- whole-run SHA-256.

`verify_multi_agent_run()` verifies those relationships without re-running
engineering services. It is an orchestration-integrity check, not a replacement
for solver-specific replay, project requirements verification, or ProofGraph
verification.

## Next integration slices

The safe progression is:

1. land the orchestration core and regression tests;
2. add a CLI/API plan loader and persisted multi-agent run artifact;
3. add GUI task/run inspection with agent handoff traces;
4. add more canonical-service adapters for BIM, airflow, pressure, uncertainty,
   recovery, dossier, and traceability;
5. add an optional provider-backed supervisor and specialist agents;
6. require any AI-proposed engineering change to pass deterministic
   re-analysis, canonical verification, and ProofGraph evidence generation
   before it can be presented as verified.

This preserves CleanroomX's current fail-closed verification direction while
adding parallel, inspectable multi-agent coordination.
