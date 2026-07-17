import contextlib
import traceback
from collections.abc import Callable

from polar_python.constants import PmdMeasurementType

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
        self._ppg_default_rate = 55

    async def start_streams(self) -> None:
        """Start the Verity Sense (and compatible) streams."""
        features = await self._fetch_available_features()

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

        # 2. Start ECG stream
        await self._start_pmd_stream(
            self.ecg_callback,
            PmdMeasurementType.ECG,
            "start_ecg_stream",
            self._ecg_handler,
            features,
            {"sample_rate": 130, "resolution": 14},
            "ECG",
        )

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
            {"sample_rate": 52, "resolution": 16, "range": 2, "channels": 3},
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

    def _ecg_handler(self, ecg_data) -> None:
        if self.ecg_callback:
            with contextlib.suppress(Exception):
                self.ecg_callback((ecg_data.timestamp, ecg_data.data))

    def _ppi_handler(self, ppi_data) -> None:
        ppi_vals = [s.ppi for s in ppi_data.samples if not s.invalid_ppi]
        if self.ppi_callback:
            try:
                if ppi_vals:
                    self.ppi_callback((ppi_data.timestamp, ppi_vals))
            except Exception:
                pass
        # Forward the computed heart rate from the PPI samples to the standard HR callback
        if self.callback and ppi_data.samples:
            try:
                latest_sample = ppi_data.samples[-1]
                self.callback((latest_sample.hr, ppi_vals))
            except Exception:
                pass

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
