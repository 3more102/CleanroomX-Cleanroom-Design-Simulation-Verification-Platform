# Project batch automation

CleanroomX provides a project-level headless runner through the `cleanroomx-project-run` command and the `cleanroomx.project_batch.run_project_file()` API.

The batch runner reuses the same validated application registry and `run_analysis()` service used by the desktop application. It does not implement parallel parser, solver, reporter, or acceptance logic.

## Command-line workflow

Run every analysis in project order:

```bash
cleanroomx-project-run project.cleanroomx.json
```

Run only selected analyses. Repeating `--analysis` selects multiple IDs; execution still follows the order stored in the project:

```bash
cleanroomx-project-run project.cleanroomx.json \
  --analysis room-verification \
  --analysis hvac-analysis
```

Stop scheduling analyses after the first execution error:

```bash
cleanroomx-project-run project.cleanroomx.json --fail-fast
```

Write a machine-readable report atomically:

```bash
cleanroomx-project-run project.cleanroomx.json \
  --format json \
  --output project-run.json
```

Write a concise Markdown summary:

```bash
cleanroomx-project-run project.cleanroomx.json \
  --format markdown \
  --output project-run.md
```

## Execution contract

The runner:

- loads the project through `load_project_document_with_revision()`;
- records the exact parsed project SHA-256 and byte size;
- takes one in-memory project snapshot for the batch;
- executes analyses sequentially in persisted project order;
- deep-copies each analysis input before execution;
- resolves relative consistency/dossier references against the project directory;
- delegates validation, execution, result normalization, reporting, plotting, and execution provenance to `run_analysis()`;
- checks the project-file revision before and after every attempted analysis;
- stops scheduling new analyses when the source project changes or becomes unreadable;
- isolates an ordinary analysis exception into that analysis's outcome and continues unless `--fail-fast` is requested;
- never writes back to the project file.

The batch report preserves each completed `AnalysisRun`, including its existing application execution provenance and canonical input SHA-256.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Every scheduled analysis executed without an execution exception, and the project source remained unchanged. |
| `2` | The project could not be loaded/selected, output failed, or at least one scheduled analysis raised an execution/validation error. |
| `3` | The project source changed or could no longer be verified during the batch. Further analyses were not scheduled. |

An engineering result such as PASS, FAIL, indeterminate, incomplete, or another workflow-specific status is retained as analysis output. It is not reinterpreted as a process exit code by the batch layer.

## Determinism and traceability

For a fixed project file, selected analysis set, referenced external inputs, CleanroomX version, and deterministic backend behavior:

- analysis scheduling order is deterministic;
- the batch envelope contains no wall-clock timestamps or duration measurements;
- the project source identity is SHA-256 based;
- each completed application run retains the existing canonical analysis-input SHA-256;
- external-file workflows retain the existing before/after dependency fingerprints from `run_analysis()`;
- JSON serialization rejects non-finite values.
- Markdown summaries escape project-controlled and error text so it cannot alter report structure.

The batch runner cannot make a nondeterministic third-party or future backend deterministic. Its responsibility is deterministic orchestration and explicit evidence around the existing backend behavior.

## Python API

```python
from cleanroomx.project_batch import run_project_file

batch = run_project_file(
    "project.cleanroomx.json",
    analysis_ids=["room-verification", "hvac-analysis"],
    fail_fast=False,
)
payload = batch.to_dict()
```

`ProjectBatchRun.outcomes` contains one outcome for each analysis that was actually attempted. If source revision verification fails, analyses that had not started are intentionally absent rather than reported as if they ran.

## Compatibility and limitations

- The persisted `cleanroomx.project` schema remains version 1.
- Existing application, solver, reporter, CLI, GUI, autosave, recovery, and project-save APIs are unchanged.
- No engineering equation, tolerance, convergence rule, acceptance criterion, or unit convention is changed.
- Execution is intentionally sequential. This avoids introducing solver concurrency assumptions and keeps scheduling deterministic.
- The current runner does not provide resume, result caching, process isolation, or cancellation.
- A batch report is execution/provenance evidence; it is not a substitute for an engineering dossier, certification, commissioning/TAB evidence, CFD validation, or manufacturer approval.
