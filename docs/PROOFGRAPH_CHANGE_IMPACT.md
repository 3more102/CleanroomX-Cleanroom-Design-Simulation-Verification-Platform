# ProofGraph Revision Diff and Change Impact

CleanroomX can compare two revisions of the same logical ProofGraph with `compare_proofgraphs(baseline, candidate)`.

The comparison is deterministic and binds both input graph SHA-256 identities. It reports added, removed, and changed requirements, evidence sources, evidence, checks, findings, verdicts, corrective actions, and verification runs.

## Impact propagation

Direct requirement, evidence-source, and evidence changes are propagated through the graph:

- changed requirements impact their checks and downstream findings/verdicts;
- changed or removed evidence impacts checks that consume it;
- unchanged evidence is flagged when its primary source or any provenance source revision changed;
- unchanged derived evidence is flagged when one of its provenance upstream evidence records changed;
- downstream findings, verdicts, corrective actions, and verification runs are identified as impacted.

The report includes a canonical `impact_sha256`.

## Potentially stale candidate records

A candidate record is marked **potentially stale** only when its own serialized record is unchanged but an upstream source/evidence/check dependency changed. This is deliberately conservative. It means the record requires review or recomputation evidence; it does not prove that the engineering result is wrong.

Source-revision changes can therefore invalidate unchanged evidence even when the evidence value happens to be numerically identical. Unchanged corrective actions downstream of changed requirements or evidence are also reported as potentially stale so `--require-no-stale` fails closed on unrevalidated recommendations.

## Command-line workflow

Installed builds expose the same analysis through:

```bash
cleanroomx-proofgraph-diff baseline.proofgraph.json candidate.proofgraph.json
```

Use `--require-identical` when CI must reject any graph revision change, or `--require-no-stale` when a revision may change but unchanged candidate evidence/outcomes must not remain downstream of changed inputs. Either policy exit returns code 2 after emitting the complete JSON report.

`--output` publishes the report through the shared atomic CLI writer and refuses a destination that aliases either ProofGraph input. Both inputs use bounded revision-stable strict JSON ingestion; duplicate keys and non-finite JSON fail closed.

## Comparison boundary

The API compares revisions of the same logical graph and requirement set. Different graph IDs or different requirement-set IDs fail closed instead of being treated as a revision diff.

Change impact is software traceability evidence. It does not replace engineering review, commissioning/TAB, or regulatory approval.
