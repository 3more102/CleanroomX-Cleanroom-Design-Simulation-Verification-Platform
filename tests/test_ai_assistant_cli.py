from __future__ import annotations

import json
from pathlib import Path

import pytest

from cleanroomx.ai_assistant_cli import (
    ProjectReviewChangedError, build_offline_review, main,
)
from cleanroomx.project import new_project, save_project_document


def test_headless_review_is_revision_bound_and_does_not_modify_file(tmp_path, capsys):
    source = tmp_path / "facility.json"
    save_project_document(source, new_project("Facility Review"))
    original = source.read_bytes()

    assert main([str(source), "--actions", "--format", "json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["schema"] == "cleanroomx.ai-offline-review"
    assert output["model_used"] is False
    assert output["network_used"] is False
    assert output["source_stable_during_review"] is True
    assert len(output["source_revision_sha256"]) == 64
    assert output["context"]["project"]["name"] == "Facility Review"
    assert output["action_plan"]["schema"] == "cleanroomx.ai-assistant-action-plan"
    assert source.read_bytes() == original


def test_headless_review_text_is_explicit_about_limitations(tmp_path, capsys):
    source = tmp_path / "working.json"
    save_project_document(source, new_project())
    assert main([str(source), "--format", "text"]) == 0
    output = capsys.readouterr().out
    assert "LOCAL EVIDENCE REVIEW" in output
    assert "No model request or solver execution was performed." in output
    assert "Source revision:" in output


def test_headless_review_rejects_invalid_arguments_and_missing_project(
    tmp_path, capsys
):
    source = tmp_path / "not-found.json"
    assert main([str(source)]) == 2
    assert "cleanroomx-ai-review:" in capsys.readouterr().err
    assert main([str(source), "--max-findings", "0"]) == 2
    assert "max_findings" in capsys.readouterr().err
    with pytest.raises(ValueError):
        build_offline_review(source, max_findings=True)


def test_headless_review_fails_closed_if_source_changes(tmp_path, monkeypatch):
    from cleanroomx import ai_assistant_cli

    source = tmp_path / "facility.json"
    save_project_document(source, new_project())
    original = ai_assistant_cli.build_assistant_context

    def mutate_source(project, **kwargs):
        result = original(project, **kwargs)
        # Simulate a concurrent writer replacing the saved source.
        source.write_text(source.read_text(encoding="utf-8") + " ", encoding="utf-8")
        return result

    monkeypatch.setattr(ai_assistant_cli, "build_assistant_context", mutate_source)
    with pytest.raises(ProjectReviewChangedError, match="changed during AI review"):
        build_offline_review(source)


def test_cli_reports_project_revision_change_without_output(monkeypatch, capsys):
    from cleanroomx import ai_assistant_cli

    def changed(*_args, **_kwargs):
        raise ProjectReviewChangedError("Saved project revision changed")

    monkeypatch.setattr(ai_assistant_cli, "build_offline_review", changed)
    assert main(["does-not-matter.json"]) == 2
    output = capsys.readouterr()
    assert not output.out
    assert "Saved project revision changed" in output.err


def test_cli_does_not_mask_unexpected_runtime_error(monkeypatch):
    from cleanroomx import ai_assistant_cli

    def unexpected(*_args, **_kwargs):
        raise RuntimeError("Unexpected programming defect")

    monkeypatch.setattr(ai_assistant_cli, "build_offline_review", unexpected)
    with pytest.raises(RuntimeError, match="Unexpected programming defect"):
        main(["does-not-matter.json"])
