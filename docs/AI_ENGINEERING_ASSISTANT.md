# CleanroomX AI Engineering Assistant

## Purpose and status

This is a **first, read-only AI assistance slice**, implemented on top of the
existing CleanroomX desktop project and canonical project diagnostics.
It does not replace the engineering backends, interpret design targets as
computed performance, or claim ISO certification. It does not perform solver
operations, optimization, IFC edits, or automated project modifications.

Open **Tools > AI Engineering Assistant...** in the normal
`cleanroomx-gui` desktop.

The window now also has a **Conversation** selector, **New**, **Save chats...**
and **Load chats...** buttons. Conversations are independent and bound to a
local project identity. Model context uses at most 12 prior messages from
complete question-answer pairs, with a 12,000-character history limit.
Concurrent/stale chat writes are rejected through the existing
`ChatSessionStore` revision and incarnation checks.

**Chat persistence is deliberately explicit:** messages live in memory until
Save chats is clicked. Saved workspaces use the existing strict-JSON
multi-agent workspace format and atomic writer. The files contain full
questions, model responses and their limited provenance metadata; protect
them as project documents. Loading an AI workspace asks before replacing
in-memory conversations. The save dialog refuses to overwrite unrelated JSON
(including normal CleanroomX project files).

The window also includes **Next actions (offline)**. This creates a digest-bound,
read-only worklist from exactly the canonical diagnostic findings already
available to CleanroomX. It sorts errors before warnings before informational
findings, records the project snapshot identity, and marks every action as
**proposal not executed**. This is not autonomous optimization, does not
rewrite project files, and does not imply compliance.

The window has two independent functions:

1. **Review project (offline):** deterministic review of the canonical
   `analyze_project_diagnostics` result, with explicit rule IDs and suggested
   corrective actions. It uses no LLM and makes no network request.
2. **Ask AI:** sends one bounded project evidence snapshot, the question, and
   up to 12 prior conversation messages to a model *only after* you press the button. The response is clearly marked
   an unverified suggestion and is not used as solver/verification evidence.

The assistant snapshot includes project name, in-memory SHA-256 identity,
bounded analysis names/types, diagnostic severity/counts/findings, the latest
15 validated run-ledger metadata entries (status, timestamps, record digests),
and retained verification status summaries. These run statuses are **not**
CFD convergence claims. The diagnostic snapshot **does not include**
raw room geometry, full analysis inputs, CFD fields, solver residual arrays,
files, or project metadata. Names, diagnostic messages and previously entered chat messages can still
contain sensitive information: inspect your project before enabling cloud mode.

The snapshot identity is calculated from the current **in-memory** project,
not assumed to be identical to any on-disk revision. If the project changes
while the model is responding, the GUI warns that the suggestion concerns
an older snapshot.

## Local model (default, no external cloud upload)

Install [Ollama](https://ollama.com/) separately and pull a local model, for
example:

```powershell
ollama pull llama3.2
$env:CLEANROOMX_AI_PROVIDER = "ollama"
$env:CLEANROOMX_AI_MODEL = "llama3.2"
cleanroomx-gui --demo
```

The assistant uses the documented local compatibility endpoint
`http://127.0.0.1:11434/v1/chat/completions`.
If no Ollama service or model is available, **Review project (offline)**
still works. No API keys are needed for Ollama's local endpoint.
See [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility).

## Explicit cloud opt-in

The only supported cloud provider in this slice is OpenAI's
`https://api.openai.com/v1/chat/completions`. Cloud transmission is
**disabled** unless `CLEANROOMX_AI_ALLOW_CLOUD=1` is set. It also requires
a model identifier and an API key in the process environment:

```powershell
$env:CLEANROOMX_AI_PROVIDER = "openai"
$env:CLEANROOMX_AI_MODEL = "<your-supported-chat-model>"
$env:CLEANROOMX_AI_ALLOW_CLOUD = "1"
# Provide OPENAI_API_KEY securely via environment/secret management.
cleanroomx-gui --demo
```

Do not put API keys in project JSON, source control, screenshots or reports.
Cloud requests may have usage charges. The engineering review never
requires a paid service.

## Recorded multiroom CFD evidence (project-bound, engineering HOLD)

Open **Tools > AI Engineering Assistant...** and click
**Review CFD export...**. Select the `report.json` created by the existing
CleanroomX multiroom CFD export workflow. This is a **local, offline**
operation. The companion `engineering-review.json`, when present, must
match a freshly computed `review_recorded_multizone()` result.

The import fails closed unless:

- The project is saved, the in-memory project matches the on-disk model,
  and the exported `provenance.project_source_sha256` matches the exact
  saved project bytes.
- The report is a strict, bounded, stable JSON file; symlinked inputs,
  oversized exports, malformed numbers, and changed files are rejected.
- The canonical OpenFOAM result-review contract finds consistent mesh,
  selected SIMPLE iteration, room/door pressure differences, face fluxes,
  and boundary flow balance.
- A supplied engineering-review companion is identical to the canonical
  recomputation and remains stable during import.

The assistant then displays bounded room-mean relative pressures, flow
imbalances, door flux/delta comparisons, iteration convergence marker,
source identifiers and **engineering release HOLD**. If an AI request is
made, the same evidence is reloaded and rechecked. Responses generated
from a changed source are marked stale and never included in later model
history. Conversation context is filtered by *both* project revision and
the exported CFD report SHA-256.

**The importer does not independently authenticate OpenFOAM outputs.**
A project-matching hash and internally consistent JSON do not establish
that a physical solver ran, a mesh is independent, boundary conditions
are physically valid, or results are certified. This feature cannot
demonstrate a closed-door 5 Pa cascade from the all-doors-open scenario.
No automatic model/CFD edits or numerical solver operations are performed.

## Offline AI evidence review from CLI

For command-line workflows and CI you can use the same project-aware,
read-only diagnostic context without needing a Tk display or any AI provider:

```bash
cleanroomx-ai-review path/to/project.json
cleanroomx-ai-review path/to/project.json --actions --format json
cleanroomx-ai-review path/to/project.json --max-findings 30
```

This command captures the saved project revision, builds the canonical
diagnostics-based context, and verifies that the source revision did not change
while preparing the result. The JSON envelope explicitly records
`model_used: false`, `network_used: false` and
`source_stable_during_review: true` on a successful run.
A failed revision check returns exit code 2 and discards the result.
No project files, solver inputs or engineering settings are modified.
The action plan is a proposal and requires separate review and authorization.
No compliance, CFD convergence or physical validation is implied.

**Project-revision conversation isolation:** The GUI now sends previous AI
conversation turns to the model only when both sides of an exchange are tied
to the *same current in-memory project SHA-256*. Answers received after the
project changed are excluded. The human-visible transcript remains available
to audit earlier conversations; it is not silently treated as current evidence.

## Architecture and safeguards

- `src/cleanroomx/ai_assistant.py`: bounded read-only context, deterministic
  review, secure provider configuration and non-streaming chat transport.
- `src/cleanroomx/ai_assistant_ui.py`: optional Tk window, local/offline
  review, background model request, revision warning, failure feedback.
- Existing `project_diagnostics.py` remains the evidence authority.
- Existing `multi_agent.py`, `multi_agent_project.py` and
  `agent_orchestration.py` are the planned future agent coordination
  foundations. This MVP does not yet connect model outputs to them.
- Fixed local/cloud endpoints, finite request timeout, bounded response size,
  no arbitrary model-supplied tool invocations or arbitrary URLs.
- No project mutations, report edits, CFD runs or automatic push are possible
  through assistant answers.
- Model text is labeled *unverified engineering suggestion*.

Select a **Review focus** of general, CFD, HVAC, particles or verification to
steer explanations to that topic. These modes guide the same bounded evidence
snapshot; they do not unlock hidden measurement data or execute solvers.

The assistant is **not** a physical validation, commissioning, quality or
regulatory compliance system. Diagnostic checks cover only configured
model/data rules. The AI cannot independently confirm any value absent
from the provided evidence.

## Next engineering phases

**Phase 2 — Specialist assistants:** add role-specific, evidence-bound context
for CFD/meshing, HVAC, geometry, contamination, and evidence review. Shared
multi-agent orchestration remains future work; no new solver claims.

**Phase 3 — Draft engineering actions:** show proposed edits as structured
diffs with units, justifications, input-revision bindings and explicit human
approval before passing them to the existing project transaction APIs.

**Phase 4 — Controlled runs:** queue canonical solver/verification workflows
with resource limits, cancellation, provenance checks, report binding and
refusal to promote a non-converged run into a verified result.

**Phase 5 — Evidence-grounded retrieval:** reference project-controlled
standards, manufacturer data, exact revisions and documented assumptions;
never fabricate thresholds or regulatory claims.

**Phase 6 — Assisted optimization:** explore parametric HVAC/pressure/particle
design alternatives, with independent reruns, mesh/convergence quality gates,
numerical-vs-physical validation distinction, and measured decision criteria.

## Verification

Run:

```bash
python -m pytest tests/test_ai_assistant.py tests/test_ai_assistant_chat.py tests/test_ai_assistant_plan.py -q
python -m pytest tests/test_ai_assistant_cli.py -q
python -m pytest tests/test_ai_cfd_evidence.py -q
python -m pytest tests/test_gui.py -q
# With a graphical display/Xvfb:
python -m pytest tests/test_ai_assistant_ui.py -q
```

The former tests context boundaries, local/cloud opt-in, sanitized failures,
and mock transport. Real Ollama/OpenAI end-to-end inference and Tk interactive
operation require an appropriately configured user workstation; passing
unit tests does not prove either.
