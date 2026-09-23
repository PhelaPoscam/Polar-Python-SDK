from dataclasses import dataclass

from .pmd_data_frame import PmdDataFrame


@dataclass
class ECGData:
    """Represents electrocardiogram measurement data.

    Attributes:
        timestamp: The UNIX timestamp in nanoseconds.
        data: A list of ECG measurement values in microvolts (µV).
    """

    timestamp: int
    data: list[int]

    @classmethod
    def from_dataframe(cls, frame: "PmdDataFrame") -> "ECGData":
        if frame.is_compressed_frame:
            raise ValueError(
                f"Compressed FrameType: {frame.frame_type} is not supported by ECG data parser"
            )
        if frame.frame_type != 0:
            raise ValueError(
                f"Raw FrameType: {frame.frame_type} is not supported by ECG data parser"
            )

        content = frame.data_content
        n_samples = len(content) // 3
        ecg_samples = [
            int.from_bytes(
                content[i * 3 : (i + 1) * 3], byteorder="little", signed=True
            )
            for i in range(n_samples)
        ]

        return cls(timestamp=frame.timestamp, data=ecg_samples)
