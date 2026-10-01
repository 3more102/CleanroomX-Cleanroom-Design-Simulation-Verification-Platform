from __future__ import annotations

from dataclasses import dataclass

import pytest

import cleanroomx.application as application
from cleanroomx.plugins import (
    PLUGIN_API_VERSION,
    AnalysisPlugin,
    PluginOrigin,
    PluginTrustPolicy,
    discover_analysis_plugins,
    plugin_trust_policy_from_environment,
)


@dataclass(frozen=True)
class _FakeDistribution:
    name: str
    version: str


class _FakeEntryPoint:
    def __init__(
        self,
        name: str,
        value: str,
        loaded,
        *,
        distribution: _FakeDistribution | None = None,
        load_error: BaseException | None = None,
    ) -> None:
        self.name = name
        self.value = value
        self._loaded = loaded
        self.dist = distribution
        self._load_error = load_error
        self.load_count = 0

    def load(self):
        self.load_count += 1
        if self._load_error is not None:
            raise self._load_error
        return self._loaded


class _UnreadableNameEntryPoint:
    value = "pkg.unreadable:registration"
    dist = None

    @property
    def name(self):
        raise SystemExit("metadata aborted")

    def load(self):
        return _plugin("unreachable")


def _parser(payload: dict) -> dict:
    return {"value": float(payload["value"])}


def _runner(model: dict) -> dict:
    return {
        "status": "complete",
        "doubled": model["value"] * 2.0,
    }


def _reporter(result: dict) -> str:
    return f"# Example plugin\n\nDoubled: {result['doubled']}\n"


def _discover_trusted(
    builtin_keys: set[str],
    *,
    entry_points: list[object],
):
    return discover_analysis_plugins(
        builtin_keys,
        entry_points=entry_points,
        trust_policy=PluginTrustPolicy(mode="trusted"),
    )


def _plugin(key: str, *, api_version: int = PLUGIN_API_VERSION) -> AnalysisPlugin:
    return AnalysisPlugin(
        api_version=api_version,
        key=key,
        title=f"{key} title",
        category="Plugin tests",
        description=f"{key} description",
        parser=_parser,
        runner=_runner,
        reporter=_reporter,
    )


def test_plugin_discovery_is_deterministic_and_retains_distribution_identity():
    discovery = _discover_trusted(
        {"builtin"},
        entry_points=[
            _FakeEntryPoint(
                "z-entry",
                "pkg.z:registration",
                _plugin("zeta"),
                distribution=_FakeDistribution("pkg-z", "2.1"),
            ),
            _FakeEntryPoint(
                "a-entry",
                "pkg.a:registration",
                lambda: _plugin("alpha"),
                distribution=_FakeDistribution("pkg-a", "1.4"),
            ),
        ],
    )

    assert [item.plugin.key for item in discovery.plugins] == ["alpha", "zeta"]
    assert discovery.issues == ()
    alpha = discovery.plugins[0]
    assert alpha.origin.entry_point_name == "a-entry"
    assert alpha.origin.entry_point_value == "pkg.a:registration"
    assert alpha.origin.distribution_name == "pkg-a"
    assert alpha.origin.distribution_version == "1.4"


def test_plugin_trust_policy_defaults_to_disabled():
    policy = plugin_trust_policy_from_environment({})

    assert policy == PluginTrustPolicy(mode="disabled")
    assert policy.to_dict() == {
        "mode": "disabled",
        "valid": True,
        "allowlist": [],
        "error": None,
    }


def test_plugin_trust_policy_disabled_blocks_before_import():
    point = _FakeEntryPoint(
        "blocked",
        "pkg.blocked:registration",
        _plugin("blocked"),
        distribution=_FakeDistribution("pkg-blocked", "1.0"),
    )

    discovery = discover_analysis_plugins(
        set(),
        entry_points=[point],
        trust_policy=PluginTrustPolicy(mode="disabled"),
    )

    assert discovery.plugins == ()
    assert point.load_count == 0
    assert len(discovery.issues) == 1
    assert "loading is disabled" in discovery.issues[0].error


def test_plugin_trust_allowlist_canonicalizes_name_and_honors_exact_version_pin():
    point = _FakeEntryPoint(
        "allowed",
        "pkg.allowed:registration",
        _plugin("allowed_plugin"),
        distribution=_FakeDistribution("CleanRoomX.Example_Plugin", "2.4.1"),
    )
    policy = plugin_trust_policy_from_environment(
        {
            "CLEANROOMX_PLUGIN_MODE": "allowlist",
            "CLEANROOMX_PLUGIN_ALLOWLIST": "cleanroomx-example-plugin==2.4.1",
        }
    )

    discovery = discover_analysis_plugins(
        set(),
        entry_points=[point],
        trust_policy=policy,
    )

    assert [item.plugin.key for item in discovery.plugins] == ["allowed_plugin"]
    assert discovery.issues == ()
    assert point.load_count == 1
    assert discovery.trust_policy.to_dict()["allowlist"] == [
        {
            "distribution_name": "cleanroomx-example-plugin",
            "version": "2.4.1",
        }
    ]


def test_plugin_trust_allowlist_blocks_non_allowlisted_distribution_before_import():
    point = _FakeEntryPoint(
        "blocked",
        "pkg.blocked:registration",
        _plugin("blocked"),
        distribution=_FakeDistribution("pkg-blocked", "1.0"),
    )
    policy = plugin_trust_policy_from_environment(
        {
            "CLEANROOMX_PLUGIN_MODE": "allowlist",
            "CLEANROOMX_PLUGIN_ALLOWLIST": "pkg-approved",
        }
    )

    discovery = discover_analysis_plugins(
        set(),
        entry_points=[point],
        trust_policy=policy,
    )

    assert discovery.plugins == ()
    assert point.load_count == 0
    assert "is not allowed" in discovery.issues[0].error


def test_plugin_trust_allowlist_blocks_version_mismatch_before_import():
    point = _FakeEntryPoint(
        "blocked-version",
        "pkg.blocked:registration",
        _plugin("blocked_version"),
        distribution=_FakeDistribution("pkg-approved", "1.9"),
    )
    policy = plugin_trust_policy_from_environment(
        {
            "CLEANROOMX_PLUGIN_MODE": "allowlist",
            "CLEANROOMX_PLUGIN_ALLOWLIST": "pkg-approved==2.0",
        }
    )

    discovery = discover_analysis_plugins(
        set(),
        entry_points=[point],
        trust_policy=policy,
    )

    assert discovery.plugins == ()
    assert point.load_count == 0
    assert "does not match required" in discovery.issues[0].error


def test_plugin_trust_allowlist_blocks_missing_distribution_identity_before_import():
    point = _FakeEntryPoint(
        "missing-dist",
        "pkg.missing:registration",
        _plugin("missing_dist"),
        distribution=None,
    )
    policy = plugin_trust_policy_from_environment(
        {
            "CLEANROOMX_PLUGIN_MODE": "allowlist",
            "CLEANROOMX_PLUGIN_ALLOWLIST": "pkg-missing",
        }
    )

    discovery = discover_analysis_plugins(
        set(),
        entry_points=[point],
        trust_policy=policy,
    )

    assert discovery.plugins == ()
    assert point.load_count == 0
    assert "distribution identity is unavailable" in discovery.issues[0].error


def test_invalid_plugin_trust_configuration_fails_closed_before_import():
    point = _FakeEntryPoint(
        "invalid-policy",
        "pkg.invalid:registration",
        _plugin("invalid_policy"),
        distribution=_FakeDistribution("pkg-invalid", "1.0"),
    )
    policy = plugin_trust_policy_from_environment(
        {"CLEANROOMX_PLUGIN_MODE": "unexpected"}
    )

    discovery = discover_analysis_plugins(
        set(),
        entry_points=[point],
        trust_policy=policy,
    )

    assert policy.valid is False
    assert discovery.plugins == ()
    assert point.load_count == 0
    assert "plugin trust policy invalid" in discovery.issues[0].error


def test_allowlist_with_malformed_entry_fails_closed_before_import():
    point = _FakeEntryPoint(
        "invalid-allowlist",
        "pkg.invalid_allowlist:registration",
        _plugin("invalid_allowlist"),
        distribution=_FakeDistribution("pkg-invalid-allowlist", "1.0"),
    )
    policy = plugin_trust_policy_from_environment(
        {
            "CLEANROOMX_PLUGIN_MODE": "allowlist",
            "CLEANROOMX_PLUGIN_ALLOWLIST": "pkg-a,,pkg-b",
        }
    )

    discovery = discover_analysis_plugins(
        set(),
        entry_points=[point],
        trust_policy=policy,
    )

    assert policy.valid is False
    assert point.load_count == 0
    assert discovery.plugins == ()
    assert "empty entry" in discovery.issues[0].error


def test_application_registry_reports_effective_plugin_trust_policy():
    validation = application.validate_application_registry()

    assert validation["plugin_trust_policy"] == (
        application._PLUGIN_DISCOVERY.trust_policy.to_dict()
    )


def test_plugin_discovery_isolates_invalid_and_incompatible_plugins():
    discovery = _discover_trusted(
        set(),
        entry_points=[
            _FakeEntryPoint(
                "bad-api",
                "pkg.bad:registration",
                _plugin("bad_api", api_version=PLUGIN_API_VERSION + 1),
            ),
            _FakeEntryPoint(
                "load-failure",
                "pkg.fail:registration",
                None,
                load_error=RuntimeError("import exploded"),
            ),
            _FakeEntryPoint(
                "bad-key",
                "pkg.key:registration",
                _plugin("Not Stable"),
            ),
        ],
    )

    assert discovery.plugins == ()
    assert len(discovery.issues) == 3
    errors = "\n".join(issue.error for issue in discovery.issues)
    assert "unsupported plugin API version" in errors
    assert "import exploded" in errors
    assert "plugin key must match" in errors


def test_plugin_discovery_isolates_system_exit_and_keeps_valid_plugins():
    discovery = _discover_trusted(
        set(),
        entry_points=[
            _FakeEntryPoint(
                "a-exit",
                "pkg.exit:registration",
                None,
                load_error=SystemExit(23),
            ),
            _FakeEntryPoint(
                "z-good",
                "pkg.good:registration",
                _plugin("good_plugin"),
            ),
        ],
    )

    assert [item.plugin.key for item in discovery.plugins] == ["good_plugin"]
    assert len(discovery.issues) == 1
    assert discovery.issues[0].entry_point_name == "a-exit"
    assert discovery.issues[0].error == "SystemExit: 23"


def test_plugin_discovery_isolates_unreadable_entry_point_identity():
    discovery = _discover_trusted(
        set(),
        entry_points=[_UnreadableNameEntryPoint()],
    )

    assert discovery.plugins == ()
    assert len(discovery.issues) == 1
    issue = discovery.issues[0]
    assert issue.entry_point_name == "<unavailable>"
    assert issue.entry_point_value == "pkg.unreadable:registration"
    assert issue.error == "ValueError: entry point name is unavailable"


def test_plugin_discovery_preserves_keyboard_interrupt():
    with pytest.raises(KeyboardInterrupt):
        _discover_trusted(
            set(),
            entry_points=[
                _FakeEntryPoint(
                    "interrupt",
                    "pkg.interrupt:registration",
                    None,
                    load_error=KeyboardInterrupt(),
                )
            ],
        )


def test_plugin_api_version_rejects_boolean_alias_for_integer_one():
    discovery = _discover_trusted(
        set(),
        entry_points=[
            _FakeEntryPoint(
                "bool-api",
                "pkg.bool_api:registration",
                _plugin("bool_api", api_version=True),
            )
        ],
    )

    assert discovery.plugins == ()
    assert len(discovery.issues) == 1
    assert "plugin API version must be an integer" in discovery.issues[0].error


def test_plugin_key_rejects_silent_whitespace_normalization():
    discovery = _discover_trusted(
        set(),
        entry_points=[
            _FakeEntryPoint(
                "space-key",
                "pkg.space_key:registration",
                _plugin(" spaced_key "),
            )
        ],
    )

    assert discovery.plugins == ()
    assert len(discovery.issues) == 1
    assert "leading or trailing whitespace" in discovery.issues[0].error


def test_plugin_discovery_disables_builtin_collision():
    discovery = _discover_trusted(
        {"hvac"},
        entry_points=[
            _FakeEntryPoint("collision", "pkg:registration", _plugin("hvac"))
        ],
    )

    assert discovery.plugins == ()
    assert len(discovery.issues) == 1
    assert "collides with a built-in analysis" in discovery.issues[0].error


def test_plugin_discovery_disables_all_duplicate_plugin_keys():
    discovery = _discover_trusted(
        set(),
        entry_points=[
            _FakeEntryPoint("first", "pkg.one:registration", _plugin("same_key")),
            _FakeEntryPoint("second", "pkg.two:registration", _plugin("same_key")),
        ],
    )

    assert discovery.plugins == ()
    assert len(discovery.issues) == 2
    assert all("all contenders disabled" in issue.error for issue in discovery.issues)


def test_plugin_analysis_runs_through_shared_application_pipeline(monkeypatch):
    origin = PluginOrigin(
        entry_point_name="example_plugin",
        entry_point_value="cleanroomx_example:registration",
        distribution_name="cleanroomx-example",
        distribution_version="3.2.1",
    )
    spec = application.AnalysisSpec(
        key="example_plugin",
        title="Example plugin",
        category="Plugin tests",
        parser=_parser,
        runner=_runner,
        reporter=_reporter,
        description="Integration test plugin.",
        source="plugin",
        plugin_api_version=PLUGIN_API_VERSION,
        plugin_origin=origin,
    )

    monkeypatch.setattr(application, "_ANALYSES", application._ANALYSES + (spec,))
    monkeypatch.setitem(application.ANALYSIS_SPECS, spec.key, spec)

    run = application.run_analysis("example_plugin", {"value": 3.5})

    assert run.kind == "example_plugin"
    assert run.result["doubled"] == pytest.approx(7.0)
    assert run.markdown.startswith("# Example plugin")
    assert application.analysis_run_matches_input(
        run, "example_plugin", {"value": 3.5}
    )
    provenance = run.diagnostics["application_execution_provenance"]
    assert provenance["analysis_kind"] == "example_plugin"
    assert provenance["implementation"] == {
        "source": "plugin",
        "plugin_api_version": PLUGIN_API_VERSION,
        "entry_point_group": "cleanroomx.analysis_plugins",
        "entry_point_name": "example_plugin",
        "entry_point_value": "cleanroomx_example:registration",
        "distribution_name": "cleanroomx-example",
        "distribution_version": "3.2.1",
    }


def test_plugin_parser_cannot_mutate_submitted_project_payload(monkeypatch):
    def mutating_parser(payload: dict) -> dict:
        payload["value"] = 999.0
        payload["nested"]["changed"] = True
        return {"value": 4.0}

    origin = PluginOrigin(
        entry_point_name="mutating_plugin",
        entry_point_value="cleanroomx_mutating:registration",
        distribution_name="cleanroomx-mutating",
        distribution_version="1.0",
    )
    spec = application.AnalysisSpec(
        key="mutating_plugin",
        title="Mutating plugin",
        category="Plugin tests",
        parser=mutating_parser,
        runner=_runner,
        reporter=None,
        description="Mutation isolation test.",
        source="plugin",
        plugin_api_version=PLUGIN_API_VERSION,
        plugin_origin=origin,
    )
    monkeypatch.setattr(application, "_ANALYSES", application._ANALYSES + (spec,))
    monkeypatch.setitem(application.ANALYSIS_SPECS, spec.key, spec)
    payload = {"value": 2.0, "nested": {"changed": False}}

    with pytest.raises(
        application.AnalysisInputMutationError,
        match="mutated its submitted analysis input",
    ):
        application.run_analysis("mutating_plugin", payload)

    assert payload == {"value": 2.0, "nested": {"changed": False}}


def test_plugin_reporter_cannot_mutate_normalized_result(monkeypatch):
    def mutating_reporter(result: dict) -> str:
        result["doubled"] = -1
        return "# Mutating reporter\n"

    origin = PluginOrigin(
        entry_point_name="report_plugin",
        entry_point_value="cleanroomx_report:registration",
        distribution_name="cleanroomx-report",
        distribution_version="1.0",
    )
    spec = application.AnalysisSpec(
        key="report_plugin",
        title="Report plugin",
        category="Plugin tests",
        parser=_parser,
        runner=_runner,
        reporter=mutating_reporter,
        description="Reporter isolation test.",
        source="plugin",
        plugin_api_version=PLUGIN_API_VERSION,
        plugin_origin=origin,
    )
    monkeypatch.setattr(application, "_ANALYSES", application._ANALYSES + (spec,))
    monkeypatch.setitem(application.ANALYSIS_SPECS, spec.key, spec)

    run = application.run_analysis("report_plugin", {"value": 3.0})

    assert run.result["doubled"] == pytest.approx(6.0)


def test_plugin_reporter_must_return_text(monkeypatch):
    origin = PluginOrigin(
        entry_point_name="bad_report_plugin",
        entry_point_value="cleanroomx_bad_report:registration",
        distribution_name="cleanroomx-bad-report",
        distribution_version="1.0",
    )
    spec = application.AnalysisSpec(
        key="bad_report_plugin",
        title="Bad report plugin",
        category="Plugin tests",
        parser=_parser,
        runner=_runner,
        reporter=lambda result: {"not": "markdown"},
        description="Reporter contract test.",
        source="plugin",
        plugin_api_version=PLUGIN_API_VERSION,
        plugin_origin=origin,
    )
    monkeypatch.setattr(application, "_ANALYSES", application._ANALYSES + (spec,))
    monkeypatch.setitem(application.ANALYSIS_SPECS, spec.key, spec)

    with pytest.raises(TypeError, match="reporter must return Markdown text"):
        application.run_analysis("bad_report_plugin", {"value": 3.0})


def test_plugin_analysis_can_be_persisted_when_registered(monkeypatch):
    from cleanroomx.project import project_from_dict

    origin = PluginOrigin(
        entry_point_name="example_plugin",
        entry_point_value="cleanroomx_example:registration",
        distribution_name="cleanroomx-example",
        distribution_version="1.0",
    )
    spec = application.AnalysisSpec(
        key="example_plugin",
        title="Example plugin",
        category="Plugin tests",
        parser=_parser,
        runner=_runner,
        reporter=None,
        description="Integration test plugin.",
        source="plugin",
        plugin_api_version=PLUGIN_API_VERSION,
        plugin_origin=origin,
    )
    monkeypatch.setitem(application.ANALYSIS_SPECS, spec.key, spec)

    project = project_from_dict(
        {
            "schema": "cleanroomx.project",
            "schema_version": 1,
            "project": {"name": "Plugin project", "metadata": {}},
            "analyses": [
                {
                    "id": "plugin-1",
                    "name": "Extension",
                    "kind": "example_plugin",
                    "input": {"value": 2.0},
                }
            ],
            "active_analysis_id": "plugin-1",
        }
    )

    assert project.analyses[0].kind == "example_plugin"


def test_builtin_run_provenance_identifies_builtin_implementation():
    run = application.run_analysis(
        "room_verification",
        {
            "name": "Room",
            "length_m": 5.0,
            "width_m": 4.0,
            "height_m": 3.0,
            "supply_airflow_m3_h": 1200.0,
        },
    )
    implementation = run.diagnostics["application_execution_provenance"][
        "implementation"
    ]
    assert implementation["source"] == "builtin"
    assert implementation["cleanroomx_version"]
