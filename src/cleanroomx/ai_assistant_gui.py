"""Small desktop chat window for CleanroomX's read-only AI advisor."""

from __future__ import annotations

import argparse
from pathlib import Path
from threading import Thread
from typing import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cleanroomx-ai-gui",
        description="Read-only AI project advisor; not a substitute for CFD verification.",
    )
    parser.add_argument("project", nargs="?", help="Existing CleanroomX project JSON")
    args = parser.parse_args(argv)

    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    project = args.project or filedialog.askopenfilename(
        title="Select a CleanroomX project",
        filetypes=[("CleanroomX project", "*.json"), ("All files", "*.*")],
    )
    if not project:
        return 1
    project_path = Path(project).expanduser().resolve(strict=False)

    from .ai_assistant import OpenAIResponsesClient, register_project_advice_agent
    from .multi_agent import ChatSessionStore, MultiAgentCoordinator

    class AdvisorWindow(tk.Tk):
        def __init__(self) -> None:
            super().__init__()
            self.title("CleanroomX | AI Project Advisor")
            self.minsize(740, 540)
            self.geometry("900x660")
            self.store = ChatSessionStore()
            self.store.create_session("project-review", "Project advisor")
            self.busy = False

            heading = ttk.Frame(self, padding=12)
            heading.pack(fill="x")
            ttk.Label(
                heading, text="AI Project Advisor", font=("Segoe UI", 16, "bold")
            ).pack(anchor="w")
            ttk.Label(
                heading, text=str(project_path), wraplength=850
            ).pack(anchor="w", pady=(3, 0))
            ttk.Label(
                heading,
                text=(
                    "ADVISORY ONLY — NOT VERIFIED ENGINEERING EVIDENCE. "
                    "The assistant never runs CFD or edits project files."
                ),
                foreground="#9b351c",
                wraplength=850,
            ).pack(anchor="w", pady=(6, 0))

            controls = ttk.Frame(self, padding=(12, 2, 12, 8))
            controls.pack(fill="x")
            ttk.Label(controls, text="Provider").pack(side="left")
            self.provider = tk.StringVar(value="offline")
            ttk.Combobox(
                controls,
                textvariable=self.provider,
                values=("offline", "openai"),
                state="readonly",
                width=12,
            ).pack(side="left", padx=(8, 20))
            ttk.Label(controls, text="Model").pack(side="left")
            self.model = tk.StringVar(value="gpt-4.1-mini")
            ttk.Entry(controls, textvariable=self.model, width=25).pack(
                side="left", padx=8
            )
            ttk.Button(
                controls, text="Export chat", command=self.export_chat
            ).pack(side="right")

            transcript_frame = ttk.Frame(self, padding=(12, 0, 12, 6))
            transcript_frame.pack(fill="both", expand=True)
            self.transcript = tk.Text(
                transcript_frame, wrap="word", state="disabled", padx=12, pady=12
            )
            scrollbar = ttk.Scrollbar(
                transcript_frame, command=self.transcript.yview
            )
            self.transcript.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            self.transcript.pack(side="left", fill="both", expand=True)

            composer = ttk.Frame(self, padding=12)
            composer.pack(fill="x")
            self.question = tk.Text(composer, height=3, wrap="word")
            self.question.pack(side="left", fill="both", expand=True)
            self.send_button = ttk.Button(
                composer, text="Ask", command=self.send_question
            )
            self.send_button.pack(side="left", padx=(12, 0))
            self.status = tk.StringVar(
                value="Offline mode reviews saved analysis definitions. "
                      "OpenAI mode sends limited metadata and questions externally."
            )
            ttk.Label(
                self, textvariable=self.status, padding=(12, 0, 12, 10),
                wraplength=850,
            ).pack(anchor="w")

        def show(self, label: str, content: str) -> None:
            self.transcript.configure(state="normal")
            self.transcript.insert("end", f"{label}\n{content}\n\n")
            self.transcript.configure(state="disabled")
            self.transcript.see("end")

        def export_chat(self) -> None:
            destination = filedialog.asksaveasfilename(
                title="Export assistant chat",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json")],
            )
            if not destination:
                return
            if Path(destination).resolve(strict=False) == project_path:
                messagebox.showerror("Protected project", "Chat cannot overwrite the project.")
                return
            try:
                self.store.save(destination)
            except (OSError, ValueError, RuntimeError) as exc:
                messagebox.showerror("Export failed", str(exc))
                return
            self.status.set("Chat workspace exported. Engineering project unchanged.")

        def send_question(self) -> None:
            if self.busy:
                return
            question = self.question.get("1.0", "end-1c").strip()
            if not question:
                return
            if len(question) > 4000:
                messagebox.showerror("Question too long", "Maximum length: 4000 characters.")
                return
            provider = self.provider.get()
            model = self.model.get()
            self.question.delete("1.0", "end")
            self.show("You", question)
            self.busy = True
            self.send_button.configure(state="disabled")
            self.status.set("Review in progress; the project file remains read-only.")

            def work() -> None:
                try:
                    client = (
                        OpenAIResponsesClient(model=model)
                        if provider == "openai"
                        else None
                    )
                    coordinator = MultiAgentCoordinator(self.store)
                    register_project_advice_agent(
                        coordinator,
                        project_path=project_path,
                        client=client,
                    )
                    batch = coordinator.run(
                        "project-review", question, agent_ids=["project-advisor"]
                    )
                    result = batch.results[0] if batch.results else None
                    if batch.commit_state != "committed":
                        output = "Chat changed concurrently; no advice committed."
                    elif result is None:
                        output = "No assistant result was returned."
                    elif result.state == "error":
                        output = f"{result.error_type}: {result.error_message}"
                    else:
                        output = result.content
                except Exception as exc:
                    output = f"Review failed: {type(exc).__name__}: {exc}"

                def render() -> None:
                    self.show("Advisor (unverified)", output)
                    self.busy = False
                    self.send_button.configure(state="normal")
                    self.status.set("Review complete. Validate conclusions through real analyses.")

                try:
                    self.after(0, render)
                except (RuntimeError, tk.TclError):
                    pass

            Thread(target=work, daemon=True).start()

    app = AdvisorWindow()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
