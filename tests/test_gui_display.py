from __future__ import annotations

import math

import pytest

from cleanroomx.gui_display import (
    detect_display_metrics,
    enable_windows_per_monitor_dpi_awareness,
    layout_scale_from_tk_scaling,
    platform_layout_scale,
    scale_window_size,
    unscale_window_size,
)


class _FakeTkInterpreter:
    def __init__(self, value):
        self.value = value

    def call(self, *_args):
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


class _FakeRoot:
    def __init__(self, scaling):
        self.tk = _FakeTkInterpreter(scaling)


@pytest.mark.parametrize(
    ("tk_scaling", "expected"),
    (
        (96.0 / 72.0, 1.0),
        (120.0 / 72.0, 1.25),
        (144.0 / 72.0, 1.5),
        (192.0 / 72.0, 2.0),
    ),
)
def test_layout_scale_from_tk_scaling_matches_windows_ratios(
    tk_scaling: float,
    expected: float,
) -> None:
    assert layout_scale_from_tk_scaling(tk_scaling) == pytest.approx(expected)


@pytest.mark.parametrize("value", (None, "bad", math.nan, math.inf, -math.inf, 0.1, 9.0))
def test_layout_scale_from_tk_scaling_falls_back_for_invalid_values(value) -> None:
    assert layout_scale_from_tk_scaling(value) == pytest.approx(1.0)


def test_detect_display_metrics_uses_tk_scaling() -> None:
    metrics = detect_display_metrics(_FakeRoot(2.0))
    assert metrics.tk_scaling == pytest.approx(2.0)
    assert metrics.effective_dpi == pytest.approx(144.0)
    assert metrics.layout_scale == pytest.approx(1.5)


def test_detect_display_metrics_falls_back_when_tk_query_fails() -> None:
    metrics = detect_display_metrics(_FakeRoot(RuntimeError("no tk")))
    assert metrics.effective_dpi == pytest.approx(96.0)
    assert metrics.layout_scale == pytest.approx(1.0)


def test_platform_layout_scale_is_only_applied_on_windows() -> None:
    root = _FakeRoot(2.0)
    assert platform_layout_scale(root, platform="linux") == pytest.approx(1.0)
    assert platform_layout_scale(root, platform="darwin") == pytest.approx(1.0)
    assert platform_layout_scale(root, platform="win32") == pytest.approx(1.5)


def test_scale_window_size_scales_logical_geometry_and_bounds_to_screen() -> None:
    assert scale_window_size(
        1440,
        900,
        1.25,
        screen_width=3840,
        screen_height=2160,
    ) == (1800, 1125)
    assert scale_window_size(
        1440,
        900,
        1.5,
        screen_width=1920,
        screen_height=1080,
    ) == (1920, 1080)


def test_unscale_window_size_round_trips_common_windows_scaling() -> None:
    for scale in (1.0, 1.25, 1.5, 2.0):
        physical = scale_window_size(
            1440,
            900,
            scale,
            screen_width=5000,
            screen_height=5000,
        )
        assert unscale_window_size(*physical, scale) == (1440, 900)


def test_nonfinite_scale_is_treated_as_one() -> None:
    assert scale_window_size(
        1000,
        700,
        math.nan,
        screen_width=4000,
        screen_height=3000,
    ) == (1000, 700)
    assert unscale_window_size(1000, 700, math.inf) == (1000, 700)


def test_dpi_awareness_is_noop_off_windows() -> None:
    assert enable_windows_per_monitor_dpi_awareness(platform="linux") == "not-windows"
