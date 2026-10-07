# Multi-agent, multi-chat foundation

CleanroomX now has a provider-agnostic orchestration core for running several specialist agents across independent chat sessions without mixing conversation state or engineering evidence.

This is an orchestration foundation. It does **not** embed an OpenAI, local-model, or other network client, and it does not change any cleanroom solver equation, numerical tolerance, project schema, compliance rule, or engineering acceptance criterion.

## Goals

The module `cleanroomx.multi_agent` provides:

- multiple independent chat sessions in one process;
- deterministic, thread-safe message ordering;
- optimistic revision checks that reject stale writes;
- parallel specialist-agent execution with bounded worker count;
- optional synthesis after specialist results are available;
- per-agent failure containment;
- strict-JSON metadata/results;
- atomic workspace persistence through the existing CleanroomX persistence boundary;
- deterministic transcript ordering in requested-agent order even when workers complete out of order.

## Core types

- `ChatSessionStore` owns isolated session histories.
- `ChatSession` is an immutable snapshot of one chat.
- `ChatMessage` records a 1-based sequence, role, optional agent id, and strict-JSON metadata.
- `AgentSpec` registers a callable specialist.
- `AgentRequest` contains the immutable submitted chat snapshot, prompt, shared input, phase, and optional peer results.
- `AgentReply` is a normalized agent response.
- `AgentExecution` records completed/error state without allowing one failed agent to crash the remaining specialists.
- `MultiAgentCoordinator` executes specialists in parallel and optionally runs a synthesizer.
- `AgentBatchResult` records execution and commit state.

## Session isolation

Every chat has its own id, title, message sequence, metadata, and revision.

A coordinator run first appends the user prompt to exactly one session. All specialist agents receive the same immutable snapshot for that submitted revision. Results are never copied into any other chat.

Different sessions can execute concurrently. The store lock protects only the state transition; agent work happens outside the store lock.

## Same-chat concurrency safety

A long-running agent batch can become stale if another actor writes to the same chat before the batch completes.

CleanroomX therefore uses an optimistic revision boundary:

1. capture the current chat revision;
2. append the submitted user prompt with that expected revision;
3. run specialists against the resulting immutable snapshot;
4. commit the whole result batch only if the chat is still at that exact revision.

If the session changed, the agent work is returned with `commit_state="conflict"` and stale outputs are **not** appended to the transcript.

The guard uses both the persisted revision and a runtime-only session-incarnation identity. This closes the delete/recreate ABA case: deleting a chat and creating a new chat with the same id and matching revision cannot cause an old in-flight batch to attach its output to the replacement chat. Incarnation ids are intentionally not serialized; loading a workspace establishes fresh runtime identities because in-flight work does not survive a process restart.

After specialist execution, the coordinator rechecks the submitted chat before invoking an optional synthesizer. If the chat is already stale, synthesis is skipped and the batch returns a conflict immediately, avoiding an unnecessary or side-effecting follow-up call.

This prevents interleaving old agent answers behind newer user messages and prevents stale output from crossing chat lifetimes.

## Parallel execution and deterministic transcripts

Specialists execute through a bounded `ThreadPoolExecutor`. Completion timing does not control transcript order.

If the caller requests:

```text
requirements, hvac, verification
```

the persisted specialist messages remain in that order even if `verification` finishes first.

An optional synthesizer runs only after all specialist results are available and receives them through `AgentRequest.peer_results`.

## Failure containment

Each handler executes behind an agent boundary.

A handler exception becomes an `AgentExecution(state="error")` with the exception type and message. Other specialists continue, their results remain available, and the transcript records the failed execution explicitly if the result batch can still be committed.

The coordinator does not catch `BaseException`; process-level termination signals remain outside the agent error boundary.

## Deterministic batch receipts

Every returned `AgentBatchResult` is now a versioned strict-JSON document:

```text
cleanroomx.multi-agent-batch / version 1
```

The batch contains a canonical SHA-256 integrity record over the task id, chat id, requested specialist order, normalized specialist results, optional synthesis result, commit state, input revision, output revision, and derived error count. `verify_agent_batch_result()` validates the schema, canonicalization, digest, result ordering, synthesis identity, revision semantics, and derived error count without re-running any agent.

For a successfully committed batch, the coordinator predicts the exact atomic output revision before writing the assistant messages. The same compact `batch_receipt` is embedded in every committed specialist/synthesis transcript message, and the post-commit revision is checked against the receipt-bound revision. If the chat becomes stale before the atomic append, the batch is returned with `commit_state="conflict"` and no stale assistant message or receipt is written to the chat.

The receipt is a deterministic content-integrity mechanism, not a digital signature or identity proof. An actor able to rewrite both content and digest can recompute an unkeyed SHA-256 value; stronger authenticity requires an external trusted signature or append-only anchor.

## Persistence

`ChatSessionStore.save()` writes a versioned strict-JSON workspace with the existing durable atomic writer.

Workspace schema:

```text
cleanroomx.multi-agent-workspace / version 1
```

`ChatSessionStore.load()` uses the existing stable strict-JSON ingestion path. Duplicate session ids, unsupported fields, malformed revisions, invalid message sequences, non-finite JSON, and other invalid structures fail closed.

Multi-agent chat state is intentionally separate from the existing `cleanroomx.project` schema. Engineering project files therefore remain backward compatible.

## Example

```python
from cleanroomx.multi_agent import (
    AgentReply,
    ChatSessionStore,
    MultiAgentCoordinator,
)

store = ChatSessionStore()
store.create_session("facility-review", "Facility review")

coordinator = MultiAgentCoordinator(store, max_workers=4)

coordinator.register_agent(
    "requirements",
    lambda request: AgentReply(
        "Requirements checked.",
        {"message_count": len(request.session.messages)},
    ),
)

coordinator.register_agent(
    "hvac",
    lambda request: "HVAC review complete.",
)

def synthesize(request):
    states = {
        result.agent_id: result.state
        for result in request.peer_results
    }
    return AgentReply("Combined review complete.", {"states": states})

coordinator.register_agent("coordinator", synthesize)

batch = coordinator.run(
    "facility-review",
    "Review this design state.",
    agent_ids=["requirements", "hvac"],
    synthesizer_agent_id="coordinator",
)
```

The callable agents above are intentionally simple. A later adapter can bind them to an LLM, local inference service, deterministic CleanroomX analysis service, or other approved execution backend without changing session isolation semantics.

## Recommended CleanroomX specialist split

For an engineering assistant layer, keep responsibilities explicit rather than using several identical general-purpose agents:

- **Coordinator** — decomposes the request and synthesizes specialist evidence.
- **Requirements agent** — project requirements, explicit criteria, traceability.
- **BIM/spatial agent** — IFC, rooms, geometry, mappings, synchronization.
- **HVAC/network agent** — airflow, ACH, duct, fan, pressure-network workflows.
- **Verification agent** — reruns/checks canonical analyses and freshness evidence.
- **Proof/evidence agent** — ProofGraph, provenance, run-history, dossier evidence.
- **Safety/reviewer agent** — checks conflicts, unsupported assumptions, and incomplete evidence before publication.

The orchestration layer must not allow an agent to silently invent engineering criteria or bypass canonical parsers/runners. Agents that invoke CleanroomX analyses should call the existing application service boundary.

## GUI integration direction

A future desktop slice can add a chat notebook or side panel over this backend:

- one tab per `ChatSession`;
- agent badges on assistant messages;
- visible per-agent running/error state;
- a coordinator summary section;
- conflict banner when `commit_state="conflict"`;
- explicit session save/load;
- no direct solver logic inside Tk callbacks.

The current module deliberately keeps those presentation concerns out of the backend.

## Verification added

Focused tests cover:

- multi-chat isolation;
- revision conflict detection;
- strict workspace save/load round-trip;
- parallel completion with deterministic requested-agent transcript order;
- per-agent failure isolation;
- synthesizer access to specialist results;
- stale result rejection when the same chat changes during execution;
- delete/recreate ABA protection for reused chat ids;
- stale-synthesis short-circuiting before follow-up work;
- simultaneous execution in different chats;
- validation before transcript mutation for duplicate/unknown agents.
