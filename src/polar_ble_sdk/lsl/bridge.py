"""Research-grade Lab Streaming Layer (LSL) bridge for Polar BLE devices.

Provides synchronized, low-latency, multi-channel LSL StreamOutlets for Polar H10
and Polar Verity Sense streams (ECG, PPG, ACC, Gyro, Mag, HR, and experiment markers).

Burst Unrolling:
    BLE delivers physiological and motion data in packet chunks (e.g. ~14 ECG samples
    every 107ms). Naive single-timestamp chunking creates stair-step timing artifacts.
    This bridge unrolls each packet burst using nominal sample delta (dt = 1/fs),
    providing continuous, sub-millisecond, sample-accurate LSL timestamps compatible
    with LabRecorder, EEGLAB, Timeflux, and custom real-time pipelines.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

try:
    import pylsl  # type: ignore[import-untyped]

    HAS_PYLSL = True
except ImportError:
    pylsl = None  # type: ignore[assignment]
    HAS_PYLSL = False


@dataclass
class LSLOutletConfig:
    """Metadata configuration for an individual LSL stream outlet."""

    name: str
    type: str
    channel_count: int
    nominal_srate: float
    channel_format: str  # "float32" | "int32" | "string"
    source_id: str
    unit: str = ""
    channel_names: list[str] = field(default_factory=list)


class PolarLSLBridge:
    """Publishes Polar physiological, motion, and marker streams over Lab Streaming Layer (LSL)."""

    def __init__(
        self,
        h10_id: str = "H10",
        sense_id: str = "Sense",
        *,
        enable_h10: bool = True,
        enable_sense: bool = True,
        enable_sense_gyro: bool = False,
        enable_sense_mag: bool = False,
        ppg_rate: float = 135.0,
        acc_rate_h10: float = 200.0,
        acc_rate_sense: float = 52.0,
    ) -> None:
        if not HAS_PYLSL or pylsl is None:
            raise ImportError(
                "pylsl is required for LSL streaming. "
                "Install it via 'pip install polar-ble-sdk[lsl]' or 'pip install pylsl'."
            )

        self.h10_id = h10_id
        self.sense_id = sense_id
        self.enable_h10 = enable_h10
        self.enable_sense = enable_sense
        self.enable_sense_gyro = enable_sense_gyro
        self.enable_sense_mag = enable_sense_mag
        self.ppg_rate = ppg_rate
        self.acc_rate_h10 = acc_rate_h10
        self.acc_rate_sense = acc_rate_sense

        self.outlets: dict[str, Any] = {}
        self.configs: dict[str, LSLOutletConfig] = {}
        self._init_outlets()

    def _init_outlets(self) -> None:
        """Create and register all requested LSL StreamOutlets."""
        if self.enable_h10:
            self._create_outlet(
                key="h10_ecg",
                config=LSLOutletConfig(
                    name=f"Polar_{self.h10_id}_ECG",
                    type="ECG",
                    channel_count=1,
                    nominal_srate=130.0,
                    channel_format="float32",
                    source_id=f"{self.h10_id}_ecg",
                    unit="microvolts",
                    channel_names=["ECG"],
                ),
            )
            self._create_outlet(
                key="h10_acc",
                config=LSLOutletConfig(
                    name=f"Polar_{self.h10_id}_ACC",
                    type="Acceleration",
                    channel_count=3,
                    nominal_srate=self.acc_rate_h10,
                    channel_format="float32",
                    source_id=f"{self.h10_id}_acc",
                    unit="mG",
                    channel_names=["ACC_X", "ACC_Y", "ACC_Z"],
                ),
            )
            self._create_outlet(
                key="h10_hr",
                config=LSLOutletConfig(
                    name=f"Polar_{self.h10_id}_HR",
                    type="HR",
                    channel_count=2,
                    nominal_srate=pylsl.IRREGULAR_RATE,
                    channel_format="float32",
                    source_id=f"{self.h10_id}_hr",
                    unit="BPM,ms",
                    channel_names=["HeartRate_BPM", "RR_Interval_ms"],
                ),
            )

        if self.enable_sense:
            self._create_outlet(
                key="sense_ppg",
                config=LSLOutletConfig(
                    name=f"Polar_{self.sense_id}_PPG",
                    type="PPG",
                    channel_count=4,
                    nominal_srate=self.ppg_rate,
                    channel_format="int32",
                    source_id=f"{self.sense_id}_ppg",
                    unit="raw_adc",
                    channel_names=["CH1", "CH2", "CH3", "CH4"],
                ),
            )
            self._create_outlet(
                key="sense_acc",
                config=LSLOutletConfig(
                    name=f"Polar_{self.sense_id}_ACC",
                    type="Acceleration",
                    channel_count=3,
                    nominal_srate=self.acc_rate_sense,
                    channel_format="float32",
                    source_id=f"{self.sense_id}_acc",
                    unit="mG",
                    channel_names=["ACC_X", "ACC_Y", "ACC_Z"],
                ),
            )
            if self.enable_sense_gyro:
                self._create_outlet(
                    key="sense_gyro",
                    config=LSLOutletConfig(
                        name=f"Polar_{self.sense_id}_GYRO",
                        type="Gyroscope",
                        channel_count=3,
                        nominal_srate=52.0,
                        channel_format="float32",
                        source_id=f"{self.sense_id}_gyro",
                        unit="dps",
                        channel_names=["GYRO_X", "GYRO_Y", "GYRO_Z"],
                    ),
                )
            if self.enable_sense_mag:
                self._create_outlet(
                    key="sense_mag",
                    config=LSLOutletConfig(
                        name=f"Polar_{self.sense_id}_MAG",
                        type="Magnetometer",
                        channel_count=3,
                        nominal_srate=20.0,
                        channel_format="float32",
                        source_id=f"{self.sense_id}_mag",
                        unit="Gauss",
                        channel_names=["MAG_X", "MAG_Y", "MAG_Z"],
                    ),
                )

        # Experiment Markers Outlet
        self._create_outlet(
            key="markers",
            config=LSLOutletConfig(
                name="Polar_Markers",
                type="Markers",
                channel_count=1,
                nominal_srate=pylsl.IRREGULAR_RATE,
                channel_format="string",
                source_id="polar_markers",
                unit="event",
                channel_names=["Marker"],
            ),
        )

    def _create_outlet(self, key: str, config: LSLOutletConfig) -> None:
        """Helper to create and configure a StreamInfo and StreamOutlet."""
        info = pylsl.StreamInfo(
            name=config.name,
            type=config.type,
            channel_count=config.channel_count,
            nominal_srate=config.nominal_srate,
            channel_format=config.channel_format,
            source_id=config.source_id,
        )
        desc = info.desc()
        channels = desc.append_child("channels")
        for ch_name in config.channel_names:
            ch = channels.append_child("channel")
            ch.append_child_value("label", ch_name)
            if config.unit:
                ch.append_child_value("unit", config.unit)

        outlet = pylsl.StreamOutlet(info)
        self.outlets[key] = outlet
        self.configs[key] = config
        logger.info("Created LSL Outlet: %s (%s)", config.name, config.type)

    def local_clock(self) -> float:
        """Return the current LSL master clock timestamp in seconds."""
        if pylsl is not None:
            return float(pylsl.local_clock())
        import time

        return time.time()

    def push_h10_ecg(self, data: Any) -> None:
        """Push a burst of ECG samples with sample-accurate burst unrolling."""
        if "h10_ecg" not in self.outlets:
            return
        _ts_hw, samples = data
        n = len(samples)
        if n == 0:
            return

        t_now = self.local_clock()
        dt = 1.0 / 130.0
        timestamps = [t_now - (n - 1 - i) * dt for i in range(n)]
        chunk = [[float(s)] for s in samples]
        self.outlets["h10_ecg"].push_chunk(chunk, timestamps)

    def push_h10_acc(self, data: Any) -> None:
        """Push a burst of H10 3-axis ACC samples with burst unrolling."""
        if "h10_acc" not in self.outlets:
            return
        _ts_hw, samples = data
        n = len(samples)
        if n == 0:
            return

        t_now = self.local_clock()
        dt = 1.0 / self.acc_rate_h10
        timestamps = [t_now - (n - 1 - i) * dt for i in range(n)]
        chunk = [[float(s[0]), float(s[1]), float(s[2])] for s in samples]
        self.outlets["h10_acc"].push_chunk(chunk, timestamps)

    def push_h10_hr(self, data: Any) -> None:
        """Push an instantaneous Heart Rate measurement and all RR intervals."""
        if "h10_hr" not in self.outlets:
            return
        hr_val, rr_list = data
        if hr_val <= 0:
            return
        t_now = self.local_clock()
        if rr_list:
            for rr in rr_list:
                self.outlets["h10_hr"].push_sample([float(hr_val), float(rr)], t_now)
        else:
            self.outlets["h10_hr"].push_sample([float(hr_val), 0.0], t_now)

    def push_sense_ppg(self, data: Any) -> None:
        """Push a burst of Verity Sense 4-channel optical PPG samples."""
        if "sense_ppg" not in self.outlets:
            return
        _ts_hw, samples = data
        n = len(samples)
        if n == 0:
            return

        t_now = self.local_clock()
        dt = 1.0 / self.ppg_rate
        timestamps = [t_now - (n - 1 - i) * dt for i in range(n)]
        chunk = []
        for s in samples:
            if isinstance(s, list | tuple):
                if len(s) >= 4:
                    chunk.append([int(s[0]), int(s[1]), int(s[2]), int(s[3])])
                else:
                    padded = [int(v) for v in s] + [0] * (4 - len(s))
                    chunk.append(padded)
            else:
                chunk.append([int(s), 0, 0, 0])
        self.outlets["sense_ppg"].push_chunk(chunk, timestamps)

    def push_sense_acc(self, data: Any) -> None:
        """Push a burst of Verity Sense 3-axis ACC samples."""
        if "sense_acc" not in self.outlets:
            return
        _ts_hw, samples = data
        n = len(samples)
        if n == 0:
            return

        t_now = self.local_clock()
        dt = 1.0 / self.acc_rate_sense
        timestamps = [t_now - (n - 1 - i) * dt for i in range(n)]
        chunk = [[float(s[0]), float(s[1]), float(s[2])] for s in samples]
        self.outlets["sense_acc"].push_chunk(chunk, timestamps)

    def push_sense_gyro(self, data: Any) -> None:
        """Push a burst of Verity Sense 3-axis Gyroscope samples."""
        if "sense_gyro" not in self.outlets:
            return
        _ts_hw, samples = data
        n = len(samples)
        if n == 0:
            return

        t_now = self.local_clock()
        dt = 1.0 / 52.0
        timestamps = [t_now - (n - 1 - i) * dt for i in range(n)]
        chunk = [[float(s[0]), float(s[1]), float(s[2])] for s in samples]
        self.outlets["sense_gyro"].push_chunk(chunk, timestamps)

    def push_sense_mag(self, data: Any) -> None:
        """Push a burst of Verity Sense 3-axis Magnetometer samples."""
        if "sense_mag" not in self.outlets:
            return
        _ts_hw, samples = data
        n = len(samples)
        if n == 0:
            return

        t_now = self.local_clock()
        dt = 1.0 / 20.0
        timestamps = [t_now - (n - 1 - i) * dt for i in range(n)]
        chunk = [[float(s[0]), float(s[1]), float(s[2])] for s in samples]
        self.outlets["sense_mag"].push_chunk(chunk, timestamps)

    def push_marker(self, marker_text: str) -> None:
        """Push an experiment marker event with current LSL timestamp."""
        if "markers" not in self.outlets:
            return
        t_now = self.local_clock()
        self.outlets["markers"].push_sample([str(marker_text)], t_now)

    def wrap_callback(
        self, stream_name: str, existing_cb: Callable[[Any], None] | None = None
    ) -> Callable[[Any], None]:
        """Wrap an existing callback to also push incoming samples to LSL."""
        push_dispatch: dict[str, Callable[[Any], None]] = {
            "h10_ecg": self.push_h10_ecg,
            "h10_acc": self.push_h10_acc,
            "h10_hr": self.push_h10_hr,
            "sense_ppg": self.push_sense_ppg,
            "sense_acc": self.push_sense_acc,
            "sense_gyro": self.push_sense_gyro,
            "sense_mag": self.push_sense_mag,
        }
        push_fn = push_dispatch.get(stream_name)

        def wrapped(data: Any) -> None:
            if existing_cb is not None:
                try:
                    existing_cb(data)
                except Exception as cb_exc:
                    logger.warning(
                        "Error in user callback for %s: %s", stream_name, cb_exc
                    )
            if push_fn is not None:
                try:
                    push_fn(data)
                except Exception as exc:
                    logger.debug("Error pushing to LSL outlet %s: %s", stream_name, exc)

        return wrapped

    def close(self) -> None:
        """Close all active LSL outlets."""
        self.outlets.clear()
        self.configs.clear()
