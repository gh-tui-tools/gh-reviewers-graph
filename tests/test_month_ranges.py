# tests/test_month_ranges.py
from conftest import reviewers


def test_standard_range():
    ranges = reviewers.generate_month_ranges("2024-01", "2024-03")
    assert len(ranges) == 3
    assert ranges[0] == ("2024-01", "2024-01-01", "2024-01-31")
    assert ranges[1] == ("2024-02", "2024-02-01", "2024-02-29")  # 2024 is a leap year
    assert ranges[2] == ("2024-03", "2024-03-01", "2024-03-31")


def test_single_month():
    ranges = reviewers.generate_month_ranges("2025-06", "2025-06")
    assert len(ranges) == 1
    assert ranges[0] == ("2025-06", "2025-06-01", "2025-06-30")


def test_leap_year_february():
    ranges = reviewers.generate_month_ranges("2024-02", "2024-02")
    assert ranges[0] == ("2024-02", "2024-02-01", "2024-02-29")


def test_non_leap_year_february():
    ranges = reviewers.generate_month_ranges("2025-02", "2025-02")
    assert ranges[0] == ("2025-02", "2025-02-01", "2025-02-28")


def test_cross_year_boundary():
    ranges = reviewers.generate_month_ranges("2024-11", "2025-02")
    assert len(ranges) == 4
    assert ranges[0][0] == "2024-11"
    assert ranges[1][0] == "2024-12"
    assert ranges[2][0] == "2025-01"
    assert ranges[3][0] == "2025-02"
