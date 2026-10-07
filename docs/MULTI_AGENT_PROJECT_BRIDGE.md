# Multi-agent canonical project bridge

The multi-chat orchestration layer can register specialists that execute a fixed
analysis from a saved CleanroomX project through the existing canonical
`cleanroomx.application.run_analysis()` boundary.

The bridge lives in `cleanroomx.multi_agent_project`.

## Authority boundary

This adapter does not add a second solver, copy engineering equations into the
agent layer, or allow a model response to become engineering evidence.

For every invocation it:

1. loads one exact project byte revision with
   `load_project_document_with_revision()`;
2. resolves one fixed, pre-registered analysis id;
3. rechecks that the project source is unchanged immediately before execution;
4. deep-copies the persisted analysis input and delegates to
   `run_analysis()`;
5. passes the project SHA-256 into the canonical analysis provenance field;
6. rechecks the source after execution and rejects the result if the project
   changed while the solver was running;
7. returns the canonical analysis run bundle, including its existing integrity
   digest, inside strict-JSON agent data.

A project-backed agent therefore cannot silently substitute a different
analysis kind or mutate the saved analysis input.

## Registration

```python
from cleanroomx.multi_agent import ChatSessionStore, MultiAgentCoordinator
from cleanroomx.multi_agent_project import register_project_analysis_agent

store = ChatSessionStore()
store.create_session("design-review", "Design review")
coordinator = MultiAgentCoordinator(store)

register_project_analysis_agent(
    coordinator,
    "airflow",
    project_path="project.cleanroomx.json",
    analysis_id="air-system",
)

result = coordinator.run(
    "design-review",
    "Run the saved airflow analysis.",
    agent_ids=["airflow"],
)
```

The registered specialist declares both
`cleanroomx.project-analysis` and `engineering-analysis` capabilities.

## Concurrency and drift behavior

The chat layer already prevents stale agent batches from being committed when
the same conversation changes concurrently. The project bridge adds a separate
engineering-source boundary: if the saved project changes before or during the
canonical solver call, the specialist returns an error execution and no
stale engineering result is presented as completed.

These are independent protections:

- chat revision checks protect conversational ordering;
- project revision checks protect engineering input provenance.

## Deliberate scope

The first bridge is intentionally pinned to persisted analysis input. It does
not accept free-form prompt values as solver overrides. Future editable-design
workflows should first produce a validated project change or another explicit,
schema-checked engineering input artifact, then re-run the canonical service.
