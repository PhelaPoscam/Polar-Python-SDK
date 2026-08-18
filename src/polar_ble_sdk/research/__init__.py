"""Research package for data loading, signal integrity audits, PPG processing, and validation."""

from .audit import StreamAudit, audit_csv_stream, verify_session_integrity
from .loader import PolarSessionData, load_session
from .ppg import (
    bandpass_filter,
    clean_ibi,
    derive_ppg_hr_epochs,
    detect_peaks_epoch,
    epoch_hr_from_fft,
    epoch_hr_from_zc,
    ibi_to_hr,
    ibi_to_rmssd,
)
from .report import generate_markdown_report, generate_validation_plots
from .validation import (
    bootstrap_ci,
    build_epochs,
    calculate_icc_2_1,
    calculate_lins_ccc,
    compute_validation_metrics,
    detect_sense_artifacts,
    grade_metrics,
)

__all__ = [
    "PolarSessionData",
    "load_session",
    "StreamAudit",
    "audit_csv_stream",
    "verify_session_integrity",
    "calculate_lins_ccc",
    "calculate_icc_2_1",
    "bootstrap_ci",
    "detect_sense_artifacts",
    "build_epochs",
    "compute_validation_metrics",
    "grade_metrics",
    "bandpass_filter",
    "epoch_hr_from_zc",
    "epoch_hr_from_fft",
    "detect_peaks_epoch",
    "clean_ibi",
    "ibi_to_hr",
    "ibi_to_rmssd",
    "derive_ppg_hr_epochs",
    "generate_validation_plots",
    "generate_markdown_report",
]
