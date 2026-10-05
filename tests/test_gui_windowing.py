from __future__ import annotations

from cleanroomx.gui_windowing import WindowFit, fit_window_metrics


def test_fit_window_metrics_preserves_preferred_size_when_it_fits():
    assert fit_window_metrics(1020, 600, 760, 430, 1920, 1080) == WindowFit(
        1020,
        600,
        760,
        430,
    )


def test_fit_window_metrics_caps_large_history_dialog_to_laptop_display():
    assert fit_window_metrics(1460, 800, 1080, 600, 1366, 768) == WindowFit(
        1270,
        672,
        1080,
        600,
    )


def test_fit_window_metrics_caps_minimum_size_on_small_display():
    fitted = fit_window_metrics(1180, 700, 900, 520, 800, 600)

    assert fitted.width == 704
    assert fitted.height == 504
    assert fitted.minimum_width == fitted.width
    assert fitted.minimum_height == fitted.height


def test_fit_window_metrics_handles_zero_margin_deterministically():
    assert fit_window_metrics(1460, 800, 1080, 600, 1366, 768, margin=0) == WindowFit(
        1366,
        768,
        1080,
        600,
    )
