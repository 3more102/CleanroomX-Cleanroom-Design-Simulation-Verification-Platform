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
_PLUGIN_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PLUGIN_TRUST_MODES = frozenset({"trusted", "disabled", "allowlist"})


@dataclass(frozen=True)
class PluginTrustRule:
    distribution_name: str
    distribution_version: str | None = None

    def to_dict(self) -> dict:
        return {
            "distribution_name": self.distribution_name,
            "distribution_version": self.distribution_version,
        }


@dataclass(frozen=True)
class PluginTrustPolicy:
    """Effective pre-import policy for installed analysis plugins."""

    mode: str
    configured_mode: str
    allowlist: tuple[PluginTrustRule, ...] = ()
    configuration_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "configured_mode": self.configured_mode,
            "allowlist": [rule.to_dict() for rule in self.allowlist],
            "configuration_error": self.configuration_error,
        }


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


def _nonempty_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _canonical_distribution_name(value: str) -> str:
    text = _nonempty_text(value, "plugin distribution name")
    canonical = re.sub(r"[-_.]+", "-", text).lower()
    if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", canonical) is None:
        raise ValueError(
            "plugin distribution name must contain only ASCII letters, digits, "
            "'.', '_' or '-' separators"
        )
    return canonical


def _parse_plugin_allowlist(value: str) -> tuple[PluginTrustRule, ...]:
    if not isinstance(value, str):
        raise ValueError(f"{PLUGIN_ALLOWLIST_ENV} must be text")
    if not value.strip():
        return ()

    rules: list[PluginTrustRule] = []
    seen: set[str] = set()
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            raise ValueError(f"{PLUGIN_ALLOWLIST_ENV} contains an empty entry")
        if item.count("==") > 1 or ("=" in item and "==" not in item):
            raise ValueError(
                f"{PLUGIN_ALLOWLIST_ENV} entries must be NAME or NAME==VERSION"
            )
        name_text, separator, version_text = item.partition("==")
        if "=" in name_text or "=" in version_text:
            raise ValueError(
                f"{PLUGIN_ALLOWLIST_ENV} entries must be NAME or NAME==VERSION"
            )
        name = _canonical_distribution_name(name_text)
        version = None
        if separator:
            if not version_text or version_text != version_text.strip():
                raise ValueError(
                    f"{PLUGIN_ALLOWLIST_ENV} version pins must be non-empty "
                    "without surrounding whitespace"
                )
            if any(character.isspace() for character in version_text):
                raise ValueError(
                    f"{PLUGIN_ALLOWLIST_ENV} version pins must not contain whitespace"
                )
            version = version_text
        if name in seen:
            raise ValueError(
                f"{PLUGIN_ALLOWLIST_ENV} contains duplicate distribution {name!r}"
            )
        seen.add(name)
        rules.append(
            PluginTrustRule(
                distribution_name=name,
                distribution_version=version,
            )
        )
    rules.sort(key=lambda rule: rule.distribution_name)
    return tuple(rules)


def plugin_trust_policy_from_environment(
    environ: Mapping[str, str] | None = None,
) -> PluginTrustPolicy:
    """Return the effective fail-closed plugin trust policy.

    Invalid mode or allowlist configuration disables all external plugins rather
    than falling back to the permissive trusted mode.
    """
    source = os.environ if environ is None else environ
    raw_mode = source.get(PLUGIN_TRUST_MODE_ENV, "disabled")
    configured_mode = str(raw_mode).strip().lower()
    if configured_mode not in _PLUGIN_TRUST_MODES:
        return PluginTrustPolicy(
            mode="disabled",
            configured_mode=configured_mode,
            configuration_error=(
                f"{PLUGIN_TRUST_MODE_ENV} must be one of "
                + ", ".join(sorted(_PLUGIN_TRUST_MODES))
            ),
        )

    if configured_mode != "allowlist":
        return PluginTrustPolicy(
            mode=configured_mode,
            configured_mode=configured_mode,
        )

    raw_allowlist = source.get(PLUGIN_ALLOWLIST_ENV, "")
    try:
        allowlist = _parse_plugin_allowlist(raw_allowlist)
    except ValueError as exc:
        return PluginTrustPolicy(
            mode="disabled",
            configured_mode=configured_mode,
            configuration_error=str(exc),
        )
    return PluginTrustPolicy(
        mode="allowlist",
        configured_mode=configured_mode,
        allowlist=allowlist,
    )


def _plugin_policy_block_reason(
    origin: "PluginOrigin",
    policy: PluginTrustPolicy,
) -> str | None:
    if policy.configuration_error is not None:
        return f"plugin trust policy configuration error: {policy.configuration_error}"
    if policy.mode == "trusted":
        return None
    if policy.mode == "disabled":
        return "external plugin blocked by plugin trust policy mode 'disabled'"
    if policy.mode != "allowlist":
        return f"external plugin blocked by unsupported trust policy mode {policy.mode!r}"

    if origin.distribution_name is None:
        return (
            "external plugin blocked by allowlist policy because distribution "
            "identity is unavailable"
        )
    try:
        distribution_name = _canonical_distribution_name(origin.distribution_name)
    except ValueError as exc:
        return f"external plugin blocked by allowlist policy: {exc}"

    rule = next(
        (
            item
            for item in policy.allowlist
            if item.distribution_name == distribution_name
        ),
        None,
    )
    if rule is None:
        return (
            f"external plugin distribution {distribution_name!r} is not present "
            "in the configured allowlist"
        )
    if rule.distribution_version is None:
        return None
    if origin.distribution_version is None:
        return (
            f"external plugin distribution {distribution_name!r} is allowlisted "
            f"only at version {rule.distribution_version!r}, but installed version "
            "metadata is unavailable"
        )
    if origin.distribution_version != rule.distribution_version:
        return (
            f"external plugin distribution {distribution_name!r} version "
            f"{origin.distribution_version!r} does not match allowlisted version "
            f"{rule.distribution_version!r}"
        )
    return None


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
    policy = (
        PluginTrustPolicy(mode="trusted", configured_mode="trusted")
        if trust_policy is None
        else trust_policy
    )
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
            block_reason = _plugin_policy_block_reason(origin, policy)
            if block_reason is not None:
                issues.append(
                    PluginIssue(
                        entry_point_name=issue_name,
                        entry_point_value=issue_value,
                        error=block_reason,
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
    return PluginDiscovery(plugins=tuple(accepted), issues=tuple(issues))
