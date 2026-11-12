from enum import IntEnum


class PmdSettingType(IntEnum):
    SAMPLE_RATE = 0
    RESOLUTION = 1
    RANGE = 2
    RANGE_MILLIUNIT = 3
    CHANNELS = 4
    FACTOR = 5
    SECURITY = 6
    DERIVED_MEASUREMENT_METHOD = 7
    SOURCE_MEASUREMENT_TYPE = 8
    SOURCE_MEASUREMENT_SAMPLE_RATE = 9
    SOURCE_MEASUREMENT_RANGE = 10
    DERIVED_MEASUREMENT_TIME_WINDOW = 11
    DERIVED_MEASUREMENT_SETTINGS_GROUP_ID = 12
    UNKNOWN = 255

    @classmethod
    def _missing_(cls, _unused_value):
        return cls.UNKNOWN

    @property
    def field_size(self) -> int:
        """Get the field size in bytes for the setting type (as in PmdSetting.kt)."""
        match self:
            case (
                PmdSettingType.RANGE_MILLIUNIT
                | PmdSettingType.FACTOR
                | PmdSettingType.SOURCE_MEASUREMENT_RANGE
                | PmdSettingType.DERIVED_MEASUREMENT_TIME_WINDOW
            ):
                return 4
            case (
                PmdSettingType.CHANNELS
                | PmdSettingType.DERIVED_MEASUREMENT_METHOD
                | PmdSettingType.SOURCE_MEASUREMENT_TYPE
                | PmdSettingType.DERIVED_MEASUREMENT_SETTINGS_GROUP_ID
            ):
                return 1
            case PmdSettingType.SECURITY:
                return 16
            case _:
                return 2
