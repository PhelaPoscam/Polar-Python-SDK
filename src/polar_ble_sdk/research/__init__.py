"""Research package for data loading, signal integrity audits, PPG processing, and validation."""

from .audit import StreamAudit, audit_csv_stream, verify_session_integrity
from .loader import PolarSessionData, load_session
from .ppg import bandpass_filter, detect_beats, spectral_hr, spectral_sqi
from .report import generate_markdown_report, generate_validation_plots
from .validation import (
    agreement,
    block_bootstrap_ci,
    calculate_icc_2_1,
    calculate_lins_ccc,
    calculate_wscv,
    grade,
    repeated_measures_agreement,
    validate_windows,
)
from .windows import build_windows

__all__ = [
    "PolarSessionData",
    "load_session",
    "StreamAudit",
    "audit_csv_stream",
    "verify_session_integrity",
    "bandpass_filter",
    "detect_beats",
    "spectral_hr",
    "spectral_sqi",
    "build_windows",
    "agreement",
    "block_bootstrap_ci",
    "calculate_icc_2_1",
    "calculate_lins_ccc",
    "calculate_wscv",
    "grade",
    "repeated_measures_agreement",
    "validate_windows",
    "generate_validation_plots",
    "generate_markdown_report",
]
