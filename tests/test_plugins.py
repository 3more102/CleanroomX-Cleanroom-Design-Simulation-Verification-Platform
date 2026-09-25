from __future__ import annotations

import copy
from dataclasses import replace

import pytest

import cleanroomx.application as application_module
from cleanroomx.application import (
    analysis_catalog,
    analysis_run_matches_input,
    application_info,
    load_analysis_plugins,
    run_analysis,
    validate_application_registry,
)
from cleanroomx.plugin_api import AnalysisPlugin, PLUGIN_API_VERSION, PluginAnalysisSpec
from cleanroomx.project import (
    PROJECT_SCHEMA,
    PROJECT_SCHEMA_VERSION,
    ProjectFormatError,
    project_from_dict,
)


class FakeEntryPoint:
    def __init__(self, name: str, descriptor: AnalysisPlugin):
        self.name = name
        self.value = f"tests.fake:{name}"
        self._descriptor = descriptor

    def load(self):
        descriptor = self._descriptor
        return lambda: descriptor


@pytest.fixture(autouse=True)
def restore_application_registry():
    analyses = application_module._ANALYSES
    mapping = dict(application_module.ANALYSIS_SPECS)
    discovered = application_module._PLUGINS_DISCOVERED
    report = copy.deepcopy(application_module._PLUGIN_DISCOVERY_REPORT)
    yield
    application_module._ANALYSES = analyses
    application_module.ANALYSIS_SPECS.clear()
    application_module.ANALYSIS_SPECS.update(mapping)
    application_module._PLUGINS_DISCOVERED = discovered
    application_module._PLUGIN_DISCOVERY_REPORT = report


def _plugin(*, version: str = "1.2.3", key: str = "plugin.acme.engineering.double"):
    def parser(payload: dict) -> dict:
        if set(payload) != {"value"}:
            raise ValueError("input must contain exactly value")
        value = float(payload["value"])
        if value < 0:
            raise ValueError("value must be non-negative")
        return {"value": value}

    def runner(model: dict) -> dict:
        return {
            "status": "complete",
            "value": model["value"],
            "doubled": 2.0 * model["value"],
        }

    def reporter(result: dict) -> str:
        return f"# Plugin report\n\nDoubled: {result['doubled']}\n"

    return AnalysisPlugin(
        name="acme.engineering",
        version=version,
        analyses=(
            PluginAnalysisSpec(
                key=key,
                title="ACME double",
                category="Extensions",
                parser=parser,
                runner=runner,
                reporter=reporter,
                description="Deterministic plugin integration test.",
            ),
        ),
    )


def test_valid_plugin_integrates_with_catalog_project_execution_and_provenance():
    report = load_analysis_plugins(
        force=True,
        entry_points_override=[FakeEntryPoint("acme", _plugin())],
    )

    assert report["status"] == "ok"
    assert report["loaded_plugin_count"] == 1
    assert report["loaded_analysis_count"] == 1
    assert report["failure_count"] == 0
    catalog_entry = next(
        item for item in analysis_catalog()
        if item["key"] == "plugin.acme.engineering.double"
    )
    assert catalog_entry["provider"] == "plugin"
    assert catalog_entry["plugin_name"] == "acme.engineering"
    assert catalog_entry["plugin_version"] == "1.2.3"

    project = project_from_dict(
        {
            "schema": PROJECT_SCHEMA,
            "schema_version": PROJECT_SCHEMA_VERSION,
            "project": {"name": "Plugin project"},
            "analyses": [
                {
                    "id": "plugin-1",
                    "name": "Double",
                    "kind": "plugin.acme.engineering.double",
                    "input": {"value": 2.5},
                }
            ],
            "active_analysis_id": "plugin-1",
        }
    )
    assert project.analyses[0].kind == "plugin.acme.engineering.double"

    run = run_analysis("plugin.acme.engineering.double", {"value": 2.5})
    assert run.result["doubled"] == 5.0
    assert "# Plugin report" in run.markdown
    provenance = run.diagnostics["application_execution_provenance"]
    assert provenance["analysis_provider"] == "plugin"
    assert provenance["plugin_identity"] == {
        "name": "acme.engineering",
        "version": "1.2.3",
        "api_version": PLUGIN_API_VERSION,
    }
    assert analysis_run_matches_input(
        run, "plugin.acme.engineering.double", {"value": 2.5}
    ) is True
    assert validate_application_registry()["plugin_analysis_count"] == 1


def test_plugin_version_change_invalidates_cached_run_ownership():
    load_analysis_plugins(
        force=True,
        entry_points_override=[FakeEntryPoint("acme", _plugin(version="1.2.3"))],
    )
    run = run_analysis("plugin.acme.engineering.double", {"value": 3})

    load_analysis_plugins(
        force=True,
        entry_points_override=[FakeEntryPoint("acme", _plugin(version="1.2.4"))],
    )

    assert analysis_run_matches_input(
        run, "plugin.acme.engineering.double", {"value": 3}
    ) is False


def test_incompatible_plugin_is_isolated_without_poisoning_core_registry():
    bad = AnalysisPlugin(
        name="acme.engineering",
        version="9.0",
        api_version=PLUGIN_API_VERSION + 1,
        analyses=_plugin().analyses,
    )
    report = load_analysis_plugins(
        force=True,
        entry_points_override=[FakeEntryPoint("bad-api", bad)],
    )

    assert report["status"] == "degraded"
    assert report["loaded_plugin_count"] == 0
    assert report["failure_count"] == 1
    assert report["failures"][0]["error_type"] == "ValueError"
    assert "incompatible" in report["failures"][0]["message"]
    assert "room_verification" in application_module.ANALYSIS_SPECS
    assert "plugin.acme.engineering.double" not in application_module.ANALYSIS_SPECS
    validation = validate_application_registry()
    assert validation["status"] == "ok"
    assert validation["plugin_analysis_count"] == 0
    info = application_info()
    assert info["plugin_discovery"]["status"] == "degraded"


@pytest.mark.parametrize(
    "key",
    ["room_verification", "plugin.other.vendor.analysis", "Plugin.acme.engineering.bad"],
)
def test_plugin_key_must_stay_in_its_namespaced_provider_boundary(key):
    report = load_analysis_plugins(
        force=True,
        entry_points_override=[FakeEntryPoint("bad-key", _plugin(key=key))],
    )

    assert report["status"] == "degraded"
    assert report["loaded_analysis_count"] == 0
    assert report["failure_count"] == 1
    assert key not in {
        item.key
        for item in application_module._ANALYSES
        if item.provider == "plugin"
    }


def test_plugin_discovery_order_is_deterministic():
    first = _plugin(key="plugin.acme.engineering.first")
    second = AnalysisPlugin(
        name="zeta.engineering",
        version="2.0",
        analyses=(
            PluginAnalysisSpec(
                key="plugin.zeta.engineering.second",
                title="Second",
                category="Extensions",
                parser=lambda payload: payload,
                runner=lambda model: {"status": "complete", "value": model.get("value")},
                reporter=None,
                description="Second deterministic plugin.",
            ),
        ),
    )

    report = load_analysis_plugins(
        force=True,
        entry_points_override=[
            FakeEntryPoint("zeta", second),
            FakeEntryPoint("acme", first),
        ],
    )

    assert [item["entry_point"] for item in report["plugins"]] == ["acme", "zeta"]
    assert [
        item["key"] for item in analysis_catalog() if item["provider"] == "plugin"
    ] == [
        "plugin.acme.engineering.first",
        "plugin.zeta.engineering.second",
    ]


def test_missing_plugin_project_fails_closed_with_actionable_error():
    load_analysis_plugins(force=True, entry_points_override=[])

    with pytest.raises(ProjectFormatError, match="install a compatible plugin"):
        project_from_dict(
            {
                "schema": PROJECT_SCHEMA,
                "schema_version": PROJECT_SCHEMA_VERSION,
                "project": {"name": "Unavailable plugin"},
                "analyses": [
                    {
                        "id": "plugin-1",
                        "name": "Missing",
                        "kind": "plugin.acme.engineering.double",
                        "input": {"value": 1},
                    }
                ],
                "active_analysis_id": "plugin-1",
            }
        )


def test_plugin_registration_is_atomic_when_one_analysis_is_invalid():
    valid = _plugin().analyses[0]
    invalid = replace(
        valid,
        key="plugin.other.invalid",
        title="Invalid sibling",
    )
    descriptor = replace(_plugin(), analyses=(valid, invalid))

    report = load_analysis_plugins(
        force=True,
        entry_points_override=[FakeEntryPoint("atomic", descriptor)],
    )

    assert report["status"] == "degraded"
    assert report["loaded_analysis_count"] == 0
    assert "plugin.acme.engineering.double" not in application_module.ANALYSIS_SPECS


def test_plugin_parser_and_reporter_receive_isolated_snapshots():
    def parser(payload: dict) -> dict:
        payload["mutated_by_parser"] = True
        return {"value": float(payload["value"])}

    def runner(model: dict) -> dict:
        return {"status": "complete", "value": model["value"]}

    def reporter(result: dict) -> str:
        result["mutated_by_reporter"] = True
        return "# Isolated"

    descriptor = AnalysisPlugin(
        name="isolation.engineering",
        version="1.0",
        analyses=(
            PluginAnalysisSpec(
                key="plugin.isolation.engineering.check",
                title="Isolation check",
                category="Extensions",
                parser=parser,
                runner=runner,
                reporter=reporter,
                description="Verify boundary snapshot isolation.",
            ),
        ),
    )
    load_analysis_plugins(
        force=True,
        entry_points_override=[FakeEntryPoint("isolation", descriptor)],
    )
    payload = {"value": 4}

    run = run_analysis("plugin.isolation.engineering.check", payload)

    assert payload == {"value": 4}
    assert run.result == {"status": "complete", "value": 4.0}


def test_plugin_reporter_must_return_text():
    spec = replace(_plugin().analyses[0], reporter=lambda result: {"not": "text"})
    descriptor = replace(_plugin(), analyses=(spec,))
    load_analysis_plugins(
        force=True,
        entry_points_override=[FakeEntryPoint("bad-reporter", descriptor)],
    )

    with pytest.raises(TypeError, match="reporter must return a string"):
        run_analysis("plugin.acme.engineering.double", {"value": 1})
