from itertools import product
from decimal import Decimal
import pytest
from app.grading.bands import compute_overall
from app.grading.schemas import Scores, CRITERIA
from app.grading.task2 import overall_band
from src.data.tiering import compute_ielts_overall


def test_exhaustive_half_band_grid():
    for units in product(range(19), repeat=4):
        values = tuple(u / 2 for u in units)
        expected = ((sum(units) + 1) // 4) / 2
        assert compute_overall(values) == expected
        assert compute_ielts_overall(*values) == expected
        assert overall_band(Scores(**dict(zip(CRITERIA, values)))) == expected


@pytest.mark.parametrize('mean,expected', [('7.875',8),('7.75',7.5),('7.625',7.5),('7.5',7.5),('7.375',7.5),('7.25',7)])
def test_exact_decimal_rounding(mean, expected):
    assert compute_overall([Decimal(mean)] * 4) == expected


@pytest.mark.parametrize('values', [[1,2,3], [1,2,3,4,5], [float('nan'),6,6,6], [float('inf'),6,6,6], [-.5,6,6,6]])
def test_invalid_inputs(values):
    with pytest.raises(ValueError):
        compute_overall(values)


def test_policy_marker_and_benchmark_cache_distinguish_old_rounding():
    from app.grading.bands import OVERALL_POLICY
    from app.grading.schemas import GradeResult
    from benchmark.run import make_metadata
    assert OVERALL_POLICY == 'half_band_threshold_0375_v1'
    assert GradeResult.model_fields['overall_policy'].default == OVERALL_POLICY
    metadata = make_metadata('fixture', 'dev', 1, 'offline-model', 'hash', {}, experiment='A0')
    assert metadata['overall_policy'] == OVERALL_POLICY


@pytest.mark.parametrize('lower', range(18))
def test_every_upper_eighth_boundary(lower):
    base = Decimal(lower) / 2
    assert compute_overall([base + Decimal('0.374999999')] * 4) == float(base)
    assert compute_overall([base + Decimal('0.375')] * 4) == float(base + Decimal('.5'))
