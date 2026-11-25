from itertools import product
from decimal import Decimal
import pytest
from app.grading.bands import floor_overall
from app.grading.schemas import Scores, CRITERIA
from app.grading.task2 import overall_band
from src.data.tiering import compute_ielts_overall


def test_exhaustive_half_band_grid():
    for units in product(range(19), repeat=4):
        values = tuple(u / 2 for u in units)
        expected = (sum(units) // 4) / 2
        assert floor_overall(values) == expected
        assert compute_ielts_overall(*values) == expected
        assert overall_band(Scores(**dict(zip(CRITERIA, values)))) == expected


@pytest.mark.parametrize('mean,expected', [('7.875',7.5),('7.75',7.5),('7.625',7.5),('7.5',7.5),('7.375',7),('7.25',7)])
def test_exact_decimal_floor(mean, expected):
    assert floor_overall([Decimal(mean)] * 4) == expected


@pytest.mark.parametrize('values', [[1,2,3], [1,2,3,4,5], [float('nan'),6,6,6], [float('inf'),6,6,6], [-.5,6,6,6]])
def test_invalid_inputs(values):
    with pytest.raises(ValueError):
        floor_overall(values)
