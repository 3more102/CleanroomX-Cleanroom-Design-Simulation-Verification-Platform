from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk


def _count(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0


class EngineeringDashboard(ttk.Frame):
    """Project-health dashboard built only from canonical application outputs."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        navigate_issue: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(master, padding=(10, 8))
        self._navigate_issue = navigate_issue
        self._issues_by_iid: dict[str, dict[str, Any]] = {}

        self.readiness_var = tk.StringVar(value="0%")
        self.readiness_detail_var = tk.StringVar(
            value="Open or configure a project to evaluate current engineering readiness."
        )
        self.geometry_var = tk.StringVar(value="0 rooms")
        self.diagnostics_var = tk.StringVar(value="NOT CHECKED")
        self.verification_var = tk.StringVar(value="0 / 0 current")
        self.evidence_var = tk.StringVar(value="0 retained")
        self.analyses_var = tk.StringVar(value="0 configured")
        self.activity_var = tk.StringVar(value="No persisted verification activity.")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(
            header,
            text="ENGINEERING DASHBOARD",
            style="CX.ViewTitle.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            text="Canonical project state · diagnostics · verification · evidence",
            style="CX.Section.TLabel",
        ).pack(side="right")

        readiness = ttk.Frame(self, style="CX.Card.TFrame", padding=(12, 10))
        readiness.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        readiness.columnconfigure(1, weight=1)
        ttk.Label(
            readiness,
            text="PROJECT READINESS",
            style="CX.CardTitle.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            readiness,
            textvariable=self.readiness_var,
            style="CX.CardValue.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ttk.Label(
            readiness,
            textvariable=self.readiness_detail_var,
            style="CX.CardTitle.TLabel",
            wraplength=900,
            justify="left",
        ).grid(row=0, column=1, rowspan=2, sticky="w", padx=(18, 0))

        cards = ttk.Frame(self)
        cards.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        for column in range(5):
            cards.columnconfigure(column, weight=1)

        card_specs = (
            ("GEOMETRY", self.geometry_var, "Geometry"),
            ("DIAGNOSTICS", self.diagnostics_var, "Safety"),
            ("VERIFICATION", self.verification_var, "Verification"),
            ("EVIDENCE", self.evidence_var, "Evidence"),
            ("ANALYSES", self.analyses_var, "Simulation"),
        )
        for column, (title, variable, domain) in enumerate(card_specs):
            card = ttk.Frame(cards, style="CX.Card.TFrame", padding=(9, 7))
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 3, 0 if column == 4 else 3),
            )
            ttk.Label(
                card,
                text=title,
                style=f"CX.Domain.{domain}.TLabel",
            ).pack(anchor="w")
            ttk.Label(
                card,
                textvariable=variable,
                style="CX.CardValue.TLabel",
            ).pack(anchor="w", pady=(5, 0))

        lower = ttk.Panedwindow(self, orient="horizontal")
        lower.grid(row=3, column=0, sticky="nsew")

        issues_host = ttk.Frame(lower, padding=(0, 0, 5, 0))
        activity_host = ttk.Frame(lower, padding=(5, 0, 0, 0))
        lower.add(issues_host, weight=3)
        lower.add(activity_host, weight=2)

        ttk.Label(
            issues_host,
            text="CRITICAL ENGINEERING ISSUES",
            style="CX.Section.TLabel",
        ).pack(anchor="w", pady=(0, 5))
        self.issues_tree = ttk.Treeview(
            issues_host,
            columns=("severity", "code", "object", "message"),
            show="headings",
            selectmode="browse",
            height=10,
        )
        for column, title, width, stretch in (
            ("severity", "Severity", 82, False),
            ("code", "Code", 175, False),
            ("object", "Object", 150, False),
            ("message", "Description", 430, True),
        ):
            self.issues_tree.heading(column, text=title)
            self.issues_tree.column(
                column,
                width=width,
                minwidth=70,
                stretch=stretch,
            )
        issues_scroll = ttk.Scrollbar(
            issues_host,
            orient="vertical",
            command=self.issues_tree.yview,
        )
        self.issues_tree.configure(yscrollcommand=issues_scroll.set)
        self.issues_tree.pack(side="left", fill="both", expand=True)
        issues_scroll.pack(side="right", fill="y")
        self.issues_tree.bind("<Double-1>", self._navigate_selected)
        self.issues_tree.bind("<Return>", self._navigate_selected)

        ttk.Label(
            activity_host,
            text="RECENT VERIFICATION ACTIVITY",
            style="CX.Section.TLabel",
        ).pack(anchor="w", pady=(0, 5))
        ttk.Label(
            activity_host,
            textvariable=self.activity_var,
            justify="left",
            anchor="nw",
            wraplength=420,
        ).pack(fill="both", expand=True)

    @staticmethod
    def _element_text(issue: dict[str, Any]) -> str:
        element = issue.get("element")
        if not isinstance(element, dict):
            return "project"
        return str(
            element.get("name")
            or element.get("id")
            or element.get("type")
            or "project"
        )

    def refresh(
        self,
        *,
        project: Any,
        diagnostics: dict[str, Any] | None,
        verification_currency: dict[str, Any] | None,
        verification_records: list[dict[str, Any]] | None,
        spatial_metrics: dict[str, Any] | None,
    ) -> None:
        metrics = spatial_metrics if isinstance(spatial_metrics, dict) else {}
        room_count = _count(metrics.get("room_count"))
        floor_area = metrics.get("total_floor_area_m2")
        if isinstance(floor_area, (int, float)):
            self.geometry_var.set(f"{room_count} rooms · {floor_area:.1f} m²")
        else:
            self.geometry_var.set(f"{room_count} rooms")

        analyses = list(getattr(project, "analyses", ()) or ())
        self.analyses_var.set(f"{len(analyses)} configured")

        diagnostic_summary = (
            diagnostics.get("summary", {})
            if isinstance(diagnostics, dict)
            else {}
        )
        errors = _count(diagnostic_summary.get("error_count"))
        warnings = _count(diagnostic_summary.get("warning_count"))
        if diagnostics is None:
            self.diagnostics_var.set("NOT CHECKED")
        elif errors:
            self.diagnostics_var.set(f"{errors} ERROR")
        elif warnings:
            self.diagnostics_var.set(f"{warnings} WARNING")
        else:
            self.diagnostics_var.set("PASS")

        currency_summary = (
            verification_currency.get("summary", {})
            if isinstance(verification_currency, dict)
            else {}
        )
        configured = _count(currency_summary.get("configured_analysis_count"))
        current = _count(currency_summary.get("current_count"))
        stale = _count(currency_summary.get("stale_count"))
        not_verified = _count(currency_summary.get("not_verified_count"))
        unverifiable = _count(
            currency_summary.get("dependency_freshness_unverifiable_count")
        )
        self.verification_var.set(f"{current} / {configured} current")

        records = list(verification_records or ())
        self.evidence_var.set(f"{len(records)} retained")

        gates = {
            "Geometry": room_count > 0,
            "Diagnostics": diagnostics is not None and errors == 0,
            "Verification": (
                configured > 0
                and current == configured
                and stale == 0
                and not_verified == 0
                and unverifiable == 0
            ),
            "Evidence": len(records) > 0,
        }
        passed = sum(1 for state in gates.values() if state)
        readiness = round(100 * passed / len(gates))
        self.readiness_var.set(f"{readiness}%")
        missing = [name for name, state in gates.items() if not state]
        if missing:
            self.readiness_detail_var.set(
                "Current readiness gates incomplete: "
                + ", ".join(missing)
                + ". This is a workspace summary, not a compliance verdict."
            )
        else:
            self.readiness_detail_var.set(
                "Geometry, diagnostics, verification currency, and retained evidence "
                "are all current. This is a workspace summary, not a compliance verdict."
            )

        for iid in self.issues_tree.get_children():
            self.issues_tree.delete(iid)
        self._issues_by_iid.clear()
        issues = diagnostics.get("issues", []) if isinstance(diagnostics, dict) else []
        severity_order = {"error": 0, "warning": 1, "info": 2}
        visible = sorted(
            (item for item in issues if isinstance(item, dict)),
            key=lambda item: (
                severity_order.get(str(item.get("severity", "")).casefold(), 9),
                _count(item.get("sequence")),
            ),
        )[:12]
        for index, issue in enumerate(visible):
            severity = str(issue.get("severity") or "info").upper()
            iid = f"dashboard-issue-{index}"
            self.issues_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    severity,
                    str(issue.get("rule") or ""),
                    self._element_text(issue),
                    str(issue.get("message") or ""),
                ),
                tags=(severity.casefold(),),
            )
            self._issues_by_iid[iid] = issue

        if not visible:
            iid = "dashboard-empty"
            self.issues_tree.insert(
                "",
                "end",
                iid=iid,
                values=("PASS", "—", "project", "No current diagnostic issues."),
                tags=("pass",),
            )

        if not records:
            self.activity_var.set("No persisted verification activity.")
        else:
            lines: list[str] = []
            for record in reversed(records[-8:]):
                verification = record.get("verification", {})
                status = (
                    str(verification.get("status") or "unknown").upper()
                    if isinstance(verification, dict)
                    else "UNKNOWN"
                )
                analysis = (
                    record.get("analysis_name")
                    or record.get("analysis_id")
                    or "analysis"
                )
                completed = str(record.get("completed_at_utc") or "")
                lines.append(f"{status} · {analysis}\n{completed}".rstrip())
            self.activity_var.set("\n\n".join(lines))

    def apply_theme(self, palette: dict[str, str]) -> None:
        self.issues_tree.tag_configure(
            "error",
            foreground=palette["error"],
            background=palette["error_surface"],
        )
        self.issues_tree.tag_configure(
            "warning",
            foreground=palette["warning"],
            background=palette["warning_surface"],
        )
        self.issues_tree.tag_configure("info", foreground=palette["info"])
        self.issues_tree.tag_configure(
            "pass",
            foreground=palette["success"],
            background=palette["success_surface"],
        )

    def _navigate_selected(self, _event=None):
        selection = self.issues_tree.selection()
        if not selection:
            return "break"
        issue = self._issues_by_iid.get(selection[0])
        if issue is not None and self._navigate_issue is not None:
            self._navigate_issue(issue)
        return "break"
