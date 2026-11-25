"""FogWrite overall policy; criterion normalization is a separate operation."""
from decimal import Decimal, ROUND_FLOOR

OVERALL_POLICY = "floor_half_v1"


def floor_overall(scores):
    values = [Decimal(str(value)) for value in scores]
    if len(values) != 4 or any(not v.is_finite() or not 0 <= v <= 9 for v in values):
        raise ValueError("Exactly four finite criterion scores in [0, 9] are required")
    half_units = (sum(values) / Decimal(2)).to_integral_value(rounding=ROUND_FLOOR)
    return float(half_units / Decimal(2))
