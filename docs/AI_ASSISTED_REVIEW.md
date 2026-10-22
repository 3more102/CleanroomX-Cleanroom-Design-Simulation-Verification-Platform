# CleanroomX local AI engineering reviewer (experimental)

This opt-in CLI is an **advisory interface**, not a CFD solver, convergence checker,
cleanroom qualification tool or design writer. It uses the existing
`ProjectAnalysisAgent` and `MultiAgentCoordinator`; it does not replace
the authoritative application services or change the project schema.

## Requirements

1. Install the repository in the active Python environment:
   `python -m pip install -e .`
2. Start a local Ollama server on `127.0.0.1:11434` and install a model
   of your choice. An internet connection and cloud-model API key are not
   required for the CLI at review time. Ollama and the model are **not**
   bundled with CleanroomX.
3. Use a valid existing CleanroomX project JSON with one or more defined
   analysis ids. The CLI runs those canonical project analyses afresh.
   Analyses may still require their own tools and input data.

## Example

```powershell
cleanroomx-ai-review "C:\\path\\to\\project.json" --analysis-id room-airflow --analysis-id pressure-study --question "What do these analyses demonstrate and what evidence is missing?" --model YOUR_INSTALLED_MODEL
```

Replace the example analysis IDs with those actually present in your project.
Use `--format json` to see the complete audit batch and the local model's
separately marked answer. `--port` and `--timeout` configure the loopback
transport. This is not an external API client and does not send data to a
cloud provider.

## Evidence-gating behavior

- Every analysis reply must originate from the canonical project analysis
  wrapper, with the current task id and chat-session id.
- Every selected analysis must have completed without an agent exception.
- Source SHA-256 and project name must agree across all analyses; stale or
  mixed-project results fail closed, as do duplicate analysis ids.
- The reviewer refuses absent, malformed or oversized evidence **before**
  contacting the model. This is structural validation of the agent's
  metadata, not independent scientific verification of the numerical result.
- The model sees a task-bound JSON packet with the analysis ids, source
  revision and raw canonical run outputs. That packet is hashed for
  accidental-integrity checking; the hash is **not an authenticity signature**.
- The response is labeled `AI ADVISORY (NOT ENGINEERING VERIFICATION)`,
  never automatically applied, and the immutable specialist results remain
  separate in the multi-agent batch record.
- Failures return nonzero CLI status. If no Ollama service is available,
  no AI answer is substituted.
- The model may make mistakes even with this prompt and evidence. Engineers
  must examine the canonical results, source files, mesh, residuals, solver
  logs, and actual qualification measurements before acceptance.

## Security and limitations

- The network transport is limited to `http://127.0.0.1:<port>/api/chat`
  and explicitly ignores process HTTP proxy settings.
- The client sends the question and selected analysis results to the
  **locally running** Ollama service. Avoid including secrets in either.
- The assistant cannot run commands, edit geometry, approve ISO 14644
  compliance or change numerical criteria.
- Results from design-only or non-converged analyses cannot establish
  verified cleanroom performance. The prompt instructs the model not to
  invent results, but the app does not claim formal safety guarantees
  against model hallucinations or a compromised local model service.
- Full interactive desktop docking, retrieval from solver artifacts,
  offline automated cross-checks, and model-specific evaluation are future
  work. This feature provides a constrained integration boundary and
  a directly runnable CLI, not a finished graphical copilot.

## Tests

```bash
python -m pytest -q tests/test_ai_assistant.py
```

Tests mock the local model response. They do not require a running Ollama
server, and they do not certify any CFD scenario.
