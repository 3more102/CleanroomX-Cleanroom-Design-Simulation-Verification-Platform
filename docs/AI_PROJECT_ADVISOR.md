# CleanroomX AI Project Advisor (read-only)

The project advisor is an optional conversational layer over an **existing,
saved** CleanroomX project. It builds on the existing
`cleanroomx.multi_agent` conversation/revision model. It does **not** replace
`run_analysis()`, run CFD, edit geometry, prescribe design criteria, or
certify cleanroom compliance.

## Start

From an installed development checkout:

```powershell
python -m pip install -e .
cleanroomx-ai-gui "C:\path\to\facility.cleanroomx.json"
```

The window starts in **offline** mode and lists the saved analyses without
contacting a model provider. To enable model-backed explanations, choose
`openai` and set your API key as a local environment variable before
launching:

```powershell
$env:OPENAI_API_KEY = "YOUR_OWN_KEY"
cleanroomx-ai-gui "C:\path\to\facility.cleanroomx.json"
```

Do not store an API key inside a project, Git repository, workspace file,
command-line argument, or screenshot. API use may incur provider charges.

## Command line

```powershell
cleanroomx-ai facility.cleanroomx.json "List configured analyses"
cleanroomx-ai facility.cleanroomx.json "What should I verify next?" --provider openai
cleanroomx-ai facility.cleanroomx.json "Review project structure" --workspace assistant-chats.json
cleanroomx-ai facility.cleanroomx.json "What can I conclude?" --format json
```

The optional workspace uses the established multi-chat JSON format. It must
not be the project itself. Workspace export is explicit in the GUI and
optional in the CLI; there is no automatic publication to the engineering
dossier.

## Data and trust boundaries

**Local only (default):** The offline review reads a saved, schema-validated
project and displays its name, SHA-256, and configured analysis identifiers.
It does not call a network API. This is a deterministic summary, not
generative AI.

**OpenAI (explicit opt-in):** The client sends the question, up to six
recent chat messages, and a **bounded whitelist** of saved project metadata:
project name, description, active analysis id, analysis ids/names/kinds,
analysis count, and the source file's SHA-256. No saved analysis input
dictionaries, user metadata, geometry files, solver logs, or raw results are
included automatically. Names, descriptions, and chat text may themselves
contain sensitive information; review what is saved before opting in.

The optional adapter uses the OpenAI Responses API over HTTPS, reads
`OPENAI_API_KEY` from the runtime environment, uses `store=false`, and
does not enable model tools or autonomous actions. Transport failures, empty
responses, and incomplete responses are reported as errors rather than
misrepresented as engineering conclusions. `store=false` controls Responses
API storage behavior; it is not a general promise about every provider
retention or legal requirement.

The assistant rechecks the exact project file revision before and after
responding. If the file changes, the answer is rejected as stale. The
multi-agent chat core separately guards against chat revision conflicts.

**Engineering evidence: NOT VERIFIED.** A list of saved analysis definitions
is not evidence that those analyses completed or passed. AI-generated text
is advisory, and it cannot alter or create canonical solver receipts,
ProofGraph nodes, qualification results, or acceptance evidence.

## Current limitations

- The model is only given a minimal project *manifest*, not actual verified
  engineering results. It can help organize review tasks, but cannot reliably
  answer numerical or compliance questions.
- No solver execution, design-edit proposal/approval, GUI docking in the main
  CleanroomX workspace, automatic RAG over external standards, or verified
  report generation is implemented in this slice.
- The desktop assistant opens as a separate Tk window.
- A full end-to-end OpenAI request requires a valid user-configured key and
  network access. Automated tests mock this transport without sending data.

## Verification

```bash
python -m pytest -q tests/test_ai_assistant.py
```

Tests exercise local metadata redaction, source revision detection, provider
opt-in, request flags, failure handling, session export, and project overwrite
protection. The full CFD regression remains a separate release requirement.
