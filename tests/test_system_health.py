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
    assert report["require_qualified_python"] is False
    assert report["require_installed_distribution"] is False
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


def test_unqualified_python_is_advisory_unless_release_qualification_is_required(monkeypatch) -> None:
    monkeypatch.setattr(system_health.sys, "version_info", (3, 14, 0))

    advisory = system_health._python_qualification_check(required=False)
    assert advisory["required"] is False
    assert advisory["status"] == "warn"
    assert advisory["remediation"]

    strict = system_health._python_qualification_check(required=True)
    assert strict["required"] is True
    assert strict["status"] == "fail"
    assert strict["remediation"]


def test_require_qualified_python_promotes_unqualified_runtime_to_required_failure(monkeypatch) -> None:
    monkeypatch.setattr(system_health.sys, "version_info", (3, 14, 0))

    report = system_health.build_system_health_report(require_qualified_python=True)
    qualification = _check_by_id(report, "python-release-qualification")

    assert report["require_qualified_python"] is True
    assert qualification["required"] is True
    assert qualification["status"] == "fail"
    assert report["required_ready"] is False
    assert report["status"] == "not_ready"


def _mock_distribution_origin(monkeypatch, root) -> None:
    class FakeDistribution:
        @staticmethod
        def locate_file(_name: str):
            return root

    monkeypatch.setattr(
        system_health.metadata,
        "distribution",
        lambda name: FakeDistribution() if name == "cleanroomx" else None,
    )


def test_distribution_identity_matches_installed_metadata_and_origin(monkeypatch) -> None:
    monkeypatch.setattr(
        system_health.metadata,
        "version",
        lambda name: system_health.__version__ if name == "cleanroomx" else "unexpected",
    )
    distribution_root = system_health.Path(system_health.__file__).resolve().parents[1]
    _mock_distribution_origin(monkeypatch, distribution_root)

    check = system_health._distribution_identity_check()

    assert check["required"] is False
    assert check["status"] == "pass"
    assert check["details"]["metadata_available"] is True
    assert check["details"]["module_version"] == system_health.__version__
    assert check["details"]["distribution_version"] == system_health.__version__
    assert check["details"]["origin_matches_distribution"] is True
    assert check["details"]["distribution_path"] == str(distribution_root)
    assert check["remediation"] is None


def test_distribution_identity_detects_shadowed_same_version_import(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        system_health.metadata,
        "version",
        lambda _name: system_health.__version__,
    )
    _mock_distribution_origin(monkeypatch, tmp_path)

    advisory = system_health._distribution_identity_check(required=False)
    assert advisory["required"] is False
    assert advisory["status"] == "warn"
    assert advisory["details"]["origin_matches_distribution"] is False
    assert advisory["details"]["distribution_path"] == str(tmp_path.resolve())
    assert advisory["remediation"]
    assert "shadowing" in advisory["remediation"].lower()

    strict = system_health._distribution_identity_check(required=True)
    assert strict["required"] is True
    assert strict["status"] == "fail"
    assert strict["details"]["origin_matches_distribution"] is False
    assert strict["remediation"]


def test_missing_distribution_metadata_is_advisory_unless_required(monkeypatch) -> None:
    def missing_distribution(_name: str) -> str:
        raise system_health.metadata.PackageNotFoundError("cleanroomx")

    monkeypatch.setattr(system_health.metadata, "version", missing_distribution)

    advisory = system_health._distribution_identity_check(required=False)
    assert advisory["required"] is False
    assert advisory["status"] == "warn"
    assert advisory["details"]["metadata_available"] is False
    assert advisory["details"]["origin_matches_distribution"] is None
    assert advisory["remediation"]

    strict = system_health.build_system_health_report(
        require_installed_distribution=True
    )
    strict_identity = _check_by_id(strict, "distribution-identity")
    assert strict["require_installed_distribution"] is True
    assert strict_identity["required"] is True
    assert strict_identity["status"] == "fail"
    assert strict["required_ready"] is False
    assert strict["status"] == "not_ready"


def test_distribution_version_mismatch_warns_and_can_fail_strict(monkeypatch) -> None:
    monkeypatch.setattr(system_health.metadata, "version", lambda _name: "0.0.0")

    advisory = system_health._distribution_identity_check(required=False)
    assert advisory["required"] is False
    assert advisory["status"] == "warn"
    assert advisory["details"]["distribution_version"] == "0.0.0"
    assert advisory["details"]["origin_matches_distribution"] is None
    assert advisory["remediation"]

    strict = system_health._distribution_identity_check(required=True)
    assert strict["required"] is True
    assert strict["status"] == "fail"
    assert strict["remediation"]


def test_distribution_identity_handles_metadata_origin_disappearing(monkeypatch) -> None:
    monkeypatch.setattr(
        system_health.metadata,
        "version",
        lambda _name: system_health.__version__,
    )

    def missing_distribution(_name: str):
        raise system_health.metadata.PackageNotFoundError("cleanroomx")

    monkeypatch.setattr(system_health.metadata, "distribution", missing_distribution)

    advisory = system_health._distribution_identity_check(required=False)
    assert advisory["status"] == "warn"
    assert advisory["details"]["metadata_available"] is False
    assert advisory["details"]["distribution_version"] == system_health.__version__
    assert advisory["details"]["origin_matches_distribution"] is None
    assert advisory["remediation"]


def test_distribution_identity_does_not_mask_metadata_runtime_defects(monkeypatch) -> None:
    def fail_metadata(_name: str) -> str:
        raise RuntimeError("synthetic metadata runtime defect")

    monkeypatch.setattr(system_health.metadata, "version", fail_metadata)

    try:
        system_health._distribution_identity_check()
    except RuntimeError as exc:
        assert "synthetic metadata runtime defect" in str(exc)
    else:
        raise AssertionError("unexpected metadata runtime defects must propagate")

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
    require_qualified_python: bool = False,
    require_installed_distribution: bool = False,
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
        "status": (
            "not_ready"
            if not required_ready
            else "ready_with_warnings"
            if any(item["status"] == "warn" for item in checks)
            else "ready"
        ),
        "required_ready": required_ready,
        "require_qualified_python": require_qualified_python,
        "require_installed_distribution": require_installed_distribution,
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


def test_system_health_comparison_detects_requiredness_downgrade_as_policy_regression() -> None:
    baseline = _synthetic_health_report(
        [_synthetic_check("runtime", "pass", required=True)]
    )
    current = _synthetic_health_report(
        [_synthetic_check("runtime", "pass", required=False)]
    )

    comparison = system_health.compare_system_health_reports(baseline, current)

    assert comparison["regressed"] is True
    assert comparison["state"] == "regressed"
    assert comparison["summary"]["required_check_coverage_regressed"] is True
    assert comparison["summary"]["requirement_change_count"] == 1
    assert comparison["requirement_changes"] == [
        {
            "id": "runtime",
            "label": "runtime",
            "from_required": True,
            "to_required": False,
            "direction": "downgraded",
            "status": "pass",
        }
    ]


def test_system_health_comparison_marks_requiredness_promotion_as_coverage_expansion() -> None:
    baseline = _synthetic_health_report(
        [_synthetic_check("runtime", "pass", required=False)]
    )
    current = _synthetic_health_report(
        [_synthetic_check("runtime", "pass", required=True)]
    )

    comparison = system_health.compare_system_health_reports(baseline, current)

    assert comparison["regressed"] is False
    assert comparison["improved"] is True
    assert comparison["state"] == "improved"
    assert comparison["summary"]["required_check_coverage_expanded"] is True
    assert comparison["requirement_changes"][0]["direction"] == "promoted"


def test_system_health_comparison_rejects_internally_inconsistent_reports() -> None:
    current = _synthetic_health_report([_synthetic_check("runtime", "pass")])

    baseline = _synthetic_health_report([_synthetic_check("runtime", "pass")])
    baseline["required_ready"] = False
    try:
        system_health.compare_system_health_reports(baseline, current)
    except ValueError as exc:
        assert "required_ready is inconsistent" in str(exc)
    else:
        raise AssertionError("inconsistent required readiness must be rejected")

    baseline = _synthetic_health_report([_synthetic_check("runtime", "pass")])
    baseline["summary"]["pass"] = 0
    try:
        system_health.compare_system_health_reports(baseline, current)
    except ValueError as exc:
        assert "summary.pass must equal 1" in str(exc)
    else:
        raise AssertionError("inconsistent summary counts must be rejected")

    baseline = _synthetic_health_report(
        [_synthetic_check("runtime", "warn", required=False)]
    )
    baseline["status"] = "ready"
    try:
        system_health.compare_system_health_reports(baseline, current)
    except ValueError as exc:
        assert "status must be 'ready_with_warnings'" in str(exc)
    else:
        raise AssertionError("inconsistent aggregate status must be rejected")



def test_health_check_contract_enforces_actionable_remediation() -> None:
    import pytest

    with pytest.raises(ValueError, match="require remediation"):
        system_health._check(
            "synthetic-failure",
            "Synthetic failure",
            required=True,
            status="fail",
            summary="Synthetic failure.",
        )

    with pytest.raises(ValueError, match="require remediation"):
        system_health._check(
            "synthetic-warning",
            "Synthetic warning",
            required=False,
            status="warn",
            summary="Synthetic warning.",
            remediation="   ",
        )

    with pytest.raises(ValueError, match="must not include remediation"):
        system_health._check(
            "synthetic-pass",
            "Synthetic pass",
            required=True,
            status="pass",
            summary="Synthetic pass.",
            remediation="No action should be present.",
        )


def test_registry_non_ready_result_includes_remediation(monkeypatch) -> None:
    monkeypatch.setattr(
        system_health,
        "validate_application_registry",
        lambda: {
            "status": "not_ready",
            "analysis_count": 0,
            "builtin_analysis_count": 0,
            "plugin_analysis_count": 0,
            "callable_target_count": 0,
            "plugin_issue_count": 0,
            "plugin_issues": [],
        },
    )

    report = system_health.build_system_health_report()
    registry = _check_by_id(report, "application-registry")

    assert registry["status"] == "fail"
    assert registry["remediation"]
    assert report["required_ready"] is False


def test_system_health_path_redaction_is_recursive_cross_platform_and_non_mutating(tmp_path) -> None:
    posix_path = str(tmp_path / "private" / "facility.cleanroomx.json")
    windows_path = r"C:\Users\operator\Projects\CleanroomX\python.exe"
    report = {
        "runtime": {"executable": windows_path},
        "checks": [
            {
                "details": {
                    "path": posix_path,
                    "nested": [
                        {
                            "source_path": windows_path,
                            "message": windows_path,
                        }
                    ],
                }
            }
        ],
    }

    redacted = system_health.redact_system_health_paths(report)

    assert report["runtime"]["executable"] == windows_path
    assert report["checks"][0]["details"]["path"] == posix_path
    assert redacted["runtime"]["executable"] == "<redacted>/python.exe"
    assert redacted["checks"][0]["details"]["path"] == "<redacted>/facility.cleanroomx.json"
    assert redacted["checks"][0]["details"]["nested"][0]["source_path"] == "<redacted>/python.exe"
    assert redacted["checks"][0]["details"]["nested"][0]["message"] == windows_path
    assert redacted["privacy"] == {"local_paths_redacted": True}


def test_system_health_comparison_rejects_invalid_remediation_contract() -> None:
    baseline = _synthetic_health_report(
        [_synthetic_check("runtime", "warn", required=False)]
    )
    current = _synthetic_health_report(
        [_synthetic_check("runtime", "pass", required=False)]
    )

    baseline["checks"][0]["remediation"] = None
    try:
        system_health.compare_system_health_reports(baseline, current)
    except ValueError as exc:
        assert "non-passing remediation must be non-empty" in str(exc)
    else:
        raise AssertionError("non-passing baseline checks must carry remediation")

    baseline = _synthetic_health_report(
        [_synthetic_check("runtime", "pass", required=False)]
    )
    baseline["checks"][0]["remediation"] = "stale action"
    try:
        system_health.compare_system_health_reports(baseline, current)
    except ValueError as exc:
        assert "passing remediation must be null" in str(exc)
    else:
        raise AssertionError("passing baseline checks must not carry remediation")
