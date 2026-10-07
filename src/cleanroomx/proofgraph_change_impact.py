from __future__ import annotations

from collections import deque
import hashlib
import json
from typing import Any, Iterable

from .proofgraph_models import ProofGraph


PROOFGRAPH_CHANGE_IMPACT_SCHEMA = "cleanroomx.proofgraph-change-impact"
PROOFGRAPH_CHANGE_IMPACT_SCHEMA_VERSION = 1


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _items_by_id(items: Iterable[Any]) -> dict[str, dict[str, Any]]:
    return {item.id: item.to_dict() for item in items}


def _collection_diff(
    baseline: dict[str, dict[str, Any]],
    candidate: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    baseline_ids = set(baseline)
    candidate_ids = set(candidate)
    added = sorted(candidate_ids - baseline_ids)
    removed = sorted(baseline_ids - candidate_ids)
    changed = sorted(
        item_id
        for item_id in baseline_ids & candidate_ids
        if baseline[item_id] != candidate[item_id]
    )
    return {
        "added_ids": added,
        "removed_ids": removed,
        "changed_ids": changed,
        "changed_records": [
            {
                "id": item_id,
                "before_sha256": _canonical_sha256(baseline[item_id]),
                "after_sha256": _canonical_sha256(candidate[item_id]),
            }
            for item_id in changed
        ],
    }


def _changed_ids(diff: dict[str, Any]) -> set[str]:
    return {
        *diff["added_ids"],
        *diff["removed_ids"],
        *diff["changed_ids"],
    }


def _candidate_unchanged(
    item_id: str,
    baseline: dict[str, dict[str, Any]],
    candidate: dict[str, dict[str, Any]],
) -> bool:
    return (
        item_id in baseline
        and item_id in candidate
        and baseline[item_id] == candidate[item_id]
    )


def compare_proofgraphs(
    baseline: ProofGraph,
    candidate: ProofGraph,
) -> dict[str, Any]:
    """Compare two revisions of the same logical ProofGraph.

    The report separates direct graph changes from downstream impact. Candidate
    evidence/findings/verdicts are marked *potentially stale* only when their own
    serialized record is unchanged while an upstream source, evidence item,
    requirement, or supporting check changed. This is a conservative review
    signal, not proof that recomputation did or did not occur.
    """
    if not isinstance(baseline, ProofGraph) or not isinstance(candidate, ProofGraph):
        raise TypeError("baseline and candidate must both be ProofGraph values")
    if baseline.id != candidate.id:
        raise ValueError("proofgraph comparison requires matching graph ids")
    if baseline.requirement_set.id != candidate.requirement_set.id:
        raise ValueError(
            "proofgraph comparison requires matching requirement-set ids"
        )

    baseline_document = baseline.to_dict()
    candidate_document = candidate.to_dict()

    baseline_requirement_set = baseline.requirement_set.to_dict()
    candidate_requirement_set = candidate.requirement_set.to_dict()
    baseline_requirements = {
        item["id"]: item for item in baseline_requirement_set["requirements"]
    }
    candidate_requirements = {
        item["id"]: item for item in candidate_requirement_set["requirements"]
    }
    baseline_set_header = {
        key: value
        for key, value in baseline_requirement_set.items()
        if key != "requirements"
    }
    candidate_set_header = {
        key: value
        for key, value in candidate_requirement_set.items()
        if key != "requirements"
    }

    baseline_sources = _items_by_id(baseline.evidence_sources)
    candidate_sources = _items_by_id(candidate.evidence_sources)
    baseline_evidence = _items_by_id(baseline.evidence)
    candidate_evidence = _items_by_id(candidate.evidence)
    baseline_checks = _items_by_id(baseline.checks)
    candidate_checks = _items_by_id(candidate.checks)
    baseline_findings = _items_by_id(baseline.findings)
    candidate_findings = _items_by_id(candidate.findings)
    baseline_verdicts = _items_by_id(baseline.verdicts)
    candidate_verdicts = _items_by_id(candidate.verdicts)
    baseline_actions = _items_by_id(baseline.corrective_actions)
    candidate_actions = _items_by_id(candidate.corrective_actions)
    baseline_runs = _items_by_id(baseline.verification_runs)
    candidate_runs = _items_by_id(candidate.verification_runs)

    changes = {
        "requirements": _collection_diff(
            baseline_requirements, candidate_requirements
        ),
        "evidence_sources": _collection_diff(
            baseline_sources, candidate_sources
        ),
        "evidence": _collection_diff(baseline_evidence, candidate_evidence),
        "checks": _collection_diff(baseline_checks, candidate_checks),
        "findings": _collection_diff(baseline_findings, candidate_findings),
        "verdicts": _collection_diff(baseline_verdicts, candidate_verdicts),
        "corrective_actions": _collection_diff(
            baseline_actions, candidate_actions
        ),
        "verification_runs": _collection_diff(
            baseline_runs, candidate_runs
        ),
    }

    requirement_set_changed = baseline_set_header != candidate_set_header
    changed_requirement_ids = _changed_ids(changes["requirements"])
    if requirement_set_changed:
        changed_requirement_ids.update(baseline_requirements)
        changed_requirement_ids.update(candidate_requirements)

    changed_source_ids = _changed_ids(changes["evidence_sources"])
    directly_changed_evidence_ids = _changed_ids(changes["evidence"])

    stale_candidate_evidence_ids: set[str] = set()
    for evidence in candidate.evidence:
        source_dependency_ids = {evidence.source_id}
        source_dependency_ids.update(
            provenance.source_id for provenance in evidence.provenance
        )
        if (
            source_dependency_ids & changed_source_ids
            and _candidate_unchanged(
                evidence.id, baseline_evidence, candidate_evidence
            )
        ):
            stale_candidate_evidence_ids.add(evidence.id)

    evidence_impact_ids = set(directly_changed_evidence_ids)
    evidence_impact_ids.update(stale_candidate_evidence_ids)

    # Index downstream dependencies once; visiting each affected record once
    # avoids repeated full scans for reverse-ordered or deep evidence chains.
    downstream: dict[str, list[str]] = {}
    for evidence in candidate.evidence:
        if evidence.id in evidence_impact_ids or not _candidate_unchanged(
            evidence.id, baseline_evidence, candidate_evidence
        ):
            continue
        upstream_ids = {
            upstream_id
            for provenance in evidence.provenance
            for upstream_id in provenance.upstream_evidence_ids
        }
        for upstream_id in upstream_ids:
            downstream.setdefault(upstream_id, []).append(evidence.id)

    pending = deque(sorted(evidence_impact_ids))
    while pending:
        for evidence_id in downstream.get(pending.popleft(), ()):
            if evidence_id in evidence_impact_ids:
                continue
            stale_candidate_evidence_ids.add(evidence_id)
            evidence_impact_ids.add(evidence_id)
            pending.append(evidence_id)

    directly_changed_check_ids = _changed_ids(changes["checks"])
    impacted_check_ids = set(directly_changed_check_ids)
    for graph in (baseline, candidate):
        for check in graph.checks:
            if (
                check.requirement_id in changed_requirement_ids
                or set(check.evidence_ids) & evidence_impact_ids
            ):
                impacted_check_ids.add(check.id)

    directly_changed_finding_ids = _changed_ids(changes["findings"])
    impacted_finding_ids = set(directly_changed_finding_ids)
    for graph in (baseline, candidate):
        for finding in graph.findings:
            if (
                finding.requirement_id in changed_requirement_ids
                or finding.check_id in impacted_check_ids
                or set(finding.evidence_ids) & evidence_impact_ids
            ):
                impacted_finding_ids.add(finding.id)

    stale_candidate_finding_ids = {
        finding.id
        for finding in candidate.findings
        if finding.id in impacted_finding_ids
        and finding.id not in directly_changed_finding_ids
        and _candidate_unchanged(
            finding.id, baseline_findings, candidate_findings
        )
    }

    directly_changed_verdict_ids = _changed_ids(changes["verdicts"])
    impacted_verdict_ids = set(directly_changed_verdict_ids)
    for graph in (baseline, candidate):
        for verdict in graph.verdicts:
            if (
                verdict.requirement_id in changed_requirement_ids
                or set(verdict.finding_ids) & impacted_finding_ids
            ):
                impacted_verdict_ids.add(verdict.id)

    stale_candidate_verdict_ids = {
        verdict.id
        for verdict in candidate.verdicts
        if verdict.id in impacted_verdict_ids
        and verdict.id not in directly_changed_verdict_ids
        and _candidate_unchanged(
            verdict.id, baseline_verdicts, candidate_verdicts
        )
    }

    directly_changed_action_ids = _changed_ids(changes["corrective_actions"])
    impacted_action_ids = set(directly_changed_action_ids)
    for graph in (baseline, candidate):
        for action in graph.corrective_actions:
            if (
                action.requirement_id in changed_requirement_ids
                or set(action.evidence_ids) & evidence_impact_ids
            ):
                impacted_action_ids.add(action.id)

    stale_candidate_action_ids = {
        action.id
        for action in candidate.corrective_actions
        if action.id in impacted_action_ids
        and action.id not in directly_changed_action_ids
        and _candidate_unchanged(
            action.id, baseline_actions, candidate_actions
        )
    }

    directly_changed_run_ids = _changed_ids(changes["verification_runs"])
    impacted_run_ids = set(directly_changed_run_ids)
    for graph in (baseline, candidate):
        for run in graph.verification_runs:
            if (
                set(run.check_ids) & impacted_check_ids
                or set(run.verdict_ids) & impacted_verdict_ids
            ):
                impacted_run_ids.add(run.id)

    stale_candidate_run_ids = {
        run.id
        for run in candidate.verification_runs
        if run.id in impacted_run_ids
        and run.id not in directly_changed_run_ids
        and _candidate_unchanged(run.id, baseline_runs, candidate_runs)
    }

    impacted_requirement_ids = set(changed_requirement_ids)
    for graph in (baseline, candidate):
        for check in graph.checks:
            if check.id in impacted_check_ids:
                impacted_requirement_ids.add(check.requirement_id)
        for finding in graph.findings:
            if finding.id in impacted_finding_ids:
                impacted_requirement_ids.add(finding.requirement_id)
        for verdict in graph.verdicts:
            if verdict.id in impacted_verdict_ids:
                impacted_requirement_ids.add(verdict.requirement_id)
        for action in graph.corrective_actions:
            if action.id in impacted_action_ids:
                impacted_requirement_ids.add(action.requirement_id)

    body = {
        "schema": PROOFGRAPH_CHANGE_IMPACT_SCHEMA,
        "schema_version": PROOFGRAPH_CHANGE_IMPACT_SCHEMA_VERSION,
        "graph_id": baseline.id,
        "requirement_set_id": baseline.requirement_set.id,
        "baseline_graph_sha256": baseline_document["graph_sha256"],
        "candidate_graph_sha256": candidate_document["graph_sha256"],
        "changed": baseline_document["graph_sha256"]
        != candidate_document["graph_sha256"],
        "requirement_set_metadata": {
            "changed": requirement_set_changed,
            "before_sha256": _canonical_sha256(baseline_set_header),
            "after_sha256": _canonical_sha256(candidate_set_header),
        },
        "changes": changes,
        "impact": {
            "impacted_requirement_ids": sorted(impacted_requirement_ids),
            "impacted_evidence_ids": sorted(evidence_impact_ids),
            "impacted_check_ids": sorted(impacted_check_ids),
            "impacted_finding_ids": sorted(impacted_finding_ids),
            "impacted_verdict_ids": sorted(impacted_verdict_ids),
            "impacted_corrective_action_ids": sorted(impacted_action_ids),
            "impacted_verification_run_ids": sorted(impacted_run_ids),
        },
        "potentially_stale_candidate": {
            "evidence_ids": sorted(stale_candidate_evidence_ids),
            "finding_ids": sorted(stale_candidate_finding_ids),
            "verdict_ids": sorted(stale_candidate_verdict_ids),
            "corrective_action_ids": sorted(stale_candidate_action_ids),
            "verification_run_ids": sorted(stale_candidate_run_ids),
        },
    }
    return {**body, "impact_sha256": _canonical_sha256(body)}
