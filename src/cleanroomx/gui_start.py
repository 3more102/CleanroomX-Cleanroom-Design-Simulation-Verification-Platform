from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import ttk

from .gui_theme import status_style_name


class StartCenter(ttk.Frame):
    """Professional zero-state surface; all project actions stay in the app layer."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_new: Callable[[], None],
        on_open: Callable[[], None],
        on_import_ifc: Callable[[], None],
        on_open_demo: Callable[[], None],
        on_open_recent: Callable[[str], None],
        on_forget_recent: Callable[[str], None] | None = None,
        on_workspace: Callable[[str], None] | None = None,
        on_show_problems: Callable[[], None] | None = None,
        on_show_recovery: Callable[[], None] | None = None,
    ):
        super().__init__(master, padding=(24, 18))
        self._on_open_recent = on_open_recent
        self._on_forget_recent = on_forget_recent
        self._on_workspace = on_workspace
        self._on_show_problems = on_show_problems
        self._on_show_recovery = on_show_recovery
        self._recent_paths: dict[str, str] = {}
        self._recent_records: list[dict[str, str]] = []
        self.recent_search_var = tk.StringVar()
        self.recent_count_var = tk.StringVar(value="0 recent projects")
        self.project_name_var = tk.StringVar(value="Untitled Project")
        self.project_path_var = tk.StringVar(value="Not yet saved")
        self.project_state_var = tk.StringVar(value="Ready")
        self.project_counts_var = tk.StringVar(value="0 analyses • 0 rooms • 0 devices")
        self.project_diagnostics_var = tk.StringVar(value="Problems: unavailable")
        self.project_verification_var = tk.StringVar(value="Verification: unavailable")
        self.project_evidence_var = tk.StringVar(value="Evidence: 0 retained records")
        self.project_recovery_var = tk.StringVar(value="Recovery: no saved recovery candidates")

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)

        brand = ttk.Frame(self)
        brand.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(2, 12))
        ttk.Label(brand, text="CleanroomX", style="CX.Brand.TLabel").pack(anchor="w")
        ttk.Label(
            brand,
            text="Engineering Design • Simulation • Verification",
            style="CX.ViewTitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            brand,
            text=(
                "Project-native cleanroom engineering with linked 2D/3D design, "
                "analysis, deterministic verification, IFC semantics, diagnostics, "
                "ProofGraph, and evidence traceability."
            ),
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        actions = ttk.LabelFrame(self, text="Start", padding=18)
        actions.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        self.new_project_button = ttk.Button(
            actions,
            text="New Project",
            style="CX.Primary.TButton",
            command=on_new,
        )
        self.new_project_button.grid(
            row=0, column=0, sticky="ew", padx=5, pady=5
        )
        self.open_project_button = ttk.Button(
            actions,
            text="Open Project",
            style="CX.Primary.TButton",
            command=on_open,
        )
        self.open_project_button.grid(
            row=0, column=1, sticky="ew", padx=5, pady=5
        )
        ttk.Button(
            actions,
            text="Import IFC",
            command=on_import_ifc,
        ).grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        ttk.Button(
            actions,
            text="Open Example Project",
            command=on_open_demo,
        ).grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        health = ttk.LabelFrame(self, text="Active Project", padding=14)
        health.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        health.columnconfigure(0, weight=1)

        headline = ttk.Frame(health)
        headline.grid(row=0, column=0, sticky="ew")
        headline.columnconfigure(0, weight=1)
        ttk.Label(
            headline,
            textvariable=self.project_name_var,
            style="CX.Section.TLabel",
        ).grid(row=0, column=0, sticky="w")
        self.project_state_label = ttk.Label(
            headline,
            textvariable=self.project_state_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.project_state_label.grid(row=0, column=1, sticky="e", padx=(10, 0))

        ttk.Label(
            health,
            textvariable=self.project_path_var,
            style="CX.Muted.TLabel",
            wraplength=470,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(5, 0))
        ttk.Label(
            health,
            textvariable=self.project_counts_var,
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))

        self.project_diagnostics_label = ttk.Label(
            health,
            textvariable=self.project_diagnostics_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.project_diagnostics_label.grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.project_verification_label = ttk.Label(
            health,
            textvariable=self.project_verification_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.project_verification_label.grid(row=4, column=0, sticky="w", pady=(5, 0))
        ttk.Label(
            health,
            textvariable=self.project_evidence_var,
        ).grid(row=5, column=0, sticky="w", pady=(7, 0))
        recovery_row = ttk.Frame(health)
        recovery_row.grid(row=6, column=0, sticky="ew", pady=(4, 0))
        recovery_row.columnconfigure(0, weight=1)
        self.project_recovery_label = ttk.Label(
            recovery_row,
            textvariable=self.project_recovery_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.project_recovery_label.grid(row=0, column=0, sticky="w")
        self.recovery_button = ttk.Button(
            recovery_row,
            text="Recovery…",
            style="CX.Compact.TButton",
            command=self._open_recovery,
            state="normal" if self._on_show_recovery is not None else "disabled",
        )
        self.recovery_button.grid(row=0, column=1, sticky="e", padx=(8, 0))

        workspace_actions = ttk.Frame(health)
        workspace_actions.grid(row=7, column=0, sticky="ew", pady=(10, 0))
        for column in range(3):
            workspace_actions.columnconfigure(column, weight=1)
        self.workspace_buttons: dict[str, ttk.Button] = {}
        for index, (label, profile) in enumerate(
            (
                ("Design", "design"),
                ("Simulation", "simulation"),
                ("Verification", "verification"),
                ("Evidence", "evidence"),
                ("Reporting", "reporting"),
            )
        ):
            button = ttk.Button(
                workspace_actions,
                text=label,
                style="CX.Compact.TButton",
                command=lambda selected=profile: self._open_workspace(selected),
                state="normal" if self._on_workspace is not None else "disabled",
            )
            button.grid(
                row=index // 3,
                column=index % 3,
                sticky="ew",
                padx=2,
                pady=2,
            )
            self.workspace_buttons[profile] = button
        self.problems_button = ttk.Button(
            workspace_actions,
            text="Problems",
            style="CX.Compact.TButton",
            command=self._open_problems,
            state="normal" if self._on_show_problems is not None else "disabled",
        )
        self.problems_button.grid(row=1, column=2, sticky="ew", padx=2, pady=2)

        recent = ttk.LabelFrame(self, text="Recent Projects", padding=12)
        recent.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(10, 0),
        )
        recent.columnconfigure(0, weight=1)
        recent.rowconfigure(1, weight=1)

        filter_row = ttk.Frame(recent)
        filter_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 7))
        ttk.Label(filter_row, text="Search").pack(side="left")
        self.recent_search_entry = ttk.Entry(
            filter_row,
            textvariable=self.recent_search_var,
            width=34,
        )
        self.recent_search_entry.pack(side="left", fill="x", expand=True, padx=(4, 8))
        ttk.Button(
            filter_row,
            text="Clear",
            command=lambda: self.recent_search_var.set(""),
        ).pack(side="left")
        ttk.Label(
            filter_row,
            textvariable=self.recent_count_var,
        ).pack(side="right", padx=(12, 0))

        self.recent_tree = ttk.Treeview(
            recent,
            columns=("path", "status", "modified"),
            show="tree headings",
            height=4,
            selectmode="browse",
        )
        self.recent_tree.heading("#0", text="Project")
        self.recent_tree.heading("path", text="Path")
        self.recent_tree.heading("status", text="Status")
        self.recent_tree.heading("modified", text="Modified")
        self.recent_tree.column("#0", width=190, minwidth=130)
        self.recent_tree.column("path", width=440, minwidth=210)
        self.recent_tree.column("status", width=95, minwidth=80, stretch=False)
        self.recent_tree.column("modified", width=135, minwidth=105, stretch=False)
        scroll = ttk.Scrollbar(recent, orient="vertical", command=self.recent_tree.yview)
        self.recent_tree.configure(yscrollcommand=scroll.set)
        self.recent_tree.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        self.recent_tree.bind("<Double-1>", self._open_selected_recent)
        self.recent_tree.bind("<Return>", self._open_selected_recent)
        self.recent_tree.bind("<Delete>", self._forget_selected_recent)
        self.recent_tree.bind("<Button-3>", self._show_recent_context_menu)

        footer = ttk.Frame(recent)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.recent_hint = ttk.Label(footer, text="No recent projects in this session.")
        self.recent_hint.pack(side="left")
        self.remove_recent_button = ttk.Button(
            footer,
            text="Remove from Recent",
            command=self._forget_selected_recent,
            state="normal" if self._on_forget_recent is not None else "disabled",
        )
        self.remove_recent_button.pack(side="right", padx=(6, 0))
        ttk.Button(
            footer,
            text="Open Selected",
            command=self._open_selected_recent,
        ).pack(side="right")

        examples = ttk.LabelFrame(self, text="Example Projects", padding=12)
        examples.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(10, 0),
        )
        ttk.Label(
            examples,
            text="Bundled CleanroomX Demo",
            style="CX.Section.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            examples,
            text=(
                "Open the packaged demo project to explore the project browser, "
                "2D/3D workspace, analyses, diagnostics, verification, and evidence."
            ),
            wraplength=760,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Button(examples, text="Open Demo", command=on_open_demo).grid(
            row=0, column=1, rowspan=2, sticky="e", padx=(18, 0)
        )
        examples.columnconfigure(0, weight=1)

        self.recent_search_var.trace_add("write", lambda *_: self._populate_recent())

    def focus_default(self) -> None:
        """Place keyboard focus on the most useful Home control."""
        if self._recent_records:
            self.recent_search_entry.focus_set()
        else:
            self.new_project_button.focus_set()

    def _open_workspace(self, profile: str) -> None:
        if self._on_workspace is not None:
            self._on_workspace(profile)

    def _open_problems(self) -> None:
        if self._on_show_problems is not None:
            self._on_show_problems()

    def _open_recovery(self) -> None:
        if self._on_show_recovery is not None:
            self._on_show_recovery()

    def set_active_project(self, summary: dict[str, object]) -> None:
        """Render a truthful, read-only project-health snapshot.

        The application layer owns all engineering calculations. This surface only
        formats supplied canonical diagnostics, verification, evidence, and recovery
        state and never derives engineering acceptance values itself.
        """
        name = str(summary.get("name") or "Untitled Project")
        path = str(summary.get("path") or "").strip()
        dirty = bool(summary.get("dirty", False))
        analysis_count = int(summary.get("analysis_count", 0) or 0)
        room_count = int(summary.get("room_count", 0) or 0)
        device_count = int(summary.get("device_count", 0) or 0)

        self.project_name_var.set(name)
        self.project_path_var.set(path if path else "Not yet saved")
        self.project_counts_var.set(
            f"{analysis_count} analyses • {room_count} rooms • {device_count} devices"
        )

        diagnostics_available = bool(summary.get("diagnostics_available", False))
        error_count = int(summary.get("error_count", 0) or 0)
        warning_count = int(summary.get("warning_count", 0) or 0)
        if not diagnostics_available:
            diagnostic_state = "neutral"
            diagnostic_text = "Problems: unavailable"
        elif error_count:
            diagnostic_state = "fail"
            diagnostic_text = (
                f"Problems: {error_count} error"
                f"{'s' if error_count != 1 else ''} • {warning_count} warning"
                f"{'s' if warning_count != 1 else ''}"
            )
        elif warning_count:
            diagnostic_state = "warning"
            diagnostic_text = (
                f"Problems: {warning_count} warning"
                f"{'s' if warning_count != 1 else ''}"
            )
        else:
            diagnostic_state = "pass"
            diagnostic_text = "Problems: clear"
        self.project_diagnostics_var.set(diagnostic_text)
        self.project_diagnostics_label.configure(
            style=status_style_name(diagnostic_state)
        )

        verification_available = bool(summary.get("verification_available", False))
        configured_count = int(summary.get("configured_analysis_count", 0) or 0)
        current_count = int(summary.get("current_count", 0) or 0)
        stale_count = int(summary.get("stale_count", 0) or 0)
        unverifiable_count = int(
            summary.get("dependency_freshness_unverifiable_count", 0) or 0
        )
        not_verified_count = int(summary.get("not_verified_count", 0) or 0)
        if not verification_available:
            verification_state = "neutral"
            verification_text = "Verification: unavailable"
        elif configured_count == 0:
            verification_state = "neutral"
            verification_text = "Verification: not configured"
        elif stale_count or unverifiable_count or not_verified_count:
            verification_state = "warning"
            verification_text = (
                "Verification: "
                f"{current_count} current • {stale_count} stale • "
                f"{not_verified_count} not verified • "
                f"{unverifiable_count} freshness unverified"
            )
        else:
            verification_state = "pass"
            verification_text = f"Verification: {current_count} configured analyses current"
        self.project_verification_var.set(verification_text)
        self.project_verification_label.configure(
            style=status_style_name(verification_state)
        )

        evidence_count = int(summary.get("evidence_record_count", 0) or 0)
        self.project_evidence_var.set(
            f"Evidence: {evidence_count} retained verification "
            f"record{'s' if evidence_count != 1 else ''}"
        )

        recovery_count = int(summary.get("recovery_count", 0) or 0)
        recovery_issue_count = int(summary.get("recovery_issue_count", 0) or 0)
        if recovery_issue_count:
            recovery_state = "warning"
            recovery_text = (
                f"Recovery: {recovery_count} candidate"
                f"{'s' if recovery_count != 1 else ''} • "
                f"{recovery_issue_count} unreadable"
            )
        elif recovery_count:
            recovery_state = "warning"
            recovery_text = (
                f"Recovery: {recovery_count} saved candidate"
                f"{'s' if recovery_count != 1 else ''}"
            )
        else:
            recovery_state = "neutral"
            recovery_text = "Recovery: no saved recovery candidates"
        self.project_recovery_var.set(recovery_text)
        self.project_recovery_label.configure(style=status_style_name(recovery_state))

        if error_count:
            project_state = "fail"
            project_state_text = f"{error_count} open error{'s' if error_count != 1 else ''}"
        elif warning_count or stale_count or unverifiable_count or not_verified_count:
            project_state = "warning"
            project_state_text = "Review required"
        elif dirty:
            project_state = "warning"
            project_state_text = "Unsaved changes"
        elif path:
            project_state = "pass"
            project_state_text = "Saved"
        else:
            project_state = "neutral"
            project_state_text = "Unsaved project"
        self.project_state_var.set(project_state_text)
        self.project_state_label.configure(style=status_style_name(project_state))

    def set_recent_projects(self, records: list[dict[str, str]]) -> None:
        self._recent_records = []
        for record in records:
            path = str(record.get("path") or "").strip()
            if not path:
                continue
            self._recent_records.append(
                {
                    "name": str(record.get("name") or path),
                    "path": path,
                    "status": str(record.get("status") or "Available"),
                    "modified": str(record.get("modified") or "—"),
                }
            )
        self._populate_recent()

    def _filtered_recent_records(self) -> list[dict[str, str]]:
        query = self.recent_search_var.get().strip().casefold()
        if not query:
            return list(self._recent_records)
        return [
            record
            for record in self._recent_records
            if query
            in " ".join(
                (
                    record["name"],
                    record["path"],
                    record["status"],
                    record["modified"],
                )
            ).casefold()
        ]

    def _populate_recent(self) -> None:
        selection = self.recent_tree.selection()
        selected_path = (
            self._recent_paths.get(selection[0])
            if selection
            else None
        )
        for item in self.recent_tree.get_children():
            self.recent_tree.delete(item)
        self._recent_paths.clear()

        visible = self._filtered_recent_records()
        for index, record in enumerate(visible):
            iid = f"recent-{index}"
            self._recent_paths[iid] = record["path"]
            self.recent_tree.insert(
                "",
                "end",
                iid=iid,
                text=record["name"],
                values=(
                    record["path"],
                    record["status"],
                    record["modified"],
                ),
            )

        total = len(self._recent_records)
        self.recent_count_var.set(f"{len(visible)} of {total} recent projects")
        self.recent_hint.configure(
            text=(
                "No recent projects in this session."
                if total == 0
                else (
                    "No recent projects match the search."
                    if not visible
                    else f"{total} recent project{'s' if total != 1 else ''}."
                )
            )
        )

        target = None
        if selected_path is not None:
            for iid, path in self._recent_paths.items():
                if path == selected_path:
                    target = iid
                    break
        children = self.recent_tree.get_children()
        if target is None and children:
            target = children[0]
        if target is not None:
            self.recent_tree.selection_set(target)
            self.recent_tree.focus(target)
            self.recent_tree.see(target)

    def _open_selected_recent(self, _event=None):
        selection = self.recent_tree.selection()
        if not selection:
            return "break"
        path = self._recent_paths.get(selection[0])
        if path:
            self._on_open_recent(path)
        return "break"

    def _forget_selected_recent(self, _event=None):
        if self._on_forget_recent is None:
            return "break"
        selection = self.recent_tree.selection()
        if not selection:
            return "break"
        path = self._recent_paths.get(selection[0])
        if path:
            self._on_forget_recent(path)
        return "break"

    def _show_recent_context_menu(self, event: tk.Event):
        iid = self.recent_tree.identify_row(event.y)
        if iid:
            self.recent_tree.selection_set(iid)
            self.recent_tree.focus(iid)
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(
            label="Open Project",
            command=self._open_selected_recent,
        )
        menu.add_command(
            label="Remove from Recent",
            command=self._forget_selected_recent,
            state="normal" if self._on_forget_recent is not None else "disabled",
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"
