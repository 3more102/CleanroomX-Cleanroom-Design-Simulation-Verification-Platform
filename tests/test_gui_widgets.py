from __future__ import annotations

import math

from cleanroomx.gui_widgets import (
    canonical_status_text,
    format_engineering_measurement,
    format_engineering_number,
)


def test_engineering_number_formatting_is_dense_and_deterministic():
    assert format_engineering_number(1250, precision=0) == "1,250"
    assert format_engineering_number(12.5, precision=1, signed=True) == "+12.5"
    assert format_engineering_number(-0.25, precision=2, signed=True) == "-0.25"


def test_engineering_measurement_formats_units_without_machine_precision():
    assert format_engineering_measurement(1250, "m³/h", precision=0) == "1,250 m³/h"
    assert format_engineering_measurement(12.5, "Pa", precision=1, signed=True) == "+12.5 Pa"
    assert format_engineering_measurement(4.9, "%", precision=1) == "4.9%"


def test_engineering_formatting_rejects_nonfinite_and_non_numeric_values():
    for value in (None, True, "not-a-number", math.inf, -math.inf, math.nan):
        assert format_engineering_number(value) == "—"


def test_canonical_status_text_uses_shared_workstation_vocabulary():
    assert canonical_status_text("passed") == "PASS"
    assert canonical_status_text("error") == "FAIL"
    assert canonical_status_text("not_checked") == "NOT CHECKED"
    assert canonical_status_text("incomplete") == "INCOMPLETE"
    assert canonical_status_text("custom_state") == "CUSTOM STATE"
