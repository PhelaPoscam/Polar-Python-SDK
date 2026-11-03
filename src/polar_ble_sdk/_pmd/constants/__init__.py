from typing import Final

from .pmd_control_operation_code import PmdControlOperationCode
from .pmd_control_point_error_code import PmdControlPointErrorCode
from .pmd_measurement_type import PmdMeasurementType
from .pmd_setting_type import PmdSettingType
from .polar_characteristic import PolarCharacteristic

# Epoch offset for Polar device timestamps (Jan 1, 2000)
TIMESTAMP_OFFSET: Final[int] = 946684800000000000

# Delivery delays of the beat streams, measured against the H10 ECG over 1 h
# (2026-11-03). Polar documents neither, so re-measure after a firmware update.
# A Verity Sense PPI frame arrives ~7.3 s after its last beat (7.24-7.50 s).
SENSE_PPI_DELAY_S: Final[float] = 7.3
# An H10 HR notification arrives ~2.0 s after the beat ending its last RR
# (median 1.99 s, 5-95 % 1.6-2.6 s: where the beat fell in the 1 s cycle).
H10_RR_DELAY_S: Final[float] = 2.0

__all__ = [
    "H10_RR_DELAY_S",
    "PmdControlOperationCode",
    "PmdControlPointErrorCode",
    "PmdMeasurementType",
    "PmdSettingType",
    "PolarCharacteristic",
    "SENSE_PPI_DELAY_S",
    "TIMESTAMP_OFFSET",
]
