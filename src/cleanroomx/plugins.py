from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
import os
import re
from typing import Any, Callable, Iterable, Mapping


PLUGIN_API_VERSION = 1
PLUGIN_ENTRY_POINT_GROUP = "cleanroomx.analysis_plugins"
PLUGIN_TRUST_MODE_ENV = "CLEANROOMX_PLUGIN_MODE"
PLUGIN_ALLOWLIST_ENV = "CLEANROOMX_PLUGIN_ALLOWLIST"
PLUGIN_TRUST_MODES = frozenset({"trusted", "disabled", "allowlist"})
_PLUGIN_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_DISTRIBUTION_NAME_RE = re.compile(r"[-_.]+")


@dataclass(frozen=True)
class AnalysisPlugin:
    """Versioned contract implemented by trusted installed analysis extensions."""

    api_version: int
    key: str
    title: str
    category: str
    description: str
    parser: Callable[[dict], Any]
    runner: Callable[[Any], Any]
    reporter: Callable[[dict], str] | None = None


@dataclass(frozen=True)
class PluginOrigin:
    entry_point_name: str
    entry_point_value: str
    distribution_name: str | None
    distribution_version: str | None

    def to_dict(self) -> dict:
        return {
            "entry_point_group": PLUGIN_ENTRY_POINT_GROUP,
            "entry_point_name": self.entry_point_name,
            "entry_point_value": self.entry_point_value,
            "distribution_name": self.distribution_name,
            "distribution_version": self.distribution_version,
        }


@dataclass(frozen=True)
class PluginTrustPolicy:
    """Operator-controlled pre-import policy for installed analysis plugins."""

    mode: str
    allowlist: tuple[tuple[str, str | None], ...] = ()
    configuration_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "allowlist": [
                {
                    "distribution_name": name,
                    "distribution_version": version,
                }
                for name, version in self.allowlist
            ],
            "configuration_error": self.configuration_error,
        }

    def denial_reason(self, origin: PluginOrigin) -> str | None:
        if self.configuration_error is not None:
            return (
                "invalid external plugin trust configuration: "
                + self.configuration_error
            )
        if self.mode == "trusted":
            return None
        if self.mode == "disabled":
            return "external plugins are disabled by operator policy"
        if self.mode != "allowlist":
            return f"unsupported external plugin trust mode {self.mode!r}"

        if origin.distribution_name is None:
            return (
                "allowlist mode requires an installed distribution identity "
                "before plugin import"
            )
        distribution_name = _canonical_distribution_name(
            origin.distribution_name,
            "plugin distribution name",
        )
        allowed = dict(self.allowlist)
        if distribution_name not in allowed:
            return (
                f"distribution {distribution_name!r} is not present in the "
                "external plugin allowlist"
            )
        required_version = allowed[distribution_name]
        if required_version is None:
            return None
        if origin.distribution_version is None:
            return (
                f"distribution {distribution_name!r} must expose version "
                f"{required_version!r} before plugin import"
            )
        if origin.distribution_version != required_version:
            return (
                f"distribution {distribution_name!r} version "
                f"{origin.distribution_version!r} does not match required "
                f"version {required_version!r}"
            )
        return None


@dataclass(frozen=True)
class DiscoveredAnalysisPlugin:
    plugin: AnalysisPlugin
    origin: PluginOrigin


@dataclass(frozen=True)
class PluginIssue:
    entry_point_name: str
    entry_point_value: str
    error: str

    def to_dict(self) -> dict:
        return {
            "entry_point_name": self.entry_point_name,
            "entry_point_value": self.entry_point_value,
            "error": self.error,
        }


@dataclass(frozen=True)
class PluginDiscovery:
    plugins: tuple[DiscoveredAnalysisPlugin, ...]
    issues: tuple[PluginIssue, ...]
    policy: PluginTrustPolicy


def _nonempty_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _canonical_distribution_name(value: Any, field_name: str) -> str:
    return _DISTRIBUTION_NAME_RE.sub(
        "-",
        _nonempty_text(value, field_name),
    ).casefold()


def plugin_trust_policy_from_environment(
    environ: Mapping[str, str] | None = None,
) -> PluginTrustPolicy:
    """Parse external-plugin execution policy without importing any plugin."""
    source = os.environ if environ is None else environ
    raw_mode = source.get(PLUGIN_TRUST_MODE_ENV, "trusted")
    if not isinstance(raw_mode, str) or not raw_mode.strip():
        return PluginTrustPolicy(
            mode="invalid",
            configuration_error=(
                f"{PLUGIN_TRUST_MODE_ENV} must be one of: "
                + ", ".join(sorted(PLUGIN_TRUST_MODES))
            ),
        )
    mode = raw_mode.strip().casefold()
    if mode not in PLUGIN_TRUST_MODES:
        return PluginTrustPolicy(
            mode="invalid",
            configuration_error=(
                f"{PLUGIN_TRUST_MODE_ENV}={raw_mode!r} is invalid; expected one of: "
                + ", ".join(sorted(PLUGIN_TRUST_MODES))
            ),
        )
    if mode != "allowlist":
        return PluginTrustPolicy(mode=mode)

    raw_allowlist = source.get(PLUGIN_ALLOWLIST_ENV, "")
    if not isinstance(raw_allowlist, str):
        return PluginTrustPolicy(
            mode="allowlist",
            configuration_error=f"{PLUGIN_ALLOWLIST_ENV} must be text",
        )

    entries: dict[str, str | None] = {}
    for index, raw_entry in enumerate(raw_allowlist.split(",")):
        token = raw_entry.strip()
        if not token:
            continue
        if token.count("==") > 1:
            return PluginTrustPolicy(
                mode="allowlist",
                configuration_error=(
                    f"{PLUGIN_ALLOWLIST_ENV} entry {index + 1} must be "
                    "distribution or distribution==version"
                ),
            )
        if "==" in token:
            raw_name, raw_version = token.split("==", 1)
            version = raw_version.strip()
            if not version:
                return PluginTrustPolicy(
                    mode="allowlist",
                    configuration_error=(
                        f"{PLUGIN_ALLOWLIST_ENV} entry {index + 1} has an "
                        "empty version pin"
                    ),
                )
        else:
            raw_name = token
            version = None
        try:
            name = _canonical_distribution_name(
                raw_name,
                f"{PLUGIN_ALLOWLIST_ENV} entry {index + 1}",
            )
        except ValueError as exc:
            return PluginTrustPolicy(
                mode="allowlist",
                configuration_error=str(exc),
            )
        if name in entries and entries[name] != version:
            return PluginTrustPolicy(
                mode="allowlist",
                configuration_error=(
                    f"{PLUGIN_ALLOWLIST_ENV} contains conflicting rules for "
                    f"distribution {name!r}"
                ),
            )
        entries[name] = version

    return PluginTrustPolicy(
        mode="allowlist",
        allowlist=tuple(sorted(entries.items())),
    )


_UNAVAILABLE_ORIGIN_TEXT = "<unavailable>"


def _safe_diagnostic_text(
    value: Any,
    *,
    fallback: str = _UNAVAILABLE_ORIGIN_TEXT,
) -> str:
    """Best-effort text for diagnostics without letting plugin metadata abort discovery."""
    try:
        return str(value)
    except (Exception, SystemExit):
        return fallback


def _safe_entry_point_text(entry_point: Any, field_name: str) -> str:
    try:
        value = getattr(entry_point, field_name)
    except (Exception, SystemExit):
        return _UNAVAILABLE_ORIGIN_TEXT
    return _safe_diagnostic_text(value)


def _required_entry_point_text(entry_point: Any, field_name: str) -> str:
    try:
        value = getattr(entry_point, field_name)
    except (Exception, SystemExit) as exc:
        raise ValueError(f"entry point {field_name} is unavailable") from exc
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"entry point {field_name} must be a non-empty string")
    return value


def _optional_origin_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _safe_diagnostic_text(value, fallback="")
    return text or None


def _plugin_error_text(exc: BaseException) -> str:
    message = _safe_diagnostic_text(exc, fallback="<unprintable error>")
    return f"{type(exc).__name__}: {message}"


def validate_analysis_plugin(plugin: AnalysisPlugin) -> AnalysisPlugin:
    if not isinstance(plugin, AnalysisPlugin):
        raise TypeError(
            "entry point must expose AnalysisPlugin or a zero-argument factory "
            "returning AnalysisPlugin"
        )
    if type(plugin.api_version) is not int:
        raise TypeError("plugin API version must be an integer")
    if plugin.api_version != PLUGIN_API_VERSION:
        raise ValueError(
            f"unsupported plugin API version {plugin.api_version!r}; "
            f"expected {PLUGIN_API_VERSION}"
        )

    key = _nonempty_text(plugin.key, "plugin key")
    if key != plugin.key:
        raise ValueError(
            "plugin key must not contain leading or trailing whitespace"
        )
    if _PLUGIN_KEY_RE.fullmatch(key) is None:
        raise ValueError(
            "plugin key must match ^[a-z][a-z0-9_]*$ for stable project identity"
        )
    title = _nonempty_text(plugin.title, "plugin title")
    category = _nonempty_text(plugin.category, "plugin category")
    description = _nonempty_text(plugin.description, "plugin description")
    if not callable(plugin.parser):
        raise TypeError("plugin parser must be callable")
    if not callable(plugin.runner):
        raise TypeError("plugin runner must be callable")
    if plugin.reporter is not None and not callable(plugin.reporter):
        raise TypeError("plugin reporter must be callable when provided")

    return AnalysisPlugin(
        api_version=plugin.api_version,
        key=key,
        title=title,
        category=category,
        description=description,
        parser=plugin.parser,
        runner=plugin.runner,
        reporter=plugin.reporter,
    )


def _origin(entry_point: Any) -> PluginOrigin:
    entry_point_name = _required_entry_point_text(entry_point, "name")
    entry_point_value = _required_entry_point_text(entry_point, "value")

    try:
        dist = getattr(entry_point, "dist", None)
    except (Exception, SystemExit):
        dist = None

    distribution_name = None
    distribution_version = None
    if dist is not None:
        try:
            distribution_name = getattr(dist, "name", None)
        except (Exception, SystemExit):
            distribution_name = None
        if distribution_name is None:
            try:
                metadata_record = getattr(dist, "metadata")
                distribution_name = metadata_record.get("Name")
            except (Exception, SystemExit):
                distribution_name = None
        try:
            distribution_version = getattr(dist, "version", None)
        except (Exception, SystemExit):
            distribution_version = None

    return PluginOrigin(
        entry_point_name=entry_point_name,
        entry_point_value=entry_point_value,
        distribution_name=_optional_origin_text(distribution_name),
        distribution_version=_optional_origin_text(distribution_version),
    )


def _installed_entry_points() -> tuple[Any, ...]:
    discovered = metadata.entry_points()
    if hasattr(discovered, "select"):
        return tuple(discovered.select(group=PLUGIN_ENTRY_POINT_GROUP))
    return tuple(discovered.get(PLUGIN_ENTRY_POINT_GROUP, ()))


def _load_registration(entry_point: Any) -> AnalysisPlugin:
    loaded = entry_point.load()
    if isinstance(loaded, AnalysisPlugin):
        return loaded
    if callable(loaded):
        loaded = loaded()
    return validate_analysis_plugin(loaded)


def discover_analysis_plugins(
    builtin_keys: Iterable[str],
    *,
    entry_points: Iterable[Any] | None = None,
    trust_policy: PluginTrustPolicy | None = None,
) -> PluginDiscovery:
    """Discover valid analysis plugins without allowing registry shadowing.

    Discovery is deterministic. A malformed/incompatible plugin is isolated as
    an issue. Built-in keys always win, and duplicate plugin keys disable every
    contender for that key instead of selecting one by environment ordering.
    """
    builtins = frozenset(str(key) for key in builtin_keys)
    policy = trust_policy or plugin_trust_policy_from_environment()
    points = tuple(entry_points) if entry_points is not None else _installed_entry_points()
    points = tuple(
        sorted(
            points,
            key=lambda item: (
                _safe_entry_point_text(item, "name"),
                _safe_entry_point_text(item, "value"),
            ),
        )
    )

    candidates: list[DiscoveredAnalysisPlugin] = []
    issues: list[PluginIssue] = []
    for point in points:
        issue_name = _safe_entry_point_text(point, "name")
        issue_value = _safe_entry_point_text(point, "value")
        try:
            origin = _origin(point)
            denial_reason = policy.denial_reason(origin)
            if denial_reason is not None:
                issues.append(
                    PluginIssue(
                        entry_point_name=issue_name,
                        entry_point_value=issue_value,
                        error="PluginTrustPolicy: " + denial_reason,
                    )
                )
                continue
            plugin = validate_analysis_plugin(_load_registration(point))
        except (Exception, SystemExit) as exc:
            issues.append(
                PluginIssue(
                    entry_point_name=issue_name,
                    entry_point_value=issue_value,
                    error=_plugin_error_text(exc),
                )
            )
            continue
        candidates.append(DiscoveredAnalysisPlugin(plugin=plugin, origin=origin))

    by_key: dict[str, list[DiscoveredAnalysisPlugin]] = {}
    for item in candidates:
        by_key.setdefault(item.plugin.key, []).append(item)

    accepted: list[DiscoveredAnalysisPlugin] = []
    for key in sorted(by_key):
        group = by_key[key]
        if key in builtins:
            for item in group:
                issues.append(
                    PluginIssue(
                        entry_point_name=item.origin.entry_point_name,
                        entry_point_value=item.origin.entry_point_value,
                        error=f"plugin analysis key {key!r} collides with a built-in analysis",
                    )
                )
            continue
        if len(group) != 1:
            for item in group:
                issues.append(
                    PluginIssue(
                        entry_point_name=item.origin.entry_point_name,
                        entry_point_value=item.origin.entry_point_value,
                        error=f"duplicate plugin analysis key {key!r}; all contenders disabled",
                    )
                )
            continue
        accepted.append(group[0])

    accepted.sort(key=lambda item: item.plugin.key)
    issues.sort(
        key=lambda item: (
            item.entry_point_name,
            item.entry_point_value,
            item.error,
        )
    )
    return PluginDiscovery(
        plugins=tuple(accepted),
        issues=tuple(issues),
        policy=policy,
    )
