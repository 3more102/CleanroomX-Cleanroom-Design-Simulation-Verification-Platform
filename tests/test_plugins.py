from __future__ import annotations

from dataclasses import dataclass

import pytest

import cleanroomx.application as application
from cleanroomx.plugins import (
    PLUGIN_API_VERSION,
    AnalysisPlugin,
    PluginOrigin,
    discover_analysis_plugins,
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
        load_error: Exception | None = None,
    ) -> None:
        self.name = name
        self.value = value
        self._loaded = loaded
        self.dist = distribution
        self._load_error = load_error

    def load(self):
        if self._load_error is not None:
            raise self._load_error
        return self._loaded


def _parser(payload: dict) -> dict:
    return {"value": float(payload["value"])}


def _runner(model: dict) -> dict:
    return {
        "status": "complete",
        "doubled": model["value"] * 2.0,
    }


def _reporter(result: dict) -> str:
    return f"# Example plugin\n\nDoubled: {result['doubled']}\n"


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
    discovery = discover_analysis_plugins(
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


def test_plugin_discovery_isolates_invalid_and_incompatible_plugins():
    discovery = discover_analysis_plugins(
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


def test_plugin_discovery_disables_builtin_collision():
    discovery = discover_analysis_plugins(
        {"hvac"},
        entry_points=[
            _FakeEntryPoint("collision", "pkg:registration", _plugin("hvac"))
        ],
    )

    assert discovery.plugins == ()
    assert len(discovery.issues) == 1
    assert "collides with a built-in analysis" in discovery.issues[0].error


def test_plugin_discovery_disables_all_duplicate_plugin_keys():
    discovery = discover_analysis_plugins(
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
