"""Shared Matplotlib renderer and reproducible analysis/figure export bundle."""
from __future__ import annotations

import csv
import copy
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
from decimal import Decimal
import shutil
import tempfile

from .cfd_proofgraph import _hash_regular_file
from .cfd_result_analysis import AnalysisSession, BOUNDARY, canonical_bytes, digest
from .markdown import markdown_text
from .proofgraph_models import (
    ComplianceCheck, ComplianceFinding, ComplianceVerdict, EvidenceSource,
    ProvenanceRecord, Requirement, SimulationEvidence, VerificationRun,
)


def draw_analysis_graph(figure, graph: dict, *, include_provenance: bool = True) -> None:
    """Render exactly graph.points, sharing the renderer between Tk and file exports."""
    figure.clear()
    kind = graph["kind"]
    ax = figure.add_subplot(111, projection="3d" if kind == "cell_3d" else None)
    compact = not include_provenance and figure.get_figheight() < 3
    figure.subplots_adjust(bottom=0.28 if include_provenance else 0.2, top=0.87, left=0.12, right=0.93)
    ax.set_title(graph["title"], fontsize=11)
    if graph["status"] == "not_available":
        text = ax.text2D if kind == "cell_3d" else ax.text
        text(0.5, 0.5, graph["reason"], ha="center", va="center", transform=ax.transAxes, wrap=True)
    elif kind in ("cell_slab", "cell_3d"):
        points = graph["series"][0]["points"]
        stats = graph.get("selections", [{}])[0].get("statistics") or {}
        colors = {"cmap": "viridis", "vmin": stats.get("minimum"), "vmax": stats.get("maximum")}
        if kind == "cell_3d":
            dots = ax.scatter([p["x"] for p in points], [p["y"] for p in points], [p["z"] for p in points],
                              c=[p["value"] for p in points], s=14, **colors)
            ax.set(xlabel="x (m)", ylabel="y (m)", zlabel="z (m)")
            bounds = graph.get("mesh_bounds_m")
            if bounds:
                ax.set(xlim=bounds[:2], ylim=bounds[2:4], zlim=bounds[4:])
                ax.set_box_aspect([bounds[i + 1] - bounds[i] for i in (0, 2, 4)])
            region = graph["filters"].get("region")
            if region:
                bounds = region["bounds_m"]
                for axis in range(3):
                    others = [i for i in range(3) if i != axis]
                    for a in (0, 1):
                        for b in (0, 1):
                            edge = [[bounds[2 * i], bounds[2 * i + 1]] if i == axis
                                    else [bounds[2 * i + (a if i == others[0] else b)]] * 2 for i in range(3)]
                            ax.plot(*edge, color="#087e8b", linewidth=0.8, alpha=0.55)
        else:
            axes = [a for a in "xyz" if a != graph["filters"]["axis"]]
            dots = ax.scatter([p[axes[0]] for p in points], [p[axes[1]] for p in points],
                              c=[p["value"] for p in points], s=22, **colors)
            ax.set(xlabel=axes[0] + " (m)", ylabel=axes[1] + " (m)")
            ax.set_aspect("equal", adjustable="box")
        colorbar = figure.colorbar(dots, ax=ax, label=graph["color_label"], shrink=0.75, pad=0.08)
        ax.set_anchor("C")
        if compact:
            from matplotlib.ticker import MaxNLocator
            ax.tick_params(labelsize=7, pad=1)
            ax.xaxis.set_major_locator(MaxNLocator(3))
            ax.yaxis.set_major_locator(MaxNLocator(3))
            if kind == "cell_3d":
                ax.zaxis.set_major_locator(MaxNLocator(3))
                ax.zaxis.labelpad = 1
            ax.xaxis.labelpad = ax.yaxis.labelpad = 1
            colorbar.ax.tick_params(labelsize=7)
    elif kind in ("comparison", "flow_balance", "air_change_rate"):
        labels, values = [], []
        single_run = len({s["run_id"] for s in graph["series"]}) == 1
        for series in graph["series"]:
            for point in series["points"]:
                short_run = series["run_id"] if len(series["run_id"]) <= 28 else series["run_id"][:25] + "..."
                if kind == "comparison":
                    label = series["case_id"] + ("\n" + short_run if not single_run else "")
                else:
                    label = str(point["x"]) + ("\n" + short_run if len(graph["series"]) > 1 else "")
                labels.append(label)
                values.append(point["y"])
        positions = list(range(len(labels)))
        if kind == "comparison" and len(labels) > 6:
            # A nine-case grid needs room for full configuration/resolution names.
            ax.barh(positions, values, color="#087e8b")
            ax.set_yticks(positions, labels, fontsize=7)
            ax.invert_yaxis()
            ax.axvline(0, color="grey", linewidth=0.6)
            ax.set_xlabel(graph["y_label"])
            ax.set_ylabel("Run / case at selected solver time")
            figure.subplots_adjust(left=0.32)
        else:
            ax.bar(positions, values, color="#087e8b")
            ax.set_xticks(positions, labels, fontsize=8)
            ax.axhline(0, color="grey", linewidth=0.6)
            ax.set_ylabel(graph["y_label"])
            ax.set_xlabel("Run / case at selected solver time" if kind == "comparison" else graph["x_label"])
    else:
        for series in graph["series"]:
            points = series["points"]
            ax.plot([p["x"] for p in points], [p["y"] for p in points],
                    label=series["label"], linewidth=1.2, marker="." if len(points) < 50 else None)
            if kind == "field_history":
                ax.fill_between([p["x"] for p in points], [p["minimum"] for p in points],
                                [p["maximum"] for p in points], alpha=0.12)
        if graph.get("scale") == "symlog":
            ax.set_yscale("symlog", linthresh=1e-12)
        ax.set(xlabel=graph["x_label"], ylabel=graph["y_label"])
        ax.grid(alpha=0.2)
        ax.legend(fontsize=7, loc="best")
    if not include_provenance:
        return  # The Tk explorer shows provenance beside the plot and in its source tab.
    sources = graph["sources"]
    hashes = ", ".join(source["sha256"][:12] for source in sources[:4])
    if len(sources) > 4:
        hashes += f" (+{len(sources)-4} sources; full hashes in graph data)"
    figure.text(0.02, 0.12, "Runs: " + ", ".join(graph["runs"]), fontsize=7, wrap=True)
    regions = "; ".join(sorted({s["region"] for s in graph["series"]}))
    figure.text(0.02, 0.16, "Region: " + (regions or "not available"), fontsize=7, wrap=True)
    figure.text(0.02, 0.085, f"Source SHA-256: {hashes or 'not available'}", fontsize=7, wrap=True)
    figure.text(0.02, 0.045, "Diagnostic solver output analysis | physical validation BLOCKED", fontsize=7)


def _csv_safe(value):
    # Avoid executing a case/array label as a formula in spreadsheet viewers.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def graph_csv(graphs: list[dict]) -> str:
    output = io.StringIO(newline="")
    columns = ["graph", "kind", "status", "run_id", "case_id", "region", "series", "time_name", "x", "y", "z",
               "value", "volume_m3", "minimum", "maximum", "cell_index", "line", "linear_iterations", "units",
               "source_paths", "source_sha256", "log_execution_binding"]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for index, graph in enumerate(graphs, 1):
        for series in graph["series"]:
            for point in series["points"]:
                row = {"graph": index, "kind": graph["kind"], "status": graph["status"],
                       "run_id": series["run_id"], "case_id": series["case_id"], "region": series["region"],
                       "series": series["label"], "units": graph.get("y_label") or graph.get("color_label", ""),
                       "source_paths": " | ".join(s["path"] for s in graph["sources"]),
                       "source_sha256": " | ".join(s["sha256"] for s in graph["sources"]),
                       "log_execution_binding": series.get("log_execution_binding", ""), **point}
                if graph["kind"] in ("field_history", "comparison"):
                    row["x"] = point["time_name"]
                writer.writerow({k: _csv_safe(v) for k, v in row.items() if k in columns})
    return output.getvalue()


def selection_csv(graphs: list[dict]) -> str:
    """All selected-cell statistics, including empty selections, before plot sampling."""
    output = io.StringIO(newline="")
    columns = ["graph", "run_id", "case_id", "time_name", "region", "field", "status", "cell_count",
               "mesh_cell_count", "volume_m3", "mesh_volume_m3", "volume_fraction_of_mesh", "mean",
               "minimum", "maximum", "units", "selection_rule", "vtk_sha256", "cell_indices_sha256"]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for index, graph in enumerate(graphs, 1):
        for selection in graph.get("selections", []):
            stats = selection.get("statistics") or {}
            row = {**selection, **{key: stats.get(key, "") for key in ("mean", "minimum", "maximum", "units")},
                   "graph": index}
            writer.writerow({key: _csv_safe(row.get(key, "")) for key in columns})
    return output.getvalue()


def _residual_csv(sessions: list[AnalysisSession]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=["run_id", "case_id", "time", "field", "initial", "final",
                                                "linear_iterations", "line", "source_path", "source_sha256",
                                                "log_execution_binding"])
    writer.writeheader()
    for session in sessions:
        for diagnosis in session.report["diagnostics"]:
            residuals = diagnosis["residuals"]
            if residuals:
                for sample in residuals["samples"]:
                    row = {"run_id": session.report["simulation_id"], "case_id": diagnosis["case_id"],
                           "source_path": residuals["source"]["path"], "source_sha256": residuals["source"]["sha256"],
                           "log_execution_binding": diagnosis["log_execution_binding"], **sample}
                    writer.writerow({key: _csv_safe(value) for key, value in row.items()})
    return output.getvalue()


def analysis_proofgraph(session: AnalysisSession, graphs: list[dict], artifacts: dict[str, str]) -> dict:
    """Extend the existing result ProofGraph; only artifact traceability may pass."""
    payload = {"report": session.report, "graphs": graphs, "exported_artifact_sha256": artifacts,
               "scientific_validation": "BLOCKED", "interpretation": BOUNDARY}
    sha = digest(payload)
    suffix = sha[:16]
    source_id, evidence_id = "SOURCE-ANALYSIS-" + suffix, "EVIDENCE-ANALYSIS-" + suffix
    requirement_id, check_id = "REQ-ANALYSIS-" + suffix, "CHECK-ANALYSIS-" + suffix
    finding_id, verdict_id = "FIND-ANALYSIS-" + suffix, "VERDICT-ANALYSIS-" + suffix
    base = session.proofgraph
    graph = replace(
        base,
        id=base.id + "-ANALYSIS-" + suffix,
        requirement_set=replace(base.requirement_set, requirements=base.requirement_set.requirements + (
            Requirement(id=requirement_id, title="Derived graph input and export traceability",
                        source="CleanroomX solver-result analysis", criteria={"scope": "artifact_traceability_only"}),)),
        evidence_sources=base.evidence_sources + (EvidenceSource(id=source_id, kind="derived_solver_analysis",
                                                                reference="analysis.json + graphs.json", revision=sha),),
        evidence=base.evidence + (SimulationEvidence(
            id=evidence_id, property_name="derived_solver_analysis_and_graphs", value=payload,
            source_id=source_id, version=sha, subject_ref=session.report["simulation_id"],
            provenance=(ProvenanceRecord(id="PROV-ANALYSIS-" + suffix, source_id=source_id,
                                         origin="verified OpenFOAM result assets",
                                         originating_file="analysis.json",
                                         originating_calculation="volume_weighted_statistics_and_graph_selection",
                                         method="cleanroomx.cfd_result_analysis.v1"),)),),
        checks=base.checks + (ComplianceCheck(id=check_id, requirement_id=requirement_id,
                                             evidence_ids=(evidence_id,)),),
        findings=base.findings + (ComplianceFinding(
            id=finding_id, check_id=check_id, requirement_id=requirement_id, status="pass",
            reason="Derived graph data and exported files carry local SHA-256 links; physical validity is not assessed.",
            evidence_ids=(evidence_id,), evidence_present=True,
            actual={"analysis_sha256": sha, "scientific_validation": "BLOCKED"}),),
        verdicts=base.verdicts + (ComplianceVerdict(id=verdict_id, requirement_id=requirement_id, status="pass",
                                                  finding_ids=(finding_id,), reason="Artifact traceability only"),),
        verification_runs=base.verification_runs + (VerificationRun(
            id="RUN-ANALYSIS-" + suffix, requirement_set_id=base.requirement_set.id,
            check_ids=(check_id,), verdict_ids=(verdict_id,),
            metadata={"analysis_sha256": sha, "execution": "post_processing_only_no_solver_started",
                      "scientific_validation": "BLOCKED"}),),
    )
    return graph.to_dict()


def _report_markdown(sessions: list[AnalysisSession], graphs: list[dict]) -> str:
    lines = ["# CleanroomX solver-result analysis", "", BOUNDARY, ""]
    for session in sessions:
        report = session.report
        lines += ["## " + markdown_text(report["simulation_id"]), "",
                  "Execution metadata: `" + json.dumps(report["cases"], sort_keys=True) + "`", "",
                  "Original OpenFOAM field bytes rehashed: " + str(report["reproducibility"]["native_source_bytes_rehashed"]) + ".", "",
                  "| Case | Solver time | Field | Units | Minimum | Volume-weighted mean | Maximum |",
                  "|---|---|---|---|---:|---:|---:|"]
        for snapshot in report["snapshots"]:
            for name, stats in snapshot["statistics"].items():
                lines.append("| " + " | ".join(markdown_text(v) for v in (
                    snapshot["case_id"], snapshot["time_name"], name, stats["units"],
                    stats["minimum"], stats["mean"], stats["maximum"])) + " |")
        lines += ["", "### Availability and warnings", ""]
        lines += ["- " + markdown_text(item["analysis"] + ": " + item["reason"]) for item in report["availability"]]
        for diagnosis in report["diagnostics"]:
            lines += ["- " + markdown_text(diagnosis["case_id"] + ": " + str(warning)) for warning in diagnosis["warnings"]]
            if diagnosis["mesh"]:
                lines += ["", "Mesh diagnostics: `" + json.dumps(diagnosis["mesh"], sort_keys=True) + "`", ""]
        if "flow_balance" in report:
            lines += ["", "Boundary flux diagnostics: `" + json.dumps(report["flow_balance"], sort_keys=True) + "`", ""]
        if "ventilation" in report:
            lines += ["", "Inlet supply ACH (whole domain): `" + json.dumps(report["ventilation"], sort_keys=True) + "`", ""]
        lines += ["", "Full source paths, SHA-256 values, native field metadata, calculation methods, and execution status are in analysis.json.", ""]
    lines += ["## Figures and data", "", "graphs.csv contains every plotted point. graphs.json records filters, source hashes, methods, and unavailable states. selections.csv contains all selected-cell statistics and mesh-volume coverage, including empty selections. residuals.csv contains all parsed linear solves. cell-data-NN.csv contains all selected cells before display sampling, when a spatial graph is exported.", ""]
    for i, graph in enumerate(graphs, 1):
        lines += [f"### Figure {i}: " + markdown_text(graph["title"]), "", markdown_text(graph["method"]), "",
                  f"![Figure {i}](figure-{i:02d}.png)", ""]
        if graph.get("selections"):
            lines += ["| Case / time | Selected cells | Selected volume (m³) | Mesh volume coverage | Mean | Range |",
                      "| --- | ---: | ---: | ---: | ---: | --- |"]
            for selection in graph["selections"]:
                stats = selection["statistics"]
                mean = f"{stats['mean']:.6g} {stats['units']}" if stats else "unavailable"
                limits = f"{stats['minimum']:.6g} to {stats['maximum']:.6g}" if stats else "unavailable"
                label = markdown_text(selection["run_id"] + " / " + selection["case_id"] + " / " + selection["time_name"])
                lines.append(f"| {label} | {selection['cell_count']} / {selection['mesh_cell_count']} | "
                             f"{selection['volume_m3']:.6g} | {100 * selection['volume_fraction_of_mesh']:.3g}% | "
                             f"{markdown_text(mean)} | {limits} |")
            lines.append("")
    return "\n".join(lines)


def export_analysis_bundle(sessions: list[AnalysisSession], graphs: list[dict], destination: str | Path) -> Path:
    """Publish a new directory atomically. Recheck all graph/report inputs before writing."""
    if not sessions or not graphs:
        raise ValueError("At least one analysis session and graph are required")
    candidate = Path(destination).expanduser()
    if candidate.exists() or candidate.is_symlink():
        raise FileExistsError("Choose a new export directory")
    target = candidate.resolve(strict=False)
    if not target.parent.is_dir():
        raise ValueError("Export parent directory must already exist")
    for session in sessions:
        if any(target == root or target.is_relative_to(root) for root in session.protected_roots):
            raise ValueError("Analysis exports must be outside source case/result directories")
        for source in session.report["sources"]:
            sha, _ = _hash_regular_file(Path(source["path"]), max_bytes=256 * 1024 * 1024)
            if sha != source["sha256"]:
                raise ValueError("Analysis source changed; reload results before exporting: " + Path(source["path"]).name)
    # Graphs are reproducible projections of their sessions, not caller-supplied values.
    from .cfd_result_analysis import build_analysis_graph
    for graph in graphs:
        filters = dict(graph["filters"])
        filters["field_name"] = filters.pop("field")
        graph_sessions = [s for s in sessions if s.report["simulation_id"] in graph["runs"]]
        rebuilt = build_analysis_graph(graph_sessions, kind=graph["kind"], **filters)
        if canonical_bytes(rebuilt) != canonical_bytes(graph):
            raise ValueError("Graph data no longer matches its analysis inputs")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    stage = Path(tempfile.mkdtemp(prefix=".cleanroomx-analysis-", dir=target.parent))
    try:
        def write_json(name: str, value) -> None:
            (stage / name).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")

        write_json("analysis.json", [session.report for session in sessions])
        write_json("graphs.json", graphs)
        (stage / "graphs.csv").write_text(graph_csv(graphs), encoding="utf-8", newline="")
        (stage / "selections.csv").write_text(selection_csv(graphs), encoding="utf-8", newline="")
        (stage / "residuals.csv").write_text(_residual_csv(sessions), encoding="utf-8", newline="")
        (stage / "report.md").write_text(_report_markdown(sessions, graphs), encoding="utf-8")
        for i, graph in enumerate(graphs, 1):
            if graph["kind"] in ("cell_slab", "cell_3d") and graph["series"]:
                from .cfd_result_analysis import spatial_samples
                full_graph = copy.deepcopy(graph)
                filters = graph["filters"]
                session = next(s for s in sessions if s.report["simulation_id"] == graph["series"][0]["run_id"])
                snapshot = next(s for s in session.report["snapshots"] if s["case_id"] == filters["case_id"]
                                and Decimal(s["time_name"]) == Decimal(filters["time_name"]))
                full_graph["series"][0]["points"] = spatial_samples(
                    snapshot, filters["field"], kind=graph["kind"], axis=filters["axis"],
                    position_m=filters["position_m"], thickness_m=filters["thickness_m"], region=filters.get("region"))
                (stage / f"cell-data-{i:02d}.csv").write_text(graph_csv([full_graph]), encoding="utf-8", newline="")
            figure = Figure(figsize=(11, 7), dpi=120)
            FigureCanvasAgg(figure)
            draw_analysis_graph(figure, graph)
            for extension in ("png", "svg"):
                figure.savefig(stage / f"figure-{i:02d}.{extension}")
            figure.clear()
        artifacts = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.iterdir()}
        for i, session in enumerate(sessions, 1):
            write_json(f"proofgraph-{i:02d}.json", analysis_proofgraph(session, graphs, artifacts))
        write_json("manifest.json", {"schema_version": "cleanroomx.cfd-analysis-export.v1",
                    "scientific_validation": "BLOCKED", "execution": "post_processing_only_no_solver_started",
                    "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.iterdir()}})
        # Recheck after rendering, too: an external solver must not change data mid-export.
        for session in sessions:
            for source in session.report["sources"]:
                sha, _ = _hash_regular_file(Path(source["path"]), max_bytes=256 * 1024 * 1024)
                if sha != source["sha256"]:
                    raise ValueError("Analysis source changed during export; reload results")
        if target.exists():
            raise FileExistsError("Export directory appeared while rendering")
        os.rename(stage, target)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return target
