from __future__ import annotations

import asyncio
import contextlib
import sys
import time
import traceback
from typing import Any
from polar_python import PolarDevice
from polar_python.constants import (
    PmdMeasurementType,
    PolarCharacteristic,
)


class BasePolarDevice:
    """Base class for connecting and streaming from Polar devices."""

    def __init__(self, device, **kwargs) -> None:
        self.device = device
        self.polar_device: Any = None
        self._running = False
        self.custom_settings = kwargs
        self.verbose = kwargs.get("verbose", True)
        self.connect_attempts = kwargs.get("connect_attempts", 3)
        self.connect_timeout = kwargs.get("connect_timeout", 20.0)
        self.retry_backoff = kwargs.get("retry_backoff", 1.5)
        self.pair_before_streaming = kwargs.get("pair_before_streaming", False)
        self.reconnect_before_streaming = kwargs.get(
            "reconnect_before_streaming", False
        )
        self.pair_timeout = kwargs.get("pair_timeout", 60.0)
        self.post_pair_delay = kwargs.get("post_pair_delay", 2.0)

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    async def start_notify(self) -> None:
        """Connect to device and initialize notifications."""
        device_name = getattr(self.device, "name", "") or ""
        last_error: Any = None

        async def _subscribe_and_start():
            await self.polar_device._client.start_notify(
                PolarCharacteristic.PMD_CONTROL_POINT.value,
                self.polar_device._handle_pmd_control,
            )
            await self.polar_device._client.start_notify(
                PolarCharacteristic.PMD_DATA.value, self.polar_device._handle_pmd_data
            )
            self._running = True
            await self.start_streams()

        for attempt in range(1, self.connect_attempts + 1):
            attempt_started = time.monotonic()
            try:
                self.polar_device = PolarDevice(self.device)
                self._log(
                    f"Connecting to {device_name or 'Polar device'} "
                    f"(attempt {attempt}/{self.connect_attempts})..."
                )
                await asyncio.wait_for(
                    self.polar_device._client.connect(), timeout=self.connect_timeout
                )
                await self._reconnect_if_needed()
                await self._pair_if_needed(device_name)
                stream_setup_started = time.monotonic()
                await _subscribe_and_start()
                stream_setup_elapsed = time.monotonic() - stream_setup_started
                total_elapsed = time.monotonic() - attempt_started
                self._log(
                    "Connected and authenticated successfully "
                    f"(stream setup {stream_setup_elapsed:.1f}s, total {total_elapsed:.1f}s)."
                )
                return
            except Exception as e:
                last_error = e
                err_str = str(e)
                if (
                    "Authentication" in err_str
                    or "Insufficient" in err_str
                    or "(5)" in err_str
                    or "-2147023673" in err_str
                ):
                    self._log(
                        f"Device ({device_name}) requires pairing. Initiating BLE pairing/bonding..."
                    )
                    try:
                        self._log("\n" + "=" * 80)
                        self._log("PAIRING PIN REQUESTED!")
                        self._log(
                            "Please look at your device screen and Windows notifications/popups now."
                        )
                        self._log(
                            "Confirm/type the pairing PIN code on both the device and the PC."
                        )
                        self._log("=" * 80 + "\n")
                        await self._pair_client()
                        # pair() stores bond keys in Windows registry, but the current
                        # connection is still unauthenticated. Reconnect so Windows opens
                        # a fresh encrypted session using the new bond keys.
                        self._log(
                            "Pairing accepted. Re-establishing authenticated connection..."
                        )
                        await self._disconnect_client(clear_device=False)
                        await asyncio.sleep(1.0)
                        await asyncio.wait_for(
                            self.polar_device._client.connect(),
                            timeout=self.connect_timeout,
                        )
                        self._log("Retrying stream subscription...")
                        stream_setup_started = time.monotonic()
                        await _subscribe_and_start()
                        stream_setup_elapsed = time.monotonic() - stream_setup_started
                        total_elapsed = time.monotonic() - attempt_started
                        self._log(
                            "Connected and authenticated successfully after pairing "
                            f"(stream setup {stream_setup_elapsed:.1f}s, total {total_elapsed:.1f}s)!"
                        )
                        return
                    except Exception as pair_err:
                        self._log(f"Failed to complete pairing: {pair_err}")
                        last_error = pair_err
                elif "not found" in err_str.lower() or "FB005C81" in err_str:
                    self._log("\n" + "=" * 60)
                    self._log(
                        "SDK STREAM NOT ACTIVE: The device is not exposing the measurement service."
                    )
                    self._log(
                        "Please ensure SDK Sharing is active and the device is ready."
                    )
                    self._log("=" * 60 + "\n")
                    await self._disconnect_client()
                    raise e

                await self._disconnect_client()
                if attempt < self.connect_attempts:
                    await asyncio.sleep(self.retry_backoff * attempt)

        raise last_error

    async def _pair_if_needed(self, device_name: str) -> None:
        """Wait for Windows pairing before starting protected Polar streams."""
        if not self.pair_before_streaming or sys.platform != "win32":
            return

        client = getattr(self.polar_device, "_client", None)
        if not client or not hasattr(client, "pair"):
            return

        self._log(
            f"Waiting for Windows pairing approval for {device_name or 'Polar device'}..."
        )
        pair_started = time.monotonic()
        try:
            await self._pair_client()
        except Exception as exc:
            err_str = str(exc).lower()
            if "already" not in err_str and "bond" not in err_str:
                raise
        pair_elapsed = time.monotonic() - pair_started
        self._log(
            "Windows pairing completed "
            f"({pair_elapsed:.1f}s). Reconnecting before stream setup..."
        )
        reconnect_started = time.monotonic()
        await self._disconnect_client(clear_device=False)
        await asyncio.sleep(self.post_pair_delay)
        await asyncio.wait_for(client.connect(), timeout=self.connect_timeout)
        reconnect_elapsed = time.monotonic() - reconnect_started
        self._log(f"Reconnected after pairing ({reconnect_elapsed:.1f}s).")

    async def _reconnect_if_needed(self) -> None:
        """Open a fresh BLE session before PMD setup without forcing Windows pairing."""
        if not self.reconnect_before_streaming:
            return

        client = getattr(self.polar_device, "_client", None)
        if not client:
            return

        reconnect_started = time.monotonic()
        self._log("Refreshing BLE connection before stream setup...")
        await self._disconnect_client(clear_device=False)
        await asyncio.sleep(self.post_pair_delay)
        await asyncio.wait_for(client.connect(), timeout=self.connect_timeout)
        reconnect_elapsed = time.monotonic() - reconnect_started
        self._log(f"BLE connection refreshed ({reconnect_elapsed:.1f}s).")

    async def _pair_client(self) -> None:
        client = getattr(self.polar_device, "_client", None)
        if not client or not hasattr(client, "pair"):
            return

        result = await asyncio.wait_for(client.pair(), timeout=self.pair_timeout)
        if result is False:
            raise RuntimeError("Windows pairing was rejected or did not complete.")

    async def start_streams(self) -> None:
        """To be overridden by subclasses to start their specific streams."""
        pass

    async def stop_notify(self) -> None:
        """Stop all streams and disconnect."""
        await self._disconnect_client()

    async def _disconnect_client(self, *, clear_device: bool = True) -> None:
        """Release the SDK/Bleak client even after a partial connection failure."""
        if not self.polar_device:
            self._running = False
            return

        client = getattr(self.polar_device, "_client", None)
        with contextlib.suppress(Exception):
            await self.polar_device.disconnect()
        if client:
            with contextlib.suppress(Exception):
                await client.disconnect()

        self._running = False
        if clear_device:
            self.polar_device = None

    async def _get_default_settings(self, measurement_type: PmdMeasurementType) -> dict:
        """Query the device for available settings and extract the first supported value."""
        try:
            settings_obj = await self.polar_device.request_stream_settings(
                measurement_type
            )
            settings_dict = {}
            for s in settings_obj.settings:
                if s.values:
                    settings_dict[s.type] = s.values[0]
            return settings_dict
        except Exception as ex:
            self._log(
                f"Warning: Could not fetch settings for {measurement_type.name}: {ex}"
            )
            return {}

    async def _start_pmd_stream(
        self,
        callback,
        measurement_type: PmdMeasurementType,
        method_name: str,
        handler,
        features: list,
        defaults: dict,
        label: str,
    ) -> None:
        """Start a PMD measurement stream with standard setup, debug logging and error handling.

        Args:
            callback: The user-provided callback (None if stream not requested).
            measurement_type: PMD measurement type enum for feature check and settings fetch.
            method_name: Name of the start method on polar_device (e.g. ``"start_ecg_stream"``).
            handler: The internal handler method bound to this instance.
            features: List of available PMD features from ``get_available_features()``.
            defaults: Fallback kwargs keyed by string parameter name when not available in settings.
            label: Human-readable stream name for debug output.
        """
        if not callback:
            return
        if measurement_type not in features:
            self._log(f"[DEBUG] {label} skipped — not in available features")
            return
        try:
            settings = await self._get_default_settings(measurement_type)
            # Normalise setting-type keys to plain strings so they can be unpacked as **kwargs.
            resolved: dict[str, object] = {}
            for key, value in settings.items():
                if hasattr(key, "name"):
                    key_str = key.name.lower()
                elif hasattr(key, "value") and isinstance(key.value, str):
                    key_str = key.value
                else:
                    key_str = str(key)
                resolved[key_str] = value
            for key, value in defaults.items():
                resolved.setdefault(key, value)
            for key in resolved.keys():
                custom_key = f"{label.lower()}_{key}"
                if custom_key in self.custom_settings and self.custom_settings[custom_key] is not None:
                    resolved[key] = self.custom_settings[custom_key]
            method = getattr(self.polar_device, method_name)
            await method(handler, **resolved)
            self._log(f"[DEBUG] {label} stream started OK")
        except Exception:
            self._log(f"[DEBUG] {label} stream failed:")
            if self.verbose:
                traceback.print_exc()
