"""Headcount parser on the three header formats Alphabet's earnings releases have used."""
import pytest

from fpa_forecast.earnings_release import parse_headcount

FORMATS = [
    # 2026 style: one header, two years
    ("Quarter Ended September 30, 2025 2026 Google Search & other $ 56,567 $ 63,350 Total TAC $ 14,876 "
     "$ 16,366 Number of employees 190,167 204,757 Segment", "2026-10-28", [("2025Q3", 190167), ("2026Q3", 204757)]),
    # 2019 style: two 'Three Months Ended' headers
    ("Three Months Ended September 30, 2018 Three Months Ended September 30, 2019 Revenues $33,740 $40,499 "
     "Number of employees 94,372 114,096 (1) Q3 2018", "2019-10-28", [("2018Q3", 94372), ("2019Q3", 114096)]),
    # 2018 style: 'quarters ended December 31, 2016 and 2017'
    ("our consolidated financial results for the quarters ended December 31, 2016 and 2017 (in millions) "
     "Effective tax rate 22 % 138 % Number of employees 72,053 80,110 Q4", "2018-02-01",
     [("2016Q4", 72053), ("2017Q4", 80110)]),
]


@pytest.mark.parametrize("text,filed,expected", FORMATS)
def test_parse_headcount_formats(text, filed, expected):
    assert parse_headcount(text, filed) == expected


def test_parse_headcount_rejects_wrong_quarter():
    text, _, _ = FORMATS[0]
    assert parse_headcount(text, "2026-07-22") == []  # a Q2 filing cannot report Q3 as current


def test_parse_headcount_without_row():
    assert parse_headcount("no employee data here", "2026-10-28") == []
