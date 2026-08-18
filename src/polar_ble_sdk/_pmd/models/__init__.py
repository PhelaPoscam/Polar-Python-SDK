from typing import TypeAlias

from .acc_data import ACCData
from .ecg_data import ECGData
from .gyro_data import GyroData
from .hr_data import HRData
from .mag_data import CalibrationStatus, MAGData
from .measurement_settings import MeasurementSettings
from .pmd_data_frame import PmdDataFrame
from .ppg_data import PPGData
from .ppi_data import PPIData

SensorData: TypeAlias = (
    ECGData | ACCData | PPIData | PPGData | GyroData | MAGData | HRData
)

__all__ = [
    "ACCData",
    "CalibrationStatus",
    "ECGData",
    "HRData",
    "PPIData",
    "PPGData",
    "GyroData",
    "MAGData",
    "MeasurementSettings",
    "SensorData",
    "PmdDataFrame",
]
