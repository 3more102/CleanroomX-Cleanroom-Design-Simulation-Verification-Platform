from __future__ import annotations

import json

import cleanroomx.doctor_cli as doctor_cli


def _report(
    *,
    ready: bool = True,
    require_bim: bool = False,
    require_desktop: bool = False,
    deep: bool = False,
) -> dict:
    return {
        "schema": "cleanroomx.system-health",
        "schema_version": 1,
        "application": {"name": "CleanroomX", "version": "test"},
        "runtime": {"platform": "test", "machine": "test", "python": "test"},
        "status": "ready" if ready else "not_ready",
        "required_ready": ready,
        "require_bim": require_bim,
        "require_desktop": require_desktop,
        "deep": deep,
        "summary": {"pass": 1 if ready else 0, "warn": 0, "fail": 0 if ready else 1, "check_count": 1},
        "checks": [
            {
                "id": "synthetic",
                "label": "Synthetic",
                "required": True,
                "status": "pass" if ready else "fail",
                "summary": "synthetic",
                "details": {},
                "remediation": None if ready else "Repair the synthetic runtime.",
            }
        ],
    }


def test_doctor_cli_emits_strict_json_and_success_exit(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        doctor_cli,
        "build_system_health_report",
        lambda *, require_bim=False, require_desktop=False, deep=False: _report(
            ready=True,
            require_bim=require_bim,
            require_desktop=require_desktop,
            deep=deep,
        ),
    )

    assert doctor_cli.main([]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["schema"] == "cleanroomx.system-health"
    assert payload["required_ready"] is True
    assert captured.err == ""


def test_doctor_cli_returns_two_when_required_check_fails(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        doctor_cli,
        "build_system_health_report",
        lambda *, require_bim=False, require_desktop=False, deep=False: _report(
            ready=False,
            require_bim=require_bim,
            require_desktop=require_desktop,
            deep=deep,
        ),
    )

    assert doctor_cli.main([]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "not_ready"
    assert captured.err == ""


def test_doctor_cli_writes_atomic_output_and_forwards_require_bim(monkeypatch, tmp_path, capsys) -> None:
    calls: list[tuple[bool, bool, bool]] = []

    def build(
        *,
        require_bim: bool = False,
        require_desktop: bool = False,
        deep: bool = False,
    ) -> dict:
        calls.append((require_bim, require_desktop, deep))
        return _report(
            ready=True,
            require_bim=require_bim,
            require_desktop=require_desktop,
            deep=deep,
        )

    monkeypatch.setattr(doctor_cli, "build_system_health_report", build)
    output = tmp_path / "doctor.json"

    assert doctor_cli.main(
        ["--require-bim", "--require-desktop", "--deep", "--output", str(output)]
    ) == 0
    assert calls == [(True, True, True)]
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["require_bim"] is True
    assert payload["require_desktop"] is True
    assert payload["deep"] is True
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_doctor_cli_text_format_is_operator_readable(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        doctor_cli,
        "build_system_health_report",
        lambda *, require_bim=False, require_desktop=False, deep=False: _report(
            ready=True,
            require_bim=require_bim,
            require_desktop=require_desktop,
            deep=deep,
        ),
    )

    assert doctor_cli.main(["--format", "text"]) == 0
    captured = capsys.readouterr()
    assert "CleanroomX test system health: ready" in captured.out
    assert "Required readiness: PASS" in captured.out
    assert "[PASS] Synthetic (required) - synthetic" in captured.out
    assert "Action:" not in captured.out
    assert captured.err == ""


def test_doctor_cli_text_format_surfaces_remediation_for_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        doctor_cli,
        "build_system_health_report",
        lambda *, require_bim=False, require_desktop=False, deep=False: _report(
            ready=False,
            require_bim=require_bim,
            require_desktop=require_desktop,
            deep=deep,
        ),
    )

    assert doctor_cli.main(["--format", "text"]) == 2
    captured = capsys.readouterr()
    assert "Action: Repair the synthetic runtime." in captured.out
    assert captured.err == ""


def test_doctor_cli_baseline_comparison_is_emitted_and_can_fail_on_regression(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    baseline = _report(ready=True)
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    current = _report(ready=True)
    current["status"] = "ready_with_warnings"
    current["summary"] = {"pass": 0, "warn": 1, "fail": 0, "check_count": 1}
    current["checks"][0]["status"] = "warn"
    current["checks"][0]["summary"] = "synthetic degraded"
    current["checks"][0]["remediation"] = "Repair the synthetic runtime."

    monkeypatch.setattr(
        doctor_cli,
        "build_system_health_report",
        lambda *, require_bim=False, require_desktop=False, deep=False: {
            **current,
            "require_bim": require_bim,
            "require_desktop": require_desktop,
            "deep": deep,
        },
    )

    assert doctor_cli.main(["--baseline", str(baseline_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["comparison"]["state"] == "regressed"
    assert payload["comparison"]["summary"]["regression_count"] == 1

    assert doctor_cli.main(
        ["--baseline", str(baseline_path), "--fail-on-regression"]
    ) == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["comparison"]["regressed"] is True


def test_doctor_cli_text_format_reports_baseline_drift(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    baseline = _report(ready=True)
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    current = _report(ready=True)
    current["status"] = "ready_with_warnings"
    current["summary"] = {"pass": 0, "warn": 1, "fail": 0, "check_count": 1}
    current["checks"][0]["status"] = "warn"
    current["checks"][0]["summary"] = "synthetic degraded"
    current["checks"][0]["remediation"] = "Repair the synthetic runtime."

    monkeypatch.setattr(
        doctor_cli,
        "build_system_health_report",
        lambda *, require_bim=False, require_desktop=False, deep=False: {
            **current,
            "require_bim": require_bim,
            "require_desktop": require_desktop,
            "deep": deep,
        },
    )

    assert doctor_cli.main(
        ["--baseline", str(baseline_path), "--format", "text"]
    ) == 0
    captured = capsys.readouterr()
    assert "Baseline drift: REGRESSED" in captured.out
    assert "1 regression(s)" in captured.out
    assert "0 requirement change(s)" in captured.out
    assert captured.err == ""


def test_doctor_cli_fail_on_regression_requires_baseline(capsys) -> None:
    assert doctor_cli.main(["--fail-on-regression"]) == 1
    captured = capsys.readouterr()
    assert "--fail-on-regression requires --baseline" in captured.err


def test_doctor_cli_fail_on_warning_is_opt_in_and_uses_exit_four(
    monkeypatch,
    capsys,
) -> None:
    current = _report(ready=True)
    current["status"] = "ready_with_warnings"
    current["summary"] = {"pass": 0, "warn": 1, "fail": 0, "check_count": 1}
    current["checks"][0]["required"] = False
    current["checks"][0]["status"] = "warn"
    current["checks"][0]["summary"] = "synthetic advisory warning"
    current["checks"][0]["remediation"] = "Inspect the synthetic advisory warning."

    monkeypatch.setattr(
        doctor_cli,
        "build_system_health_report",
        lambda *, require_bim=False, require_desktop=False, deep=False: {
            **current,
            "require_bim": require_bim,
            "require_desktop": require_desktop,
            "deep": deep,
        },
    )

    assert doctor_cli.main([]) == 0
    capsys.readouterr()

    assert doctor_cli.main(["--fail-on-warning"]) == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ready_with_warnings"
    assert payload["summary"]["warn"] == 1


def test_doctor_cli_required_failure_precedes_fail_on_warning(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        doctor_cli,
        "build_system_health_report",
        lambda *, require_bim=False, require_desktop=False, deep=False: _report(
            ready=False,
            require_bim=require_bim,
            require_desktop=require_desktop,
            deep=deep,
        ),
    )

    assert doctor_cli.main(["--fail-on-warning"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "not_ready"



def test_doctor_cli_redacts_explicit_local_paths(monkeypatch, capsys) -> None:
    report = _report(ready=True)
    windows_path = r"C:\Users\operator\CleanroomX\gui_demo.cleanroomx.json"
    report["runtime"]["executable"] = r"C:\Python313\python.exe"
    report["checks"][0]["details"] = {
        "path": windows_path,
        "message": windows_path,
    }
    monkeypatch.setattr(
        doctor_cli,
        "build_system_health_report",
        lambda *, require_bim=False, require_desktop=False, deep=False: report,
    )

    assert doctor_cli.main(["--redact-paths"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["runtime"]["executable"] == "<redacted>/python.exe"
    assert payload["checks"][0]["details"]["path"] == "<redacted>/gui_demo.cleanroomx.json"
    assert payload["checks"][0]["details"]["message"] == windows_path
    assert payload["privacy"] == {"local_paths_redacted": True}
