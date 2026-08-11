import contextlib
import traceback
from collections.abc import Callable

from ..._pmd.constants import PmdMeasurementType
from .base import BasePolarDevice


class PolarVeritySense(BasePolarDevice):
    """Connection wrapper for Polar Verity Sense / OH1 optical heart rate sensors."""

    def __init__(
        self,
        device,
        callback: Callable | None = None,
        ppi_callback: Callable | None = None,
        ppg_callback: Callable | None = None,
        acc_callback: Callable | None = None,
        gyro_callback: Callable | None = None,
        mag_callback: Callable | None = None,
        ecg_callback: Callable | None = None,
        **kwargs,
    ) -> None:
        kwargs.setdefault("reconnect_before_streaming", True)
        super().__init__(device, **kwargs)
        self.callback = callback  # Callback for Heart Rate and RR-Intervals
        self.ppi_callback = ppi_callback
        self.ppg_callback = ppg_callback
        self.acc_callback = acc_callback
        self.gyro_callback = gyro_callback
        self.mag_callback = mag_callback
        self.ecg_callback = ecg_callback
        self._ppi_active = False
        # Configurable defaults for subclasses (Watch overrides some).
        self._strict_hr = False
        self._catch_auth_on_features = True
        # 135 Hz PPG is the default: at 55 Hz the raw optical signal is
        # dominated by a fixed ~104 BPM beat artifact and the cardiac pulse is
        # not recoverable; at 135 Hz the pulse is clearly present (validated:
        # zero-crossing HR within ~2.6 BPM of the H10 ECG). 135 Hz requires
        # SDK mode, which disables the Sense's own HR/PPI streams.
        self._ppg_default_rate = 135

    async def start_streams(self) -> None:
        """Start the Verity Sense (and compatible) streams."""
        features = await self._fetch_available_features()

        # SDK mode unlocks higher PPG rates (135/176 Hz) and is now the default.
        # A user can disable it via custom_settings["sdk_mode"]=False.
        custom = getattr(self, "custom_settings", {}) or {}
        want_sdk = custom.get("sdk_mode", True)  # SDK mode ON by default
        if want_sdk:
            try:
                # Enable unconditionally (idempotent); the status pre-check can
                # fail if the response format differs, so don't gate on it.
                await self.polar_device.enable_sdk_mode()
                self._log("[DEBUG] SDK mode enabled")
            except Exception as e:
                self._log(f"[DEBUG] SDK mode enable failed: {e}")

        # 1. Start standard Heart Rate stream
        if self.callback:
            try:
                await self.polar_device.start_hr_stream(self._hr_handler)
                self._log("[DEBUG] HR stream started OK")
            except Exception as e:
                self._log(f"[DEBUG] HR stream failed: {e}")
                if self._strict_hr:
                    raise
                if self.verbose:
                    traceback.print_exc()

        # 3. Start PPG stream
        await self._start_pmd_stream(
            self.ppg_callback,
            PmdMeasurementType.PPG,
            "start_ppg_stream",
            self._ppg_handler,
            features,
            {"sample_rate": self._ppg_default_rate, "resolution": 22, "channels": 4},
            "PPG",
        )

        # 4. Start ACC stream
        await self._start_pmd_stream(
            self.acc_callback,
            PmdMeasurementType.ACC,
            "start_acc_stream",
            self._acc_handler,
            features,
            {"sample_rate": 52, "resolution": 16, "range": 8, "channels": None},
            "ACC",
        )

        # 5. Start PPI stream
        if self.ppi_callback and PmdMeasurementType.PPI in features:
            try:
                self._ppi_active = True
                await self.polar_device.start_ppi_stream(self._ppi_handler)
                self._log("[DEBUG] PPI stream started OK")
            except Exception:
                self._ppi_active = False
                self._log("[DEBUG] PPI stream failed:")
                if self.verbose:
                    traceback.print_exc()

        # 6. Start Gyro stream
        await self._start_pmd_stream(
            self.gyro_callback,
            PmdMeasurementType.GYRO,
            "start_gyro_stream",
            self._gyro_handler,
            features,
            {"sample_rate": 52, "resolution": 16, "range": 2000, "channels": 3},
            "GYRO",
        )

        # 7. Start Magnetometer stream
        await self._start_pmd_stream(
            self.mag_callback,
            PmdMeasurementType.MAG,
            "start_mag_stream",
            self._mag_handler,
            features,
            {"sample_rate": 20, "resolution": 16, "range": 50, "channels": 3},
            "MAG",
        )

    async def _fetch_available_features(self) -> list:
        """Query PMD features, optionally catching non-auth errors."""
        if not self._catch_auth_on_features:
            return await self.polar_device.get_available_features()
        try:
            features = await self.polar_device.get_available_features()
            feature_names = [f.name for f in features] if features else []
            self._log(f"[DEBUG] Available PMD features: {feature_names or '(none)'}")
            return features
        except Exception as e:
            err_str = str(e)
            if any(
                term in err_str
                for term in (
                    "Authentication",
                    "Insufficient",
                    "(5)",
                    "-2147023673",
                    "not connected",
                    "Not connected",
                )
            ):
                raise e
            self._log("[DEBUG] get_available_features() failed:")
            if self.verbose:
                traceback.print_exc()
            return []

    async def stop_notify(self) -> None:
        self._ppi_active = False
        await super().stop_notify()

    def _hr_handler(self, hr_data) -> None:
        if self.callback:
            if hr_data.heartrate == 0:
                return
            with contextlib.suppress(Exception):
                self.callback((hr_data.heartrate, hr_data.rr_intervals))

    def _ppi_handler(self, ppi_data) -> None:
        ppi_vals = []
        for s in ppi_data.samples:
            if s.invalid_ppi:
                continue
            ppi_vals.append(
                (
                    s.timestamp,
                    s.ppi,
                    s.error_estimate,
                    s.hr,
                    s.skin_contact_status,
                    s.skin_contact_supported,
                )
            )
        if self.ppi_callback and ppi_vals:
            with contextlib.suppress(Exception):
                self.ppi_callback(ppi_vals)

    def _ppg_handler(self, ppg_data) -> None:
        if self.ppg_callback:
            try:
                self.ppg_callback((ppg_data.timestamp, ppg_data.samples))
            except Exception:
                import traceback

                traceback.print_exc()

    def _acc_handler(self, acc_data) -> None:
        if self.acc_callback:
            try:
                self.acc_callback((acc_data.timestamp, acc_data.data))
            except Exception:
                import traceback

                traceback.print_exc()

    def _gyro_handler(self, gyro_data) -> None:
        if self.gyro_callback:
            try:
                self.gyro_callback((gyro_data.timestamp, gyro_data.data))
            except Exception:
                import traceback

                traceback.print_exc()

    def _mag_handler(self, mag_data) -> None:
        if self.mag_callback:
            try:
                mag_vals = [(s.x, s.y, s.z) for s in mag_data.data]
                self.mag_callback((mag_data.timestamp, mag_vals))
            except Exception:
                import traceback

                traceback.print_exc()
