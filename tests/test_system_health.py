from __future__ import annotations

import cleanroomx.system_health as system_health


def _check_by_id(report: dict, check_id: str) -> dict:
    return next(item for item in report["checks"] if item["id"] == check_id)


def test_system_health_report_has_stable_schema_and_summary() -> None:
    report = system_health.build_system_health_report()

    assert report["schema"] == "cleanroomx.system-health"
    assert report["schema_version"] == 1
    assert report["deep"] is False
    assert report["require_desktop"] is False
    assert report["application"]["version"] == system_health.__version__
    assert report["status"] in {"ready", "ready_with_warnings", "not_ready"}
    assert report["summary"]["check_count"] == len(report["checks"])

    ids = [item["id"] for item in report["checks"]]
    assert len(ids) == len(set(ids))
    assert set(item["status"] for item in report["checks"]) <= {"pass", "warn", "fail"}
    assert all("remediation" in item for item in report["checks"])

    expected_required_ready = not any(
        item["required"] and item["status"] == "fail"
        for item in report["checks"]
    )
    assert report["required_ready"] is expected_required_ready
    assert sum(report["summary"][state] for state in ("pass", "warn", "fail")) == len(report["checks"])


def test_missing_optional_bim_is_warning_but_strict_bim_is_failure(monkeypatch) -> None:
    real_import = system_health.import_module

    def fake_import(name: str, package: str | None = None):
        if name == "ifcopenshell":
            raise ImportError("synthetic missing native BIM runtime")
        return real_import(name, package)

    monkeypatch.setattr(system_health, "import_module", fake_import)

    optional = system_health.build_system_health_report(require_bim=False)
    optional_bim = _check_by_id(optional, "native-bim")
    assert optional_bim["required"] is False
    assert optional_bim["status"] == "warn"
    assert "cleanroomx[bim]" in optional_bim["remediation"]

    strict = system_health.build_system_health_report(require_bim=True)
    strict_bim = _check_by_id(strict, "native-bim")
    assert strict_bim["required"] is True
    assert strict_bim["status"] == "fail"
    assert strict["required_ready"] is False
    assert strict["status"] == "not_ready"


def test_registry_failure_is_reported_as_required_health_failure(monkeypatch) -> None:
    def fail_registry():
        raise RuntimeError("synthetic registry failure")

    monkeypatch.setattr(system_health, "validate_application_registry", fail_registry)
    report = system_health.build_system_health_report()

    registry = _check_by_id(report, "application-registry")
    plugins = _check_by_id(report, "plugin-discovery")
    assert registry["required"] is True
    assert registry["status"] == "fail"
    assert registry["details"]["error_type"] == "RuntimeError"
    assert registry["remediation"]
    assert plugins["status"] == "warn"
    assert plugins["remediation"]
    assert report["required_ready"] is False


def test_tk_check_initializes_headless_tcl_interpreter(monkeypatch) -> None:
    class FakeInterpreter:
        def eval(self, command: str) -> str:
            assert command == "info patchlevel"
            return "8.6.14"

    class FakeTkinter:
        TkVersion = 8.6
        TclVersion = 8.6
        TclError = RuntimeError

        @staticmethod
        def Tcl():
            return FakeInterpreter()

    real_import = system_health.import_module

    def fake_import(name: str, package: str | None = None):
        if name == "tkinter":
            return FakeTkinter
        return real_import(name, package)

    monkeypatch.setattr(system_health, "import_module", fake_import)
    check = system_health._tk_check()

    assert check["status"] == "pass"
    assert check["required"] is True
    assert check["details"]["tcl_patchlevel"] == "8.6.14"
    assert check["details"]["display_probe_performed"] is False


def test_tk_check_reports_interpreter_initialization_failure(monkeypatch) -> None:
    class FakeTkinter:
        TkVersion = 8.6
        TclVersion = 8.6
        TclError = RuntimeError

        @staticmethod
        def Tcl():
            raise RuntimeError("synthetic Tcl initialization failure")

    real_import = system_health.import_module

    def fake_import(name: str, package: str | None = None):
        if name == "tkinter":
            return FakeTkinter
        return real_import(name, package)

    monkeypatch.setattr(system_health, "import_module", fake_import)
    check = system_health._tk_check()

    assert check["status"] == "fail"
    assert check["required"] is True
    assert check["details"]["error_type"] == "RuntimeError"
    assert check["details"]["display_probe_performed"] is False
    assert check["remediation"]


def test_deep_health_executes_packaged_active_analysis(monkeypatch) -> None:
    calls: list[tuple[str, dict, object]] = []

    class FakeRun:
        status = "pass"
        result = {"synthetic": True}

    def fake_run(kind: str, payload: dict, *, base_dir=None):
        calls.append((kind, payload, base_dir))
        return FakeRun()

    monkeypatch.setattr(system_health, "run_analysis", fake_run)
    report = system_health.build_system_health_report(deep=True)

    deep = _check_by_id(report, "packaged-demo-analysis")
    assert report["deep"] is True
    assert deep["required"] is True
    assert deep["status"] == "pass"
    assert deep["details"]["analysis_kind"] == calls[0][0]
    assert calls[0][2] is not None


def test_deep_health_failure_is_required_and_fail_closed(monkeypatch) -> None:
    def fail_run(*_args, **_kwargs):
        raise RuntimeError("synthetic demo execution failure")

    monkeypatch.setattr(system_health, "run_analysis", fail_run)
    report = system_health.build_system_health_report(deep=True)

    deep = _check_by_id(report, "packaged-demo-analysis")
    assert deep["required"] is True
    assert deep["status"] == "fail"
    assert deep["details"]["error_type"] == "RuntimeError"
    assert report["required_ready"] is False
    assert report["status"] == "not_ready"

def test_desktop_display_check_initializes_hidden_root(monkeypatch) -> None:
    events: list[str] = []

    class FakeRoot:
        def withdraw(self) -> None:
            events.append("withdraw")

        def update_idletasks(self) -> None:
            events.append("update_idletasks")

        def destroy(self) -> None:
            events.append("destroy")

    class FakeTkinter:
        TclError = RuntimeError

        @staticmethod
        def Tk():
            events.append("Tk")
            return FakeRoot()

    real_import = system_health.import_module

    def fake_import(name: str, package: str | None = None):
        if name == "tkinter":
            return FakeTkinter
        return real_import(name, package)

    monkeypatch.setattr(system_health, "import_module", fake_import)
    check = system_health._desktop_display_check()

    assert check["status"] == "pass"
    assert check["required"] is True
    assert check["details"]["display_probe_performed"] is True
    assert events == ["Tk", "withdraw", "update_idletasks", "destroy"]


def test_desktop_display_check_fails_closed_when_tk_root_cannot_initialize(monkeypatch) -> None:
    class FakeTkinter:
        TclError = RuntimeError

        @staticmethod
        def Tk():
            raise RuntimeError("synthetic desktop display failure")

    real_import = system_health.import_module

    def fake_import(name: str, package: str | None = None):
        if name == "tkinter":
            return FakeTkinter
        return real_import(name, package)

    monkeypatch.setattr(system_health, "import_module", fake_import)
    check = system_health._desktop_display_check()

    assert check["status"] == "fail"
    assert check["required"] is True
    assert check["details"]["display_probe_performed"] is True
    assert check["details"]["error_type"] == "RuntimeError"
    assert check["remediation"]


def test_require_desktop_adds_required_display_probe(monkeypatch) -> None:
    monkeypatch.setattr(
        system_health,
        "_desktop_display_check",
        lambda: system_health._check(
            "desktop-display",
            "Tk desktop display",
            required=True,
            status="pass",
            summary="synthetic desktop display readiness",
        ),
    )

    report = system_health.build_system_health_report(require_desktop=True)

    desktop = _check_by_id(report, "desktop-display")
    assert report["require_desktop"] is True
    assert desktop["required"] is True
    assert desktop["status"] == "pass"


def _synthetic_health_report(
    checks: list[dict],
    *,
    required_ready: bool = True,
    require_bim: bool = False,
    require_desktop: bool = False,
    deep: bool = False,
    version: str = "test",
) -> dict:
    return {
        "schema": "cleanroomx.system-health",
        "schema_version": 1,
        "application": {"name": "CleanroomX", "version": version},
        "runtime": {"platform": "test", "machine": "test", "python": "test"},
        "status": "ready" if required_ready else "not_ready",
        "required_ready": required_ready,
        "require_bim": require_bim,
        "require_desktop": require_desktop,
        "deep": deep,
        "summary": {
            "pass": sum(item["status"] == "pass" for item in checks),
            "warn": sum(item["status"] == "warn" for item in checks),
            "fail": sum(item["status"] == "fail" for item in checks),
            "check_count": len(checks),
        },
        "checks": checks,
    }


def _synthetic_check(
    check_id: str,
    status: str,
    *,
    required: bool = True,
) -> dict:
    return {
        "id": check_id,
        "label": check_id,
        "required": required,
        "status": status,
        "summary": f"{check_id} is {status}",
        "details": {},
        "remediation": None if status == "pass" else f"Repair {check_id}.",
    }


def test_system_health_comparison_detects_regressions_and_improvements() -> None:
    baseline = _synthetic_health_report(
        [
            _synthetic_check("runtime", "pass"),
            _synthetic_check("plugin", "warn", required=False),
        ],
        version="1.0",
    )
    current = _synthetic_health_report(
        [
            _synthetic_check("runtime", "warn"),
            _synthetic_check("plugin", "pass", required=False),
        ],
        version="1.1",
    )

    comparison = system_health.compare_system_health_reports(baseline, current)

    assert comparison["schema"] == "cleanroomx.system-health-comparison"
    assert comparison["schema_version"] == 1
    assert comparison["state"] == "regressed"
    assert comparison["regressed"] is True
    assert comparison["improved"] is True
    assert comparison["baseline_application_version"] == "1.0"
    assert comparison["current_application_version"] == "1.1"
    assert comparison["regressions"] == [
        {
            "id": "runtime",
            "label": "runtime",
            "from": "pass",
            "to": "warn",
            "required": True,
            "summary": "runtime is warn",
            "remediation": "Repair runtime.",
        }
    ]
    assert comparison["improvements"][0]["id"] == "plugin"


def test_system_health_comparison_treats_removed_required_check_as_coverage_regression() -> None:
    baseline = _synthetic_health_report(
        [_synthetic_check("required-probe", "pass")]
    )
    current = _synthetic_health_report([])

    comparison = system_health.compare_system_health_reports(baseline, current)

    assert comparison["regressed"] is True
    assert comparison["state"] == "regressed"
    assert comparison["summary"]["required_check_coverage_regressed"] is True
    assert comparison["removed_checks"] == [
        {"id": "required-probe", "status": "pass", "required": True}
    ]


def test_system_health_comparison_rejects_incompatible_probe_profiles() -> None:
    baseline = _synthetic_health_report(
        [_synthetic_check("runtime", "pass")],
        require_desktop=False,
    )
    current = _synthetic_health_report(
        [_synthetic_check("runtime", "pass")],
        require_desktop=True,
    )

    try:
        system_health.compare_system_health_reports(baseline, current)
    except ValueError as exc:
        assert "baseline profile does not match" in str(exc)
    else:
        raise AssertionError("profile mismatch must be rejected")


def test_system_health_comparison_rejects_duplicate_check_ids() -> None:
    duplicate = _synthetic_health_report(
        [
            _synthetic_check("runtime", "pass"),
            _synthetic_check("runtime", "warn"),
        ]
    )
    current = _synthetic_health_report([_synthetic_check("runtime", "pass")])

    try:
        system_health.compare_system_health_reports(duplicate, current)
    except ValueError as exc:
        assert "duplicate check id" in str(exc)
    else:
        raise AssertionError("duplicate baseline check ids must be rejected")


def test_system_health_comparison_rejects_malformed_schema_fields() -> None:
    baseline = _synthetic_health_report([_synthetic_check("runtime", "pass")])
    current = _synthetic_health_report([_synthetic_check("runtime", "pass")])

    baseline["schema_version"] = True
    try:
        system_health.compare_system_health_reports(baseline, current)
    except ValueError as exc:
        assert "unsupported system-health schema version" in str(exc)
    else:
        raise AssertionError("boolean schema version must be rejected")

    baseline = _synthetic_health_report([_synthetic_check("runtime", "pass")])
    baseline["checks"][0]["status"] = []
    try:
        system_health.compare_system_health_reports(baseline, current)
    except ValueError as exc:
        assert "unsupported status" in str(exc)
    else:
        raise AssertionError("non-string check status must be rejected")
