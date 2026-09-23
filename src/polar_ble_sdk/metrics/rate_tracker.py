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

# A stream counts as delivering its configured rate within this relative error.
RATE_TOLERANCE = 0.05


@dataclass
class StreamAccumulator:
    """Session-level accumulator for tracking stream sample counts and time spans."""

    samples: int = 0
    first_count: int = 0
    first_ts: float = 0.0
    last_ts: float = 0.0
    _has_started: bool = False

    def add(self, count: int, timestamp: float | None = None) -> None:
        now = time.time() if timestamp is None else timestamp
        if not self._has_started:
            self.first_ts = now
            self.first_count = count
            self._has_started = True
        self.samples += count
        self.last_ts = now

    @property
    def duration(self) -> float:
        return max(0.0, self.last_ts - self.first_ts)

    @property
    def average_hz(self) -> float:
        # The first batch arrived at first_ts; its samples predate the span.
        dur = self.duration
        return (self.samples - self.first_count) / dur if dur > 0.0 else 0.0


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
        if len(recent) > 1:
            # Samples of the oldest batch predate the span it opens.
            time_span = recent[-1][0] - recent[0][0]
            total_samples -= recent[0][1]
        else:
            time_span = curr_time - recent[0][0]
        return total_samples / time_span if time_span > 0.1 else 0.0

    def get_session_hz(self, stream: str) -> float:
        """Get the full session average frequency in Hz."""
        acc = self.accumulators.get(stream)
        return acc.average_hz if acc else 0.0

    def refresh_state_hz(
        self,
        state: dict[str, Any],
        streams: Sequence[tuple[str, str]],
        now: float | None = None,
    ) -> None:
        """Publish live Hz into a dashboard state dict.

        ``streams`` is a sequence of ``(state_prefix, tracker_key)`` pairs; they
        differ in dual sessions, where one tracker holds ``h10_acc`` and
        ``sense_acc`` but each panel still renders ``acc_hz``.
        """
        curr_time = time.time() if now is None else now
        for prefix, key in streams:
            state[f"{prefix}_hz"] = self.get_instantaneous_hz(key, now=curr_time)

    def verify_all(
        self,
        configured: dict[str, int],
        tolerance_pct: float = RATE_TOLERANCE,
        extra_streams: Sequence[str] | None = None,
    ) -> list[RateVerificationResult]:
        """Compare all configured streams against observed session rates."""
        results = []
        for name, cfg_rate in configured.items():
            acc = self.accumulators.get(name, StreamAccumulator())
            actual = acc.average_hz
            err = (abs(actual - cfg_rate) / max(cfg_rate, 1)) if cfg_rate > 0 else 0.0
            results.append(
                RateVerificationResult(
                    stream=name,
                    configured_hz=cfg_rate,
                    observed_hz=actual,
                    samples=acc.samples,
                    duration_s=acc.duration,
                    is_match=err <= tolerance_pct,
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


def print_hz_summary(
    configured: dict[str, int],
    tracker: RateTracker,
    *,
    extra_streams: Sequence[str] | None = None,
) -> None:
    """Print a session-end Hz summary table comparing configured vs actual rates."""
    print("\n" + "=" * 56)
    print("  SESSION HZ VERIFICATION")
    print("=" * 56)
    print(f"  {'Stream':<12} {'Configured':>10} {'Observed':>10} {'Match':>8}")
    print("-" * 56)
    for r in tracker.verify_all(configured, extra_streams=extra_streams):
        cfg = (
            f"{r.configured_hz:>7} Hz" if r.configured_hz is not None else f"{'—':>10}"
        )
        match = ("OK" if r.is_match else "X") if r.configured_hz is not None else "—"
        print(f"  {r.stream:<12} {cfg} {r.observed_hz:>7.2f} Hz {match:>8}")
    print("=" * 56 + "\n")
