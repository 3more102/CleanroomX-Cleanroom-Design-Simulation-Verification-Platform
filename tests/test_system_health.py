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
    assert plugins["status"] == "warn"
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

