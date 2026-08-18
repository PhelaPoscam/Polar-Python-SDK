"""Automated reporting and visualization generator for cross-device validation.

Produces comprehensive Markdown reports and Matplotlib figures (Bland-Altman, time series,
error distributions, scatter correlations) saved directly to the session's report directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def generate_validation_plots(df: pd.DataFrame, output_dir: Path) -> list[Path]:
    """Generate diagnostic cross-validation plots and save them to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_paths: list[Path] = []

    valid = df.dropna(subset=["H10_HR", "Sense_HR"])
    valid = valid[(valid["H10_HR"] > 0) & (valid["Sense_HR"] > 0)]

    if len(valid) < 2:
        return plot_paths

    x = valid["H10_HR"].values.astype(float)
    y = valid["Sense_HR"].values.astype(float)
    diff = y - x
    mean = (x + y) / 2.0
    bias = float(np.mean(diff))
    sd = float(np.std(diff, ddof=1))

    # 1. Bland-Altman Plot
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(mean, diff, alpha=0.6, edgecolors="none", c="#1f77b4")
    ax.axhline(bias, color="red", linestyle="--", label=f"Mean Bias ({bias:+.2f} BPM)")
    ax.axhline(
        bias + 1.96 * sd,
        color="gray",
        linestyle=":",
        label=f"+1.96 SD ({bias + 1.96 * sd:+.2f})",
    )
    ax.axhline(
        bias - 1.96 * sd,
        color="gray",
        linestyle=":",
        label=f"-1.96 SD ({bias - 1.96 * sd:+.2f})",
    )
    ax.set_xlabel("Mean HR (BPM) [ (H10 + Sense) / 2 ]")
    ax.set_ylabel("Difference (Sense - H10) [BPM]")
    ax.set_title("Bland-Altman Agreement Plot")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="upper right")
    ba_path = output_dir / "bland_altman.png"
    fig.tight_layout()
    fig.savefig(ba_path, dpi=150)
    plt.close(fig)
    plot_paths.append(ba_path)

    # 2. Time Series Alignment Plot
    if "Timestamp" in valid.columns:
        fig, ax = plt.subplots(figsize=(10, 4))
        ts = pd.to_datetime(valid["Timestamp"])
        ax.plot(ts, x, label="Polar H10 (ECG)", color="#2ca02c", linewidth=1.5)
        ax.plot(
            ts,
            y,
            label="Verity Sense (PPG)",
            color="#ff7f0e",
            linestyle="--",
            linewidth=1.5,
        )
        ax.set_xlabel("Time")
        ax.set_ylabel("Heart Rate (BPM)")
        ax.set_title("Time-Synchronized Heart Rate Comparison")
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.legend(loc="upper right")
        ts_path = output_dir / "time_series_hr.png"
        fig.tight_layout()
        fig.savefig(ts_path, dpi=150)
        plt.close(fig)
        plot_paths.append(ts_path)

    # 3. Correlation Scatter Plot
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(x, y, alpha=0.6, c="#9467bd", edgecolors="none")
    min_val = min(float(np.min(x)), float(np.min(y))) - 5
    max_val = max(float(np.max(x)), float(np.max(y))) + 5
    ax.plot(
        [min_val, max_val],
        [min_val, max_val],
        "k--",
        label="Identity (Line of Equality)",
    )
    ax.set_xlim(min_val, max_val)
    ax.set_ylim(min_val, max_val)
    ax.set_xlabel("Polar H10 HR (BPM)")
    ax.set_ylabel("Verity Sense HR (BPM)")
    ax.set_title("Polar H10 vs Verity Sense Correlation")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="upper left")
    corr_path = output_dir / "scatter_correlation.png"
    fig.tight_layout()
    fig.savefig(corr_path, dpi=150)
    plt.close(fig)
    plot_paths.append(corr_path)

    return plot_paths


def generate_markdown_report(
    metrics: dict[str, Any],
    session_id: str,
    ppg_metrics: dict[str, Any] | None = None,
) -> str:
    """Generate a clean Markdown cross-validation report supporting both reported HR and optical PPG."""
    mae_val = metrics.get("mae")
    has_reported_hr = (metrics.get("n_samples", 0) > 0) or (
        mae_val is not None and not np.isnan(mae_val)
    )

    md_lines = [
        "# Polar Dual-Device Cross-Validation Report",
        "",
        f"**Session ID**: `{session_id}`",
        "**Criterion Reference**: Polar H10 (ECG 130 Hz + 1 kHz RR-intervals)",
        "**Evaluated Device**: Polar Verity Sense (PPG Optical + ACC/Gyro/Mag)",
        "",
        "---",
        "",
    ]

    # Section 1: Mode Description & Executive Summary
    if has_reported_hr:
        md_lines.extend(
            [
                "## 1. Executive Summary & Grading (Reported Heart Rate)",
                "",
                "| Metric | Measured Value | Grade / Status | Clinical / Research Threshold |",
                "| :--- | :--- | :--- | :--- |",
                f"| **MAE** (Mean Absolute Error) | `{metrics.get('mae', 0):.2f} BPM` | `{metrics.get('mae_grade', 'n/a').upper()}` | `< 5.0 BPM` |",
                f"| **MAPE** (Mean Absolute % Error) | `{metrics.get('mape', 0):.2f} %` | `{metrics.get('mape_grade', 'n/a').upper()}` | `< 5.0 %` |",
                f"| **Systematic Bias** | `{metrics.get('bias', 0):+.2f} BPM` | `{metrics.get('bias_grade', 'n/a').upper()}` | `|Bias| < 2.0 BPM` |",
                f"| **Lin's CCC** | `{metrics.get('lins_ccc', 0):.3f}` | `{metrics.get('ccc_grade', 'n/a').upper()}` | `> 0.90` (Substantial) |",
                f"| **ICC (2,1)** | `{metrics.get('icc_2_1', 0):.3f}` | `{metrics.get('icc_grade', 'n/a').upper()}` | `> 0.75` (Good) |",
                f"| **Pearson r** | `{metrics.get('pearson_r', 0):.3f}` | `{metrics.get('r_grade', 'n/a').upper()}` | `> 0.90` |",
                f"| **Within-Subject CV** | `{metrics.get('wscv', 0):.2f} %` | `{metrics.get('cv_grade', 'n/a').upper()}` | `< 5.0 %` |",
                f"| **Data Dropout Rate** | `{metrics.get('dropout_rate', 0):.2f} %` | `{metrics.get('dropout_grade', 'n/a').upper()}` | `< 5.0 %` |",
                "",
                "---",
                "",
                "## 2. Statistical Agreement & Distribution",
                "",
                f"- **Total Valid Paired Seconds**: `{metrics.get('n_samples', 0)} s`",
                f"- **10-Second Epochs**: `{metrics.get('n_epochs', 0)}`",
                f"- **Bland-Altman 95% Limits of Agreement**: `[{metrics.get('loa_lower', 0):+.2f}, {metrics.get('loa_upper', 0):+.2f}] BPM`",
                "- **Concordance Rates**:",
                f"  - Within $\\pm$ 1 BPM: `{metrics.get('within_1bpm', 0):.1f} %`",
                f"  - Within $\\pm$ 2 BPM: `{metrics.get('within_2bpm', 0):.1f} %`",
                f"  - Within $\\pm$ 5 BPM: `{metrics.get('within_5bpm', 0):.1f} %`",
                "",
                "---",
                "",
                "## 3. Device Summary Statistics",
                "",
                "| Device | Mean HR (BPM) | Std Dev (BPM) | Min HR | Max HR |",
                "| :--- | :--- | :--- | :--- | :--- |",
                f"| **Polar H10 (ECG)** | `{metrics.get('h10_mean', 0):.1f}` | `{metrics.get('h10_std', 0):.1f}` | `{metrics.get('h10_min', 0):.1f}` | `{metrics.get('h10_max', 0):.1f}` |",
                f"| **Polar Verity Sense** | `{metrics.get('sense_mean', 0):.1f}` | `{metrics.get('sense_std', 0):.1f}` | `{metrics.get('sense_min', 0):.1f}` | `{metrics.get('sense_max', 0):.1f}` |",
                "",
            ]
        )
    else:
        md_lines.extend(
            [
                "## 1. Operating Mode Notice",
                "",
                "> ℹ️ **Verity Sense SDK Mode Active (135 Hz High-Speed Optical Research Mode)**",
                "> In SDK Mode, the Verity Sense firmware streams raw multi-channel optical photodiode signals at **135 Hz**.",
                "> Direct 1 Hz Bluetooth Heart Rate and PPI broadcasting are disabled by Polar firmware during SDK Mode.",
                "> The validation below derives heart rate directly from the raw optical waveforms against the H10 ECG criterion.",
                "",
                "---",
                "",
            ]
        )

    # Section: Raw Optical PPG Waveform Analysis
    if ppg_metrics:
        md_lines.extend(
            [
                "## Optical PPG Raw Waveform vs H10 ECG (10s Epochs)",
                "",
                "| Metric | Measured Value | Assessment |",
                "| :--- | :--- | :--- |",
                f"| **Total Epochs Analyzed** | `{ppg_metrics.get('total_epochs', 0)}` | Full session duration |",
                f"| **Valid Optical Epochs** | `{ppg_metrics.get('valid_epochs', 0)}` | `{ppg_metrics.get('tracking_rate', 0):.1f}%` tracking rate |",
                f"| **PPG Derived MAE** | `{ppg_metrics.get('mae', 0):.2f} BPM` | `{'EXCELLENT' if ppg_metrics.get('mae', 99) < 5 else 'MODERATE'}` |",
                f"| **PPG Derived Bias** | `{ppg_metrics.get('bias', 0):+.2f} BPM` | Optical fundamental offset |",
                f"| **Linear Correlation ($r$)** | `{ppg_metrics.get('r', 0):.3f}` | `{'STRONG' if ppg_metrics.get('r', 0) > 0.70 else 'MODERATE'}` |",
                "",
            ]
        )

    return "\n".join(md_lines)
