from __future__ import annotations

from collections import Counter
from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from .gui_theme import canonical_status, status_tokens, theme_palette


_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _items(value: Any) -> list:
    return value if isinstance(value, list) else []


def _diagnostic_domain(issue: dict[str, Any]) -> str:
    category = str(issue.get("category") or "").strip().casefold()
    rule = str(issue.get("rule") or "").strip().casefold()
    text = f"{category} {rule}"
    for token, label in (
        ("ifc", "BIM / IFC"),
        ("spatial", "Geometry"),
        ("geometry", "Geometry"),
        ("pressure", "Pressure"),
        ("air", "Airflow / HVAC"),
        ("hvac", "Airflow / HVAC"),
        ("evidence", "Evidence"),
        ("proof", "Evidence"),
        ("verify", "Verification"),
        ("requirement", "Requirements"),
        ("analysis", "Analysis"),
    ):
        if token in text:
            return label
    return "Project"


def engineering_dashboard_snapshot(
    project: Any,
    diagnostics: dict[str, Any] | None,
    *,
    proofgraph_count: int = 0,
    verification_state: str = "unknown",
) -> dict[str, Any]:
    """Build a presentation-only project health snapshot from canonical state."""
    metadata = getattr(project, "metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    spatial = metadata.get("spatial_layout")
    spatial = spatial if isinstance(spatial, dict) else {}
    rooms = _items(spatial.get("rooms"))
    devices = _items(spatial.get("devices"))
    analyses = list(getattr(project, "analyses", ()) or ())

    diagnostic_payload = diagnostics if isinstance(diagnostics, dict) else {}
    issues = [
        item
        for item in _items(diagnostic_payload.get("issues"))
        if isinstance(item, dict)
    ]
    summary = diagnostic_payload.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    errors = int(summary.get("error_count", 0) or 0)
    warnings = int(summary.get("warning_count", 0) or 0)
    info = int(summary.get("info_count", 0) or 0)

    if diagnostics is None:
        health_label, health_status = "NOT EVALUATED", "unknown"
    elif errors:
        health_label, health_status = "BLOCKED", "fail"
    elif warnings:
        health_label, health_status = "ATTENTION", "warning"
    else:
        health_label, health_status = "READY", "pass"

    counts = Counter(_diagnostic_domain(issue) for issue in issues)
    domains = []
    for domain in (
        "Geometry",
        "BIM / IFC",
        "Airflow / HVAC",
        "Pressure",
        "Requirements",
        "Verification",
        "Evidence",
        "Analysis",
        "Project",
    ):
        count = counts.get(domain, 0)
        domains.append(
            {
                "domain": domain,
                "issue_count": count,
                "status": "attention" if count else "clear",
            }
        )

    sorted_issues = sorted(
        issues,
        key=lambda item: (
            _SEVERITY_ORDER.get(
                str(item.get("severity") or "info").strip().lower(),
                9,
            ),
            int(item.get("sequence", 0) or 0),
        ),
    )
    critical = []
    for issue in sorted_issues[:8]:
        element = issue.get("element")
        element = element if isinstance(element, dict) else {}
        critical.append(
            {
                "severity": str(issue.get("severity") or "info").upper(),
                "code": str(issue.get("rule") or ""),
                "message": str(issue.get("message") or ""),
                "object": str(
                    element.get("name")
                    or element.get("id")
                    or element.get("type")
                    or "project"
                ),
                "domain": _diagnostic_domain(issue),
            }
        )

    return {
        "project_name": str(getattr(project, "name", "") or "Untitled project"),
        "health_label": health_label,
        "health_status": health_status,
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "issue_count": len(issues),
        "room_count": len(rooms),
        "device_count": len(devices),
        "analysis_count": len(analyses),
        "proofgraph_count": max(0, int(proofgraph_count)),
        "verification_state": canonical_status(verification_state),
        "domains": domains,
        "critical_issues": critical,
        "analyses": [
            {
                "name": str(getattr(item, "name", "") or "Analysis"),
                "kind": str(getattr(item, "kind", "") or "unknown"),
            }
            for item in analyses[:12]
        ],
    }


class EngineeringDashboard(ttk.Frame):
    """Dense read-only dashboard over current canonical engineering state."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_open_design: Callable[[], None],
        on_open_problems: Callable[[], None],
        on_verify: Callable[[], None],
    ) -> None:
        super().__init__(master, padding=(12, 10))
        self._on_open_design = on_open_design
        self._on_open_problems = on_open_problems
        self._on_verify = on_verify
        self._snapshot: dict[str, Any] = {}
        self._theme_name = "dark"

        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 8))
        title_host = ttk.Frame(header)
        title_host.pack(side="left", fill="x", expand=True)
        ttk.Label(
            title_host,
            text="ENGINEERING DASHBOARD",
            style="CX.Section.TLabel",
        ).pack(anchor="w")
        self.project_var = tk.StringVar(value="Untitled project")
        ttk.Label(
            title_host,
            textvariable=self.project_var,
            style="CX.ViewTitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        self.health_badge = ttk.Label(
            header,
            text="NOT EVALUATED",
            style="CX.Status.unknown.TLabel",
        )
        self.health_badge.pack(side="right", padx=(8, 0))
        ttk.Label(
            header,
            text="PROJECT HEALTH",
            style="CX.Muted.TLabel",
        ).pack(side="right")

        cards = ttk.Frame(self)
        cards.pack(fill="x", pady=(0, 8))
        self._card_vars: dict[str, tk.StringVar] = {}
        for index, (key, title) in enumerate(
            (
                ("rooms", "ROOMS"),
                ("analyses", "ANALYSES"),
                ("issues", "OPEN ISSUES"),
                ("proofgraph", "PROOFGRAPH"),
            )
        ):
            card = ttk.Frame(cards, style="CX.Card.TFrame")
            card.grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 4, 0 if index == 3 else 4),
            )
            cards.columnconfigure(index, weight=1)
            ttk.Label(card, text=title, style="CX.CardTitle.TLabel").pack(anchor="w")
            value = tk.StringVar(value="0")
            self._card_vars[key] = value
            ttk.Label(card, textvariable=value, style="CX.CardValue.TLabel").pack(
                anchor="w", pady=(3, 0)
            )

        actions = ttk.Frame(self, style="CX.Toolbar.TFrame")
        actions.pack(fill="x", pady=(0, 8))
        ttk.Label(actions, text="QUICK ACTIONS", style="CX.Section.TLabel").pack(
            side="left", padx=(2, 8)
        )
        ttk.Button(
            actions,
            text="Open Design",
            style="CX.Compact.TButton",
            command=self._on_open_design,
        ).pack(side="left", padx=2)
        ttk.Button(
            actions,
            text="Review Problems",
            style="CX.Compact.TButton",
            command=self._on_open_problems,
        ).pack(side="left", padx=2)
        ttk.Button(
            actions,
            text="Verify Project",
            style="CX.Primary.TButton",
            command=self._on_verify,
        ).pack(side="left", padx=2)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)

        health_host = ttk.Frame(body, padding=(0, 0, 5, 0))
        issue_host = ttk.Frame(body, padding=(5, 0, 0, 0))
        body.add(health_host, weight=2)
        body.add(issue_host, weight=3)

        ttk.Label(
            health_host,
            text="ENGINEERING DOMAIN STATUS",
            style="CX.Section.TLabel",
        ).pack(anchor="w", pady=(0, 5))
        self.domain_tree = ttk.Treeview(
            health_host,
            columns=("status", "issues"),
            show="tree headings",
            selectmode="browse",
            height=10,
        )
        self.domain_tree.heading("#0", text="Domain")
        self.domain_tree.heading("status", text="State")
        self.domain_tree.heading("issues", text="Issues")
        self.domain_tree.column("#0", width=190, minwidth=130)
        self.domain_tree.column("status", width=100, minwidth=80, stretch=False)
        self.domain_tree.column("issues", width=70, minwidth=60, stretch=False, anchor="e")
        self.domain_tree.pack(fill="both", expand=True)

        ttk.Label(
            issue_host,
            text="CRITICAL ENGINEERING ISSUES",
            style="CX.Section.TLabel",
        ).pack(anchor="w", pady=(0, 5))
        self.issue_tree = ttk.Treeview(
            issue_host,
            columns=("severity", "code", "object", "domain", "message"),
            show="headings",
            selectmode="browse",
            height=10,
        )
        for key, label in (
            ("severity", "Severity"),
            ("code", "Code"),
            ("object", "Object"),
            ("domain", "Domain"),
            ("message", "Description"),
        ):
            self.issue_tree.heading(key, text=label)
        self.issue_tree.column("severity", width=86, stretch=False)
        self.issue_tree.column("code", width=160, minwidth=120, stretch=False)
        self.issue_tree.column("object", width=130, minwidth=100)
        self.issue_tree.column("domain", width=120, minwidth=95, stretch=False)
        self.issue_tree.column("message", width=380, minwidth=220)
        self.issue_tree.pack(fill="both", expand=True)
        self.issue_tree.bind("<Double-1>", lambda _event: self._on_open_problems())
        self.issue_tree.bind("<Return>", lambda _event: self._on_open_problems())

        footer = ttk.Frame(self)
        footer.pack(fill="x", pady=(8, 0))
        self.summary_var = tk.StringVar(value="Diagnostics have not been evaluated.")
        ttk.Label(
            footer,
            textvariable=self.summary_var,
            style="CX.Muted.TLabel",
        ).pack(side="left", fill="x", expand=True)


    def apply_theme(self, value: str) -> None:
        self._theme_name = str(value or "dark")
        palette = theme_palette(self._theme_name)
        for tag, semantic in (
            ("error", "fail"),
            ("warning", "warning"),
            ("info", "running"),
            ("pass", "pass"),
        ):
            tokens = status_tokens(semantic, self._theme_name)
            self.issue_tree.tag_configure(tag, foreground=tokens["foreground"])
            self.domain_tree.tag_configure(tag, foreground=tokens["foreground"])
        self.issue_tree.tag_configure("odd", background=palette["tree"])
        self.issue_tree.tag_configure("even", background=palette["surface"])
        self.domain_tree.tag_configure("odd", background=palette["tree"])
        self.domain_tree.tag_configure("even", background=palette["surface"])

    def refresh(self, snapshot: dict[str, Any]) -> None:
        self._snapshot = dict(snapshot)
        self.project_var.set(str(snapshot.get("project_name") or "Untitled project"))
        health = canonical_status(snapshot.get("health_status"))
        self.health_badge.configure(
            text=str(snapshot.get("health_label") or "NOT EVALUATED"),
            style=f"CX.Status.{health}.TLabel",
        )
        self._card_vars["rooms"].set(str(snapshot.get("room_count", 0)))
        self._card_vars["analyses"].set(str(snapshot.get("analysis_count", 0)))
        self._card_vars["issues"].set(str(snapshot.get("issue_count", 0)))
        self._card_vars["proofgraph"].set(str(snapshot.get("proofgraph_count", 0)))

        for item in self.domain_tree.get_children():
            self.domain_tree.delete(item)
        for index, domain in enumerate(snapshot.get("domains", ())):
            count = int(domain.get("issue_count", 0) or 0)
            self.domain_tree.insert(
                "",
                "end",
                iid=f"domain-{index}",
                text=str(domain.get("domain") or "Project"),
                values=("ATTENTION" if count else "CLEAR", count),
                tags=(
                    "warning" if count else "pass",
                    "even" if index % 2 == 0 else "odd",
                ),
            )

        for item in self.issue_tree.get_children():
            self.issue_tree.delete(item)
        critical = list(snapshot.get("critical_issues", ()) or ())
        for index, issue in enumerate(critical):
            severity = str(issue.get("severity") or "INFO").upper()
            self.issue_tree.insert(
                "",
                "end",
                iid=f"issue-{index}",
                values=(
                    severity,
                    issue.get("code", ""),
                    issue.get("object", ""),
                    issue.get("domain", ""),
                    issue.get("message", ""),
                ),
                tags=(
                    severity.lower(),
                    "even" if index % 2 == 0 else "odd",
                ),
            )

        errors = int(snapshot.get("errors", 0) or 0)
        warnings = int(snapshot.get("warnings", 0) or 0)
        info = int(snapshot.get("info", 0) or 0)
        if snapshot.get("health_status") == "unknown":
            text = "Diagnostics have not been evaluated."
        elif not critical:
            text = "No current project diagnostics require attention."
        else:
            text = f"{errors} error(s) · {warnings} warning(s) · {info} informational issue(s)"
        self.summary_var.set(text)
