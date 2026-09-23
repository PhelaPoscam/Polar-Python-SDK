"""Unit tests for the CLI pieces shared by the single- and dual-device dashboards."""

from __future__ import annotations

import argparse
import asyncio
import time
from typing import Any

import pytest

from polar_ble_sdk.cli_common import (
    LOG_TOGGLE,
    add_common_args,
    build_stream_callbacks,
    run_dashboard,
    stream_setting_kwargs,
)
from polar_ble_sdk.metrics.rate_tracker import RateTracker
from polar_ble_sdk.session.state import make_device_state
from polar_ble_sdk.ui.log_panel import LogPanel


class _FakeLive:
    def __init__(self) -> None:
        self.updates = 0

    def update(self, _renderable) -> None:
        self.updates += 1


class _FakeReader:
    def __init__(self, scripted: list[list[str]]) -> None:
        self._scripted = scripted

    def poll_markers(self) -> list[str]:
        return self._scripted.pop(0) if self._scripted else []


class TestStreamSettingKwargs:
    def _args(self, **overrides) -> argparse.Namespace:
        parser = argparse.ArgumentParser()
        add_common_args(parser)
        args = parser.parse_args([])
        for key, value in overrides.items():
            setattr(args, key, value)
        return args

    def test_only_enabled_streams_contribute(self) -> None:
        args = self._args(acc_rate=52, gyro_rate=52, ppg_rate=135)
        assert stream_setting_kwargs(args, ["acc", "ppg"]) == {
            "acc_sample_rate": 52,
            "ppg_sample_rate": 135,
        }

    def test_unset_overrides_are_dropped(self) -> None:
        assert stream_setting_kwargs(self._args(), ["acc", "ecg", "ppg"]) == {}

    def test_common_args_accepts_sdk_mode(self) -> None:
        parser = argparse.ArgumentParser()
        add_common_args(parser)
        args = parser.parse_args(["--sdk-mode"])
        assert args.no_sdk_mode is False


class TestBuildStreamCallbacks:
    def test_frames_reach_state_and_tracker(self) -> None:
        state = make_device_state("test")
        tracker = RateTracker()
        callbacks = build_stream_callbacks(["hr", "acc"], state, tracker)

        callbacks["hr"]((70, [850.0]))
        callbacks["acc"]((1_000_000_000, [(1, 2, 3), (4, 5, 6)]))

        assert state["hr"] == 70
        assert state["acc_count"] == 2
        assert state["acc_raw"] == (4, 5, 6)
        assert tracker.accumulators["acc"].samples == 2

    def test_key_prefix_namespaces_the_tracker(self) -> None:
        """Dual sessions share one tracker, so each device needs its own keys."""
        tracker = RateTracker()
        h10 = build_stream_callbacks(
            ["acc"], make_device_state("h10"), tracker, key_prefix="h10"
        )
        sense = build_stream_callbacks(
            ["acc"], make_device_state("sense"), tracker, key_prefix="sense"
        )

        h10["acc"]((0, [(1, 2, 3)]))
        sense["acc"]((0, [(1, 2, 3), (4, 5, 6)]))

        assert tracker.accumulators["h10_acc"].samples == 1
        assert tracker.accumulators["sense_acc"].samples == 2


class TestRunDashboard:
    def _run(self, reader, duration=None, start=None):
        live: Any = _FakeLive()
        log_panel = LogPanel()
        markers: list[str] = []
        rows: list[str] = []

        asyncio.run(
            run_dashboard(
                live,
                lambda: "panel",
                reader=reader,
                log_panel=log_panel,
                start=start if start is not None else time.time(),
                duration=duration,
                on_marker=markers.append,
                write_rows=rows.append,
            )
        )
        return live, log_panel, markers, rows

    def test_stops_at_duration_and_writes_rows(self) -> None:
        # start 5s in the past: the duration is already spent, so one row is
        # written on the first tick and the loop returns instead of hanging.
        _live, _panel, markers, rows = self._run(
            _FakeReader([["baseline_start"]]),
            duration=1,
            start=time.time() - 5.0,
        )
        assert markers == ["baseline_start"]
        assert rows == ["baseline_start"]

    def test_log_toggle_is_not_a_marker(self) -> None:
        _live, panel, markers, _rows = self._run(
            _FakeReader([[LOG_TOGGLE]]),
            duration=1,
            start=time.time() - 5.0,
        )
        assert markers == []
        assert panel.level == "verbose"

    def test_markers_buffered_across_subsecond_ticks(self) -> None:
        # Multiple markers polled before a 1 Hz row flush are joined and retained
        _live, _panel, markers, rows = self._run(
            _FakeReader([["marker_a", "marker_b"]]),
            duration=1,
            start=time.time() - 5.0,
        )
        assert markers == ["marker_a", "marker_b"]
        assert rows == ["marker_a;marker_b"]

    def test_cancellable_when_no_duration(self) -> None:
        async def _cancel_after_a_few_ticks() -> int:
            live: Any = _FakeLive()
            task = asyncio.create_task(
                run_dashboard(
                    live,
                    lambda: "panel",
                    reader=_FakeReader([]),  # type: ignore[arg-type]
                    log_panel=LogPanel(),
                    start=time.time(),
                )
            )
            await asyncio.sleep(0.35)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            return live.updates

        assert asyncio.run(_cancel_after_a_few_ticks()) >= 2


def test_apply_rate_overrides_follows_flags() -> None:
    import argparse

    from polar_ble_sdk.cli_common import apply_rate_overrides

    args = argparse.Namespace(acc_rate=100, acc_range=None, ecg_rate=None)
    rates = {"h10_acc": 200, "sense_acc": 52, "h10_ecg": 130}
    apply_rate_overrides(rates, args, prefixes=("h10_", "sense_"))
    assert rates == {"h10_acc": 100, "sense_acc": 100, "h10_ecg": 130}


def test_sdk_mode_flags_last_one_wins() -> None:
    import argparse

    from polar_ble_sdk.cli_common import add_common_args

    parser = argparse.ArgumentParser()
    add_common_args(parser)
    assert parser.parse_args([]).no_sdk_mode is False
    assert parser.parse_args(["--no-sdk-mode"]).no_sdk_mode is True
    assert parser.parse_args(["--no-sdk-mode", "--sdk-mode"]).no_sdk_mode is False
