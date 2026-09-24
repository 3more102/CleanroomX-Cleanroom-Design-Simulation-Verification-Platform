"""Compatibility exports for nonlinear fan/loop uncertainty models."""

from .fan_variable_friction_uncertainty import (
    FanCurveScenario,
    FanVariableFrictionLoopUncertaintyStudy,
)

__all__ = [
    "FanCurveScenario",
    "FanVariableFrictionLoopUncertaintyStudy",
]
