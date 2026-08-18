"""Physiological signal metrics and Heart Rate Variability (HRV) calculations.

This module provides standard time-domain HRV indices calculated from successive
normal-to-normal (NN) or inter-beat intervals (RR/PPI).

Physiological Reference:
    - Task Force of the European Society of Cardiology & North American Society
      of Pacing and Electrophysiology (1996). Heart rate variability: standards
      of measurement, physiological interpretation, and clinical use.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def calculate_rmssd(rr_list: Sequence[float | int | None]) -> float:
    """Calculate the Root Mean Square of Successive Differences (RMSSD) in milliseconds.

    RMSSD reflects the beat-to-beat variance in heart rate and is the primary
    time-domain measure used to estimate vagally mediated changes in HRV.

    Formula:
        .. math::
            \\text{RMSSD} = \\sqrt{ \\frac{1}{N-1} \\sum_{i=1}^{N-1} (RR_{i+1} - RR_i)^2 }

    Args:
        rr_list: A sequence of RR or PPI interval values in milliseconds. Non-positive
            and None values are automatically filtered out.

    Returns:
        float: The calculated RMSSD in milliseconds, or 0.0 if fewer than 2 valid
            intervals are provided.
    """
    vals = [float(rr) for rr in rr_list if rr is not None and rr > 0]
    if len(vals) < 2:
        return 0.0
    diffs = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
    return float(math.sqrt(sum(d * d for d in diffs) / len(diffs)))


def calculate_sdnn(rr_list: Sequence[float | int | None]) -> float:
    """Calculate the Standard Deviation of NN/RR intervals (SDNN) in milliseconds.

    SDNN reflects all the cyclic components responsible for variability in the
    recording period (both sympathetic and parasympathetic influences).

    Args:
        rr_list: A sequence of RR or PPI interval values in milliseconds.

    Returns:
        float: The calculated SDNN in milliseconds, or 0.0 if fewer than 2 valid intervals.
    """
    vals = [float(rr) for rr in rr_list if rr is not None and rr > 0]
    n = len(vals)
    if n < 2:
        return 0.0
    mean = sum(vals) / n
    variance = sum((x - mean) ** 2 for x in vals) / (n - 1)
    return float(math.sqrt(variance))


def calculate_pnn50(rr_list: Sequence[float | int | None]) -> float:
    """Calculate the percentage of successive RR intervals differing by > 50 ms (pNN50).

    Args:
        rr_list: A sequence of RR or PPI interval values in milliseconds.

    Returns:
        float: The pNN50 percentage (0.0 to 100.0), or 0.0 if fewer than 2 valid intervals.
    """
    vals = [float(rr) for rr in rr_list if rr is not None and rr > 0]
    if len(vals) < 2:
        return 0.0
    diffs = [abs(vals[i + 1] - vals[i]) for i in range(len(vals) - 1)]
    nn50 = sum(1 for d in diffs if d > 50.0)
    return float((nn50 / len(diffs)) * 100.0)
