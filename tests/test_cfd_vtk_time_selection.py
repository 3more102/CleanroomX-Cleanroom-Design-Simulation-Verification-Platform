import pytest

from cleanroomx.cfd_vtk_time_selection import parse_foam_to_vtk_time_log


def test_v10_foam_to_vtk_log_accepts_only_the_requested_time():
    log = "OpenFOAM Foundation Version: 10\nTime: 100\nWriting VTK files\nEnd\n"

    assert parse_foam_to_vtk_time_log(log, "100") == ["100"]


@pytest.mark.parametrize(
    ("log", "expected_time"),
    [
        ("OpenFOAM\nEnd\n", "100"),
        ("Time: 50\nEnd\n", "100"),
        ("Time: 100\nTime: 150\nEnd\n", "100"),
        ("Time: 100\nEnd\nTime: 100\n", "100"),
        ("Time: 100\n", "100"),
        ("Time: 100\nFOAM FATAL ERROR: failed\nEnd\n", "100"),
    ],
)
def test_v10_foam_to_vtk_log_rejects_missing_wrong_or_incomplete_selection(log, expected_time):
    with pytest.raises(ValueError):
        parse_foam_to_vtk_time_log(log, expected_time)


@pytest.mark.parametrize("expected_time", ["", "latestTime", "nan", "inf", "-1"])
def test_v10_foam_to_vtk_log_requires_one_finite_numeric_time_name(expected_time):
    with pytest.raises(ValueError):
        parse_foam_to_vtk_time_log("Time: 100\nEnd\n", expected_time)
