"""Sampling rate tracking, jitter calculation, and verification for sensor streams.

Provides real-time sliding-window frequency estimation (Hz) and whole-session
summary verification to validate that sensors delivered data at configured rates.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass
class StreamAccumulator:
    """Session-level accumulator for tracking stream sample counts and time spans."""

    samples: int = 0
    first_ts: float = 0.0
    last_ts: float = 0.0

    def add(self, count: int, timestamp: float | None = None) -> None:
        now = time.time() if timestamp is None else timestamp
        if self.samples == 0:
            self.first_ts = now
        self.samples += count
        self.last_ts = now

    @property
    def duration(self) -> float:
        return max(0.0, self.last_ts - self.first_ts)

    @property
    def average_hz(self) -> float:
        dur = self.duration
        return self.samples / dur if dur > 0.0 else 0.0


@dataclass
class RateVerificationResult:
    """Result of comparing configured vs observed sample rates for a stream."""

    stream: str
    configured_hz: int | None
    observed_hz: float
    samples: int
    duration_s: float
    is_match: bool
    relative_error_pct: float


class RateTracker:
    """Tracks instantaneous and cumulative sampling frequencies across multiple streams."""

    def __init__(self, sliding_window_s: float = 1.5) -> None:
        self.sliding_window_s = sliding_window_s
        self.accumulators: dict[str, StreamAccumulator] = {}
        self.history: dict[str, deque[tuple[float, int]]] = {}

    def track(
        self, stream: str, sample_count: int, timestamp: float | None = None
    ) -> None:
        """Register a new batch of samples for a given stream."""
        now = time.time() if timestamp is None else timestamp
        if stream not in self.accumulators:
            self.accumulators[stream] = StreamAccumulator()
        self.accumulators[stream].add(sample_count, now)

        if stream not in self.history:
            self.history[stream] = deque(maxlen=40)
        self.history[stream].append((now, sample_count))

    def get_instantaneous_hz(self, stream: str, now: float | None = None) -> float:
        """Compute instantaneous frequency from recent samples within the sliding window."""
        curr_time = time.time() if now is None else now
        ts_list = self.history.get(stream)
        if not ts_list:
            return 0.0

        recent = [
            item for item in ts_list if curr_time - item[0] <= self.sliding_window_s
        ]
        if not recent:
            return 0.0

        total_samples = sum(item[1] for item in recent)
        time_span = curr_time - recent[0][0]
        return total_samples / time_span if time_span > 0.1 else 0.0

    def get_session_hz(self, stream: str) -> float:
        """Get the full session average frequency in Hz."""
        acc = self.accumulators.get(stream)
        return acc.average_hz if acc else 0.0

    def verify_all(
        self,
        configured: dict[str, int],
        tolerance_pct: float = 0.05,
        extra_streams: Sequence[str] | None = None,
    ) -> list[RateVerificationResult]:
        """Compare all configured streams against observed session rates."""
        results = []
        for name, cfg_rate in configured.items():
            acc = self.accumulators.get(name, StreamAccumulator())
            actual = acc.average_hz
            err = (abs(actual - cfg_rate) / max(cfg_rate, 1)) if cfg_rate > 0 else 0.0
            is_match = err <= tolerance_pct
            results.append(
                RateVerificationResult(
                    stream=name,
                    configured_hz=cfg_rate,
                    observed_hz=actual,
                    samples=acc.samples,
                    duration_s=acc.duration,
                    is_match=is_match,
                    relative_error_pct=err * 100.0,
                )
            )

        for name in extra_streams or []:
            if name not in configured:
                acc = self.accumulators.get(name, StreamAccumulator())
                results.append(
                    RateVerificationResult(
                        stream=name,
                        configured_hz=None,
                        observed_hz=acc.average_hz,
                        samples=acc.samples,
                        duration_s=acc.duration,
                        is_match=True,
                        relative_error_pct=0.0,
                    )
                )
        return results


def update_hz_for_state(
    state: dict[str, Any],
    *streams: tuple[str, deque[tuple[float, int]]],
    now: float | None = None,
) -> None:
    """Compute observed sample rates and update the state dictionary.

    Backward compatibility helper for dashboard render loops.
    """
    curr_time = time.time() if now is None else now
    for prefix, ts_list in streams:
        recent = [item for item in ts_list if curr_time - item[0] <= 1.5]
        if not recent:
            state[f"{prefix}_hz"] = 0.0
            continue
        total_samples = sum(item[1] for item in recent)
        time_span = curr_time - recent[0][0]
        state[f"{prefix}_hz"] = total_samples / time_span if time_span > 0.1 else 0.0


def compute_session_hz(state: dict[str, Any], stream: str) -> float:
    """Compute average Hz over the full session from state accumulators."""
    acc = state.get("_session_streams", {}).get(stream)
    if not acc or acc["last_ts"] <= acc["first_ts"]:
        return 0.0
    return acc["samples"] / (acc["last_ts"] - acc["first_ts"])


def print_hz_summary(
    configured: dict[str, int],
    state: dict[str, Any],
    *,
    extra_streams: Sequence[str] | None = None,
) -> None:
    """Print a session-end Hz summary table comparing configured vs actual rates."""
    print("\n" + "=" * 56)
    print("  SESSION HZ VERIFICATION")
    print("=" * 56)
    print(f"  {'Stream':<8} {'Configured':>10} {'Observed':>10} {'Match':>8}")
    print("-" * 56)
    for name, cfg_rate in configured.items():
        actual = compute_session_hz(state, name)
        match = "OK" if abs(actual - cfg_rate) / max(cfg_rate, 1) < 0.05 else "X"
        print(f"  {name:<8} {cfg_rate:>8} Hz {actual:>8.2f} Hz {match:>8}")
    for name in extra_streams or []:
        actual = compute_session_hz(state, name)
        print(f"  {name:<8} {'—':>10} {actual:>8.2f} Hz {'—':>8}")
    print("=" * 56 + "\n")
