"""Live waveform viewer for Nuanic stress payload and raw EDA streams."""

import asyncio
import struct
import threading
from collections import deque

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

from .connector import NuanicConnector


class WaveformState:
    """Thread-safe container for live waveform buffers."""

    def __init__(self, history_points: int = 600):
        self.lock = threading.Lock()

        self.sample_index = 0
        self.stress_index = deque(maxlen=history_points)
        self.stress_wave = deque(maxlen=history_points)

        self.raw_index = deque(maxlen=history_points)
        self.raw_wave = deque(maxlen=history_points)

        self.latest_stress_percent = None
        self.stress_packets = 0
        self.raw_packets = 0


class NuanicWaveformViewer:
    """Connects to ring, subscribes to streams, and exposes data for plotting."""

    def __init__(self, ring_addr: str | None = None):
        self.connector = NuanicConnector(target_address=ring_addr)
        self.state = WaveformState()
        self._running = False

    def _stress_callback(self, sender, data):
        if len(data) < 15:
            return

        stress_raw = data[14]
        stress_percent = (stress_raw / 255) * 100

        # Treat bytes 15-91 as waveform bytes and scale to 0..100 for display.
        payload = data[15:92] if len(data) >= 92 else data[15:]
        if not payload:
            return

        with self.state.lock:
            self.state.latest_stress_percent = stress_percent
            self.state.stress_packets += 1

            for byte_val in payload:
                self.state.sample_index += 1
                self.state.stress_index.append(self.state.sample_index)
                self.state.stress_wave.append((byte_val / 255.0) * 100.0)

    def _raw_eda_callback(self, sender, data):
        if len(data) < 2:
            return

        with self.state.lock:
            self.state.raw_packets += 1

            # Decode as little-endian int16 sample stream.
            for i in range(0, len(data) - 1, 2):
                val = struct.unpack("<h", data[i : i + 2])[0]
                self.state.sample_index += 1
                self.state.raw_index.append(self.state.sample_index)
                self.state.raw_wave.append(val)

    async def connect_and_subscribe(self) -> bool:
        if not await self.connector.connect():
            return False

        stress_ok = await self.connector.subscribe_to_stress(self._stress_callback)
        raw_ok = await self.connector.subscribe_to_raw_eda(self._raw_eda_callback)

        if not (stress_ok and raw_ok):
            await self.connector.unsubscribe_from_stress()
            await self.connector.unsubscribe_from_raw_eda()
            await self.connector.disconnect()
            return False

        self._running = True
        return True

    async def run_until_stopped(self):
        try:
            while self._running:
                await asyncio.sleep(0.1)
        finally:
            await self.stop()

    async def stop(self):
        self._running = False
        await self.connector.unsubscribe_from_stress()
        await self.connector.unsubscribe_from_raw_eda()
        await self.connector.disconnect()


def run_plot(viewer: NuanicWaveformViewer, window_seconds: int, refresh_ms: int):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=False)
    fig.suptitle("Nuanic Live Waveform Viewer")

    (line1,) = ax1.plot([], [], lw=1.5)
    (line2,) = ax2.plot([], [], lw=1.2, color="tab:orange")

    ax1.set_ylabel("Stress Payload\nScaled (0-100)")
    ax2.set_ylabel("Raw EDA\nint16")
    ax2.set_xlabel("Sample Index")

    status_text = fig.text(0.02, 0.96, "Connecting...", fontsize=10)

    # Rough point budget for visible x window (adapts if payload density changes).
    max_points = max(200, window_seconds * 100)

    def update(_frame):
        with viewer.state.lock:
            x1 = list(viewer.state.stress_index)[-max_points:]
            y1 = list(viewer.state.stress_wave)[-max_points:]
            x2 = list(viewer.state.raw_index)[-max_points:]
            y2 = list(viewer.state.raw_wave)[-max_points:]

            stress_packets = viewer.state.stress_packets
            raw_packets = viewer.state.raw_packets
            latest_stress = viewer.state.latest_stress_percent

        if x1 and y1:
            line1.set_data(x1, y1)
            ax1.set_xlim(min(x1), max(x1))
            ax1.set_ylim(0, 105)

        if x2 and y2:
            line2.set_data(x2, y2)
            ax2.set_xlim(min(x2), max(x2))
            ymin, ymax = min(y2), max(y2)
            pad = max(50, int((ymax - ymin) * 0.1))
            ax2.set_ylim(ymin - pad, ymax + pad)

        stress_display = "n/a" if latest_stress is None else f"{latest_stress:.1f}%"
        status_text.set_text(
            f"Stress packets: {stress_packets} | Raw EDA packets: {raw_packets} | Latest stress: {stress_display}"
        )

        return line1, line2, status_text

    ani = FuncAnimation(
        fig, update, interval=refresh_ms, blit=False, cache_frame_data=False
    )

    def _on_close(_event):
        viewer._running = False

    fig.canvas.mpl_connect("close_event", _on_close)
    plt.tight_layout()
    plt.show()

    # Keep a live reference to avoid premature GC in some environments.
    return ani


async def run_waveform_viewer(
    ring_addr: str | None = None,
    window_seconds: int = 10,
    refresh_ms: int = 120,
) -> int:
    """Run live waveform viewer and block until plot window closes."""
    viewer = NuanicWaveformViewer(ring_addr=ring_addr)

    if not await viewer.connect_and_subscribe():
        print("[FAIL] Could not connect and subscribe to waveform streams")
        return 1

    print("[OK] Connected. Opening live plot window...")

    # Run BLE loop in background while matplotlib blocks on UI thread.
    worker = asyncio.create_task(viewer.run_until_stopped())

    try:
        run_plot(viewer, window_seconds=window_seconds, refresh_ms=refresh_ms)
    finally:
        await viewer.stop()
        await worker

    print("[STOP] Waveform viewer stopped")
    return 0
