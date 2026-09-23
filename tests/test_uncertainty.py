import pytest

from cleanroomx.uncertainty import measurement_interval, upper_limit_decision


def test_absolute_uncertainty_interval() -> None:
    result = measurement_interval(90, uncertainty_abs=5, floor=0)

    assert result["lower_bound"] == pytest.approx(85)
    assert result["upper_bound"] == pytest.approx(95)
    assert result["uncertainty_abs"] == pytest.approx(5)


def test_percentage_uncertainty_interval() -> None:
    result = measurement_interval(200, uncertainty_percent=10)

    assert result["lower_bound"] == pytest.approx(180)
    assert result["upper_bound"] == pytest.approx(220)
    assert result["uncertainty_abs"] == pytest.approx(20)


def test_upper_limit_decision_reports_indeterminate_overlap() -> None:
    result = upper_limit_decision(95, 100, uncertainty_abs=10, floor=0)

    assert result["status"] == "indeterminate"


def test_upper_limit_decision_passes_only_when_full_interval_is_below_limit() -> None:
    assert upper_limit_decision(80, 100, uncertainty_abs=10)["status"] == "pass"
    assert upper_limit_decision(120, 100, uncertainty_abs=10)["status"] == "fail"


def test_uncertainty_modes_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="either absolute uncertainty"):
        measurement_interval(100, uncertainty_abs=5, uncertainty_percent=5)
