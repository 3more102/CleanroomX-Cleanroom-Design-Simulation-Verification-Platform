from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


PLUGIN_API_VERSION = 1

Parser = Callable[[dict], Any]
Runner = Callable[[Any], Any]
Reporter = Callable[[dict], str]


@dataclass(frozen=True)
class PluginAnalysisSpec:
    """One trusted external analysis workflow exposed to CleanroomX."""

    key: str
    title: str
    category: str
    parser: Parser
    runner: Runner
    reporter: Reporter | None
    description: str


@dataclass(frozen=True)
class AnalysisPlugin:
    """Versioned descriptor returned by a cleanroomx.analysis_plugins entry point."""

    name: str
    version: str
    analyses: tuple[PluginAnalysisSpec, ...]
    api_version: int = PLUGIN_API_VERSION
