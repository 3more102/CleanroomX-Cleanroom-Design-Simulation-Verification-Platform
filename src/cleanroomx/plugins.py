from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
import os
import re
from typing import Any, Callable, Iterable, Mapping


PLUGIN_API_VERSION = 1
PLUGIN_ENTRY_POINT_GROUP = "cleanroomx.analysis_plugins"
_PLUGIN_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PLUGIN_DISTRIBUTION_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$"
)
PLUGIN_MODE_ENV = "CLEANROOMX_PLUGIN_MODE"
PLUGIN_ALLOWLIST_ENV = "CLEANROOMX_PLUGIN_ALLOWLIST"
_PLUGIN_MODES = frozenset({"trusted", "disabled", "allowlist"})


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
class PluginTrustPolicy:
    """Pre-import policy for installed third-party analysis entry points."""

    mode: str = "trusted"
    allowlist: tuple[str, ...] = ()
    configuration_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "allowlist": list(self.allowlist),
            "configuration_error": self.configuration_error,
        }


@dataclass(frozen=True)
class PluginDiscovery:
    plugins: tuple[DiscoveredAnalysisPlugin, ...]
    issues: tuple[PluginIssue, ...]
    trust_policy: PluginTrustPolicy = PluginTrustPolicy()


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


def _canonical_distribution_name(value: str) -> str:
    text = value.strip()
    if not text or _PLUGIN_DISTRIBUTION_RE.fullmatch(text) is None:
        raise ValueError(f"invalid plugin distribution name {value!r}")
    return re.sub(r"[-_.]+", "-", text).lower()


def _normalize_allowlist_spec(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("plugin allowlist entries must be strings")
    text = value.strip()
    if not text:
        raise ValueError("plugin allowlist entries must not be empty")
    if text.count("==") > 1:
        raise ValueError(f"invalid plugin allowlist entry {value!r}")
    if "==" in text:
        name, version = text.split("==", 1)
        name = _canonical_distribution_name(name)
        version = version.strip()
        if not version:
            raise ValueError(f"plugin allowlist version pin is empty in {value!r}")
        return f"{name}=={version}"
    return _canonical_distribution_name(text)


def _validated_plugin_trust_policy(policy: PluginTrustPolicy) -> PluginTrustPolicy:
    if not isinstance(policy, PluginTrustPolicy):
        raise TypeError("plugin trust policy must be PluginTrustPolicy")
    if not isinstance(policy.mode, str):
        raise TypeError("plugin trust policy mode must be a string")
    mode = policy.mode.strip().lower()
    if mode not in _PLUGIN_MODES:
        raise ValueError(
            f"plugin trust policy mode must be one of {sorted(_PLUGIN_MODES)!r}"
        )
    normalized = tuple(
        sorted({_normalize_allowlist_spec(item) for item in policy.allowlist})
    )
    return PluginTrustPolicy(
        mode=mode,
        allowlist=normalized,
        configuration_error=policy.configuration_error,
    )


def plugin_trust_policy_from_environment(
    environ: Mapping[str, str] | None = None,
) -> PluginTrustPolicy:
    """Build a fail-closed external-plugin policy from process environment."""

    source = os.environ if environ is None else environ
    raw_mode = source.get(PLUGIN_MODE_ENV, "trusted")
    raw_allowlist = source.get(PLUGIN_ALLOWLIST_ENV, "")
    try:
        if not isinstance(raw_allowlist, str):
            raise TypeError(f"{PLUGIN_ALLOWLIST_ENV} must be a string")
        if raw_allowlist.strip():
            parts = tuple(raw_allowlist.split(","))
            if any(not part.strip() for part in parts):
                raise ValueError(
                    f"{PLUGIN_ALLOWLIST_ENV} contains an empty allowlist entry"
                )
        else:
            parts = ()
        return _validated_plugin_trust_policy(
            PluginTrustPolicy(mode=raw_mode, allowlist=parts)
        )
    except (TypeError, ValueError) as exc:
        return PluginTrustPolicy(
            mode="disabled",
            allowlist=(),
            configuration_error=(
                "invalid external-plugin trust configuration; plugin loading "
                f"disabled: {exc}"
            ),
        )


def _policy_allows_origin(
    origin: PluginOrigin,
    policy: PluginTrustPolicy,
) -> bool:
    if policy.mode == "trusted":
        return True
    if policy.mode == "disabled":
        return False
    if origin.distribution_name is None:
        return False
    try:
        distribution_name = _canonical_distribution_name(origin.distribution_name)
    except ValueError:
        return False
    for spec in policy.allowlist:
        if "==" in spec:
            allowed_name, allowed_version = spec.split("==", 1)
        else:
            allowed_name, allowed_version = spec, None
        if distribution_name != allowed_name:
            continue
        if allowed_version is None or origin.distribution_version == allowed_version:
            return True
    return False


def _policy_block_reason(
    origin: PluginOrigin | None,
    policy: PluginTrustPolicy,
) -> str:
    if policy.mode == "disabled":
        return "external plugin blocked by disabled plugin trust policy"
    if origin is None or origin.distribution_name is None:
        return (
            "external plugin blocked by allowlist policy because distribution "
            "identity is unavailable"
        )
    identity = origin.distribution_name
    if origin.distribution_version is not None:
        identity += f"=={origin.distribution_version}"
    return f"external plugin distribution {identity!r} is not in the configured allowlist"


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
    policy = _validated_plugin_trust_policy(
        PluginTrustPolicy() if trust_policy is None else trust_policy
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
    if policy.configuration_error is not None:
        issues.append(
            PluginIssue(
                entry_point_name="<policy>",
                entry_point_value=PLUGIN_MODE_ENV,
                error=policy.configuration_error,
            )
        )

    for point in points:
        issue_name = _safe_entry_point_text(point, "name")
        issue_value = _safe_entry_point_text(point, "value")
        if policy.mode == "disabled":
            issues.append(
                PluginIssue(
                    entry_point_name=issue_name,
                    entry_point_value=issue_value,
                    error=_policy_block_reason(None, policy),
                )
            )
            continue

        try:
            origin = _origin(point)
        except (Exception, SystemExit) as exc:
            issues.append(
                PluginIssue(
                    entry_point_name=issue_name,
                    entry_point_value=issue_value,
                    error=_plugin_error_text(exc),
                )
            )
            continue

        if not _policy_allows_origin(origin, policy):
            issues.append(
                PluginIssue(
                    entry_point_name=origin.entry_point_name,
                    entry_point_value=origin.entry_point_value,
                    error=_policy_block_reason(origin, policy),
                )
            )
            continue

        try:
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
