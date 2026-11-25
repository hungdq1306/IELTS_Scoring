"""FogWrite overall policy; criterion normalization is a separate operation."""
from decimal import Decimal, ROUND_FLOOR

OVERALL_POLICY = "half_band_threshold_0375_v1"


def compute_overall(scores):
    values = [Decimal(str(value)) for value in scores]
    if len(values) != 4 or any(not v.is_finite() or not 0 <= v <= 9 for v in values):
        raise ValueError("Exactly four finite criterion scores in [0, 9] are required")
    # In each half-band interval, .000/.125/.250 stay down; .375 moves up.
    # Adding a quarter half-unit makes the threshold exact without binary floats.
    half_units = (sum(values) / Decimal(2) + Decimal("0.25")).to_integral_value(rounding=ROUND_FLOOR)
    return float(half_units / Decimal(2))
