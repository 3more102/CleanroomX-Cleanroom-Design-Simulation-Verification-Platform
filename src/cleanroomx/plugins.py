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
_DISTRIBUTION_NAME_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$"
)
_DISTRIBUTION_CANONICAL_RE = re.compile(r"[-_.]+")
_PLUGIN_TRUST_MODES = frozenset({"trusted", "disabled", "allowlist"})


@dataclass(frozen=True)
class PluginTrustPolicy:
    """Pre-import trust policy for installed external analysis plugins."""

    mode: str
    allowlist: tuple[tuple[str, str | None], ...] = ()
    valid: bool = True
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "valid": self.valid,
            "allowlist": [
                {
                    "distribution_name": distribution_name,
                    "version": version,
                }
                for distribution_name, version in self.allowlist
            ],
            "error": self.error,
        }


def _canonical_distribution_name(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("distribution name must be a non-empty string")
    if value != value.strip():
        raise ValueError("distribution name must not contain surrounding whitespace")
    if _DISTRIBUTION_NAME_RE.fullmatch(value) is None:
        raise ValueError(f"invalid distribution name {value!r}")
    return _DISTRIBUTION_CANONICAL_RE.sub("-", value).lower()


def _parse_plugin_allowlist(raw: str) -> tuple[tuple[str, str | None], ...]:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(
            f"{PLUGIN_ALLOWLIST_ENV} must contain at least one distribution"
        )

    parsed: dict[str, str | None] = {}
    for raw_item in raw.split(","):
        item = raw_item.strip()
        if not item:
            raise ValueError(f"{PLUGIN_ALLOWLIST_ENV} contains an empty entry")
        if item.count("==") > 1:
            raise ValueError(
                f"{PLUGIN_ALLOWLIST_ENV} entry {item!r} contains multiple version separators"
            )
        if "==" in item:
            name_text, version_text = item.split("==", 1)
            name_text = name_text.strip()
            version = version_text.strip()
            if not version:
                raise ValueError(
                    f"{PLUGIN_ALLOWLIST_ENV} entry {item!r} has an empty version pin"
                )
        else:
            name_text = item
            version = None

        canonical = _canonical_distribution_name(name_text)
        if canonical in parsed:
            raise ValueError(
                f"{PLUGIN_ALLOWLIST_ENV} contains duplicate distribution {canonical!r}"
            )
        parsed[canonical] = version

    return tuple(sorted(parsed.items()))


def plugin_trust_policy_from_environment(
    environment: Mapping[str, str] | None = None,
) -> PluginTrustPolicy:
    env = os.environ if environment is None else environment
    raw_mode = env.get(PLUGIN_TRUST_MODE_ENV)
    mode = "trusted" if raw_mode is None else raw_mode.strip().lower()

    if mode not in _PLUGIN_TRUST_MODES:
        return PluginTrustPolicy(
            mode=mode or "<empty>",
            valid=False,
            error=(
                f"{PLUGIN_TRUST_MODE_ENV} must be one of "
                + ", ".join(sorted(_PLUGIN_TRUST_MODES))
            ),
        )

    if mode != "allowlist":
        return PluginTrustPolicy(mode=mode)

    raw_allowlist = env.get(PLUGIN_ALLOWLIST_ENV)
    try:
        allowlist = _parse_plugin_allowlist(
            "" if raw_allowlist is None else raw_allowlist
        )
    except ValueError as exc:
        return PluginTrustPolicy(
            mode=mode,
            valid=False,
            error=str(exc),
        )
    return PluginTrustPolicy(mode=mode, allowlist=allowlist)


def _plugin_trust_denial(
    policy: PluginTrustPolicy,
    origin: "PluginOrigin",
) -> str | None:
    if not policy.valid:
        return f"plugin trust policy invalid: {policy.error}"
    if policy.mode == "trusted":
        return None
    if policy.mode == "disabled":
        return (
            f"external plugin loading is disabled by {PLUGIN_TRUST_MODE_ENV}=disabled"
        )
    if policy.mode != "allowlist":
        return f"unsupported plugin trust mode {policy.mode!r}"

    distribution_name = origin.distribution_name
    if distribution_name is None:
        return (
            "plugin distribution identity is unavailable and cannot satisfy "
            f"{PLUGIN_ALLOWLIST_ENV}"
        )
    try:
        canonical = _canonical_distribution_name(distribution_name)
    except ValueError as exc:
        return f"plugin distribution identity is invalid: {exc}"

    allowed = dict(policy.allowlist)
    if canonical not in allowed:
        return (
            f"distribution {canonical!r} is not allowed by {PLUGIN_ALLOWLIST_ENV}"
        )

    expected_version = allowed[canonical]
    if expected_version is not None:
        if origin.distribution_version is None:
            return (
                f"distribution {canonical!r} version is unavailable; "
                f"{expected_version!r} is required"
            )
        if origin.distribution_version != expected_version:
            return (
                f"distribution {canonical!r} version "
                f"{origin.distribution_version!r} does not match required "
                f"{expected_version!r}"
            )
    return None


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
    trust_policy: PluginTrustPolicy


def _nonempty_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


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
        plugin_trust_policy_from_environment()
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

        if not policy.valid:
            issues.append(
                PluginIssue(
                    entry_point_name=issue_name,
                    entry_point_value=issue_value,
                    error=f"plugin trust policy invalid: {policy.error}",
                )
            )
            continue
        if policy.mode == "disabled":
            issues.append(
                PluginIssue(
                    entry_point_name=issue_name,
                    entry_point_value=issue_value,
                    error=(
                        "external plugin loading is disabled by "
                        f"{PLUGIN_TRUST_MODE_ENV}=disabled"
                    ),
                )
            )
            continue

        try:
            origin = _origin(point)
            trust_denial = _plugin_trust_denial(policy, origin)
            if trust_denial is not None:
                issues.append(
                    PluginIssue(
                        entry_point_name=issue_name,
                        entry_point_value=issue_value,
                        error=trust_denial,
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
        trust_policy=policy,
    )
