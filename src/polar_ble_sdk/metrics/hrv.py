"""Physiological signal metrics and Heart Rate Variability (HRV) calculations.

This module provides standard time-domain HRV indices calculated from successive
normal-to-normal (NN) or inter-beat intervals (RR/PPI).

Physiological Reference:
    - Task Force of the European Society of Cardiology & North American Society
      of Pacing and Electrophysiology (1996). Heart rate variability: standards
      of measurement, physiological interpretation, and clinical use.

Artifact handling: intervals are validated with a physiological range check and
a local-median check (an interval deviating > 20 % from the median of its
neighbours is an ectopic beat or a missed/extra detection). Invalid intervals
are *excluded*, never interpolated or split, and successive differences are
only taken between two intervals that are adjacent in the original series and
both valid, so a removed beat never produces a difference between beats that
were not consecutive. ``None`` (or <= 0) in the input marks a known gap.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

RR_MIN_MS = 300.0  # 200 BPM
RR_MAX_MS = 2000.0  # 30 BPM
LOCAL_DEVIATION = 0.20
LOCAL_HALF_WINDOW = 5


def rr_valid_mask(rr_list: Sequence[float | int | None]) -> list[bool]:
    """Per-interval validity: in range and within 20 % of the local median.

    The local median uses up to ``LOCAL_HALF_WINDOW`` in-range neighbours on
    each side (not the interval itself); with fewer than 3 neighbours only the
    range check applies.
    """
    vals = [
        float(v) if v is not None and RR_MIN_MS <= v <= RR_MAX_MS else None
        for v in rr_list
    ]
    mask = []
    for i, v in enumerate(vals):
        if v is None:
            mask.append(False)
            continue
        lo, hi = max(0, i - LOCAL_HALF_WINDOW), i + LOCAL_HALF_WINDOW + 1
        neigh = [n for n in vals[lo:i] + vals[i + 1 : hi] if n is not None]
        if len(neigh) >= 3:
            med = statistics.median(neigh)
            mask.append(abs(v - med) <= LOCAL_DEVIATION * med)
        else:
            mask.append(True)
    return mask


def _valid_values(rr_list: Sequence[float | int | None]) -> list[float]:
    mask = rr_valid_mask(rr_list)
    return [float(v) for v, ok in zip(rr_list, mask, strict=True) if ok and v]


def successive_differences(rr_list: Sequence[float | int | None]) -> list[float]:
    """Differences between adjacent intervals that are both valid."""
    mask = rr_valid_mask(rr_list)
    return [
        float(rr_list[i + 1]) - float(rr_list[i])  # type: ignore[arg-type]
        for i in range(len(rr_list) - 1)
        if mask[i] and mask[i + 1]
    ]


def calculate_rmssd(rr_list: Sequence[float | int | None]) -> float:
    """Root Mean Square of Successive Differences (RMSSD) in milliseconds.

    RMSSD reflects beat-to-beat variance in heart rate and is the primary
    time-domain estimate of vagally mediated HRV.

    Formula (over the M valid adjacent pairs):
        .. math::
            \\text{RMSSD} = \\sqrt{ \\frac{1}{M} \\sum (RR_{i+1} - RR_i)^2 }

    Returns NaN if there is no valid adjacent pair.
    """
    diffs = successive_differences(rr_list)
    if not diffs:
        return float("nan")
    return float(math.sqrt(sum(d * d for d in diffs) / len(diffs)))


def calculate_sdnn(rr_list: Sequence[float | int | None]) -> float:
    """Standard deviation of the valid NN intervals (SDNN) in milliseconds.

    SDNN reflects all cyclic components of variability in the recording period.
    Returns NaN with fewer than 2 valid intervals.
    """
    vals = _valid_values(rr_list)
    if len(vals) < 2:
        return float("nan")
    return statistics.stdev(vals)


def calculate_pnn50(rr_list: Sequence[float | int | None]) -> float:
    """Percentage of valid successive differences larger than 50 ms (pNN50).

    Returns NaN if there is no valid adjacent pair.
    """
    diffs = successive_differences(rr_list)
    if not diffs:
        return float("nan")
    return float(sum(1 for d in diffs if abs(d) > 50.0) / len(diffs) * 100.0)
