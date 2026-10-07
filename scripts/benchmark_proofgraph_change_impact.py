from __future__ import annotations

from dataclasses import replace
import json
from time import perf_counter

from cleanroomx.proofgraph import (
    DesignEvidence,
    EvidenceSource,
    ProofGraph,
    ProvenanceRecord,
    Requirement,
    RequirementSet,
    compare_proofgraphs,
)


CASES = (1_000, 5_000)
MAX_COMPARE_SECONDS = 3.0


def chain_pair(count: int) -> tuple[ProofGraph, ProofGraph]:
    source = EvidenceSource(id="source", kind="design", reference="design.json")
    evidence = [
        DesignEvidence(
            id="evidence-0", property_name="chain-value", value=1,
            source_id=source.id,
        )
    ]
    for index in range(1, count):
        evidence.append(
            DesignEvidence(
                id=f"evidence-{index}", property_name="chain-value", value=1,
                source_id=source.id,
                provenance=(
                    ProvenanceRecord(
                        id=f"provenance-{index}", source_id=source.id,
                        origin="derived calculation",
                        upstream_evidence_ids=(f"evidence-{index - 1}",),
                    ),
                ),
            )
        )
    baseline = ProofGraph(
        id="chain-benchmark",
        requirement_set=RequirementSet(
            id="URS", version="1", title="Synthetic benchmark", source="benchmark",
            requirements=(Requirement(id="REQ", title="Chain review", source="benchmark"),),
        ),
        evidence_sources=(source,),
        # Reverse dependency order exercises the adverse valid serialization.
        evidence=tuple(reversed(evidence)),
    )
    candidate = replace(
        baseline,
        evidence=tuple(reversed([replace(evidence[0], value=2), *evidence[1:]])),
    )
    return baseline, candidate


def main() -> int:
    results = []
    for count in CASES:
        baseline, candidate = chain_pair(count)
        start = perf_counter()
        report = compare_proofgraphs(baseline, candidate)
        seconds = perf_counter() - start
        expected_stale = sorted(f"evidence-{index}" for index in range(1, count))
        if report["potentially_stale_candidate"]["evidence_ids"] != expected_stale:
            raise RuntimeError("change impact did not reach every derived evidence record")
        if report["changes"]["evidence"]["changed_ids"] != ["evidence-0"]:
            raise RuntimeError("change impact misclassified the changed root evidence")
        results.append({
            "evidence_count": count,
            "compare_seconds": round(seconds, 6),
            "stale_evidence_count": len(expected_stale),
            "impact_sha256": report["impact_sha256"],
        })
        if seconds > MAX_COMPARE_SECONDS:
            print(json.dumps({"proofgraph_change_impact_benchmark": results}, sort_keys=True))
            raise RuntimeError(
                f"{count}-record comparison exceeded the regression budget: "
                f"{seconds:.6f}s > {MAX_COMPARE_SECONDS:.6f}s"
            )
    print(json.dumps({"proofgraph_change_impact_benchmark": results}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
