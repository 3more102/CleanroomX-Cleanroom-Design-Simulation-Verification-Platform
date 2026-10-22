# Optional model-backed assistant — 22 October 2026

This is an **additive optional Q&A** feature inside the existing deterministic
saved-project Evidence Review. It is not a new numerical engine or certification
authority. The canonical review remains available without any model, network,
API key or AI dependencies.

## Desktop use

1. Open and **save** a CleanroomX project.
2. Open **Tools → Project Assistant (Evidence Review)...** using the existing
   desktop menu. Use **Review saved project** to inspect rule-backed findings.
3. Select **Optional model Q&A...**. Opening the dialog sends **nothing**.
4. Write one question and click **Ask configured model (opt-in)**.
5. Read the visibly marked *unverified suggestion*. A changed saved-project
   revision or invalid provider reply is rejected; no project modification occurs.

Only an allowlisted diagnostic snapshot is sent: saved project SHA-256, aggregate
error/warning/info counts, and up to 12 canonical finding references, rule IDs,
severities, bounded messages and suggested actions, plus the explicit question.
The sender **does not include** project names, full analysis inputs, raw
geometry, CFD fields, project file paths or engineering logs. Diagnostic
messages and user questions can still contain sensitive text: review them
before opting in, especially when using cloud mode.

No implicit request on startup or window opening; no chat history is automatically
saved. A request is read-only, runs in a worker away from Tk, and cannot
change project data, invoke OpenFOAM or publish a verification artifact.

## Default local provider (Ollama)

Install and start [Ollama](https://ollama.com/) separately, and install a model
under a name you choose. Then:

```bash
ollama pull llama3.2
export CLEANROOMX_AI_PROVIDER=ollama
export CLEANROOMX_AI_MODEL=llama3.2
cleanroomx-gui --demo
```

On Windows PowerShell, set the two variables using `$env:VARIABLE="value"`.
The model endpoint is fixed at `http://127.0.0.1:11434/v1/chat/completions`.
Only the explicit **Ask** action communicates with it. A local model being
installed does not guarantee scientifically accurate responses.

## Optional cloud provider (OpenAI)

Cloud mode is deliberately disabled unless all required environment variables
are present:

```bash
export CLEANROOMX_AI_PROVIDER=openai
export CLEANROOMX_AI_MODEL=<supported-chat-model-id>
export CLEANROOMX_AI_ALLOW_CLOUD=1
# Provide OPENAI_API_KEY securely; do not put it in Git, project JSON or logs.
cleanroomx-gui --demo
```

The destination is fixed to `https://api.openai.com/v1/chat/completions`.
Arbitrary service URLs and HTTP redirects are blocked. A configured proxy is
bypassed for this restricted request. A cloud API key can incur charges.
Cloud opt-in is **not** required for local offline evidence review.

## Integrity and scientific boundaries

- Each query rechecks the source file revision before outbound transmission
  and again before publishing the model reply.
- Incoming model JSON is strictly decoded with bounded bytes and response
  text; malformed/nonfinite/duplicate-key responses are rejected.
- No AI result is accepted as evidence of CFD convergence, cleanroom class,
  physical particle transport, or a 5 Pa closed-door pressure cascade.
- The original model-backed development PR #1364 is not blindly merged.
  Existing Evidence Review and its canonical diagnostics remain authoritative.
- **Engineering release: HOLD.** Measured commissioning evidence, closed-door
  leakage physics, mesh-independence and design-airflow convergence remain open.

## Synthetic tests

```bash
python -m pytest -q tests/test_assistant_model_gateway.py
# With a real graphical display:
xvfb-run -a python -m pytest -q tests/test_assistant_model_ui.py
```

A passing mock transport test proves request construction and fail-closed
behavior only. It does not establish a successful live Ollama/OpenAI session,
cloud reliability, physical engineering validity or Windows workstation support.
