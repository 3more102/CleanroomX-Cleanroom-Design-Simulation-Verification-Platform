# Project-native requirements execution workflow

Release 3 can execute one selected analysis directly from a saved CleanroomX
project and carry the result through the existing canonical requirements and
ProofGraph pipeline.

The backend path is:

`Saved Project Revision`
→ `Selected Project Analysis`
→ `Immutable Analysis Run`
→ `Persisted Project Requirements`
→ `Persisted Explicit Evidence Mappings`
→ `Canonical Requirements Verification`
→ `ProofGraph`

This removes the need for callers to manually assemble requirements, run
bundles, mapping objects, current analysis input, or project revision identity.

## API

`run_project_requirements_workflow(project_path, analysis_id)`

The workflow:

1. loads one stable saved project revision;
2. selects the requested project analysis by stable analysis ID;
3. loads the canonical `project.metadata.requirements` registry;
4. loads the canonical
   `project.metadata.requirement_evidence_mappings` registry;
5. selects only active mappings explicitly assigned to that analysis;
6. checks the project file still matches the revision that was loaded;
7. executes the analysis with that exact project SHA-256 bound into immutable
   application execution provenance;
8. checks the project source again after execution;
9. verifies the completed run bundle and its embedded project revision;
10. converts persisted mappings to the existing immutable-run evidence binding
    model without inferring semantics;
11. derives evidence freshness from the exact analysis input and external
    dependencies;
12. invokes the existing canonical project requirements verifier;
13. projects the canonical findings and verdicts into the existing ProofGraph
    adapter.

## Fail-closed behavior

No project verification result is issued when:

- the project has no persisted requirements registry;
- the project has no persisted evidence-mapping registry;
- the requested analysis ID does not exist;
- the selected analysis has no active persisted mappings;
- a persisted mapping disagrees with the selected analysis kind;
- the project source changes between the loaded revision and analysis start;
- the project source changes during the analysis;
- the immutable analysis run is not bound to the loaded project SHA-256;
- run-bundle integrity validation fails;
- a ProofGraph verification run declares requirements/evidence/verification
  identities that disagree with the canonical workflow;
- ProofGraph source-finding metadata disagrees with the canonical verification
  findings for that requirement set;
- ProofGraph evidence or evidence-source projection disagrees with the exact
  bound workflow evidence.

A missing mapped result field is not converted into PASS. It flows through the
existing evidence binding as missing evidence and the canonical verifier reports
an incomplete/not-checked result.

## Identity

Each workflow result exposes a deterministic `workflow_sha256` derived from:

- exact source-project SHA-256;
- selected analysis identity and kind;
- normalized requirements digest;
- normalized persisted mappings digest;
- exact active mapping IDs;
- immutable run-bundle digest;
- canonical verification digest;
- ProofGraph digest(s).

The source path is reported for usability but is intentionally not part of the
engineering identity.

The component verifier does not rely on those digests alone. It also checks the
cross-artifact links between the canonical verification, bound evidence, and
ProofGraph projection. Recomputing both a ProofGraph digest and the outer workflow
digest after changing ProofGraph metadata or evidence therefore does not make the
modified projection acceptable.

The verifier also requires exact requirement and evidence coverage across the
workflow's ProofGraphs and reconstructs the deterministic check, finding,
verdict, verification-run, and graph identities from the canonical verification
findings. A producer cannot make a projection acceptable by dropping retained
evidence, omitting a canonical requirement, or rewriting a finding/verdict and
then resealing the graph and workflow hashes.

## Authority boundaries

This workflow is orchestration only. It does not implement requirement
comparison logic, infer engineering units, guess solver-output semantics, or
claim regulatory compliance.

The existing project requirements verifier remains the only comparison
authority. The existing immutable run verifier remains the run-integrity
authority, and the existing ProofGraph adapter remains a projection of canonical
verification output.


## Operator CLI

The canonical workflow is available without custom Python integration:

```text
cleanroomx-project-verify run project.cleanroomx.json <analysis-id>
cleanroomx-project-verify run project.cleanroomx.json <analysis-id> --output workflow.json
cleanroomx-project-verify persist project.cleanroomx.json <analysis-id>
```

The `run` form does not mutate the project. The `persist` form executes the same
workflow and then passes it through the guarded project verification persistence
boundary. See `PROJECT_VERIFICATION_OPERATOR_CLI.md` for exit-code and
publication semantics.
