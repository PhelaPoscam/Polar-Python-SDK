"""Dual-Device cross-validation analysis CLI (Polar H10 vs Polar Verity Sense).

Usage:
    python scripts/run_analysis.py [session_dir]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

from polar_ble_sdk.research import (  # noqa: E402
    compute_validation_metrics,
    generate_markdown_report,
    generate_validation_plots,
    load_session,
    verify_session_integrity,
)


def find_latest_session_dir() -> Path | None:
    """Find the most recent session directory in data/dual/ or data/."""
    dual_dir = PROJECT_ROOT / "data" / "dual"
    if dual_dir.exists():
        subdirs = [p for p in dual_dir.iterdir() if p.is_dir()]
        if subdirs:
            subdirs.sort(key=lambda p: p.name, reverse=True)
            return subdirs[0]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Polar Dual-Device Cross-Validation Analysis"
    )
    parser.add_argument(
        "session_dir",
        nargs="?",
        type=str,
        default=None,
        help="Path to session directory",
    )
    args = parser.parse_args()

    console = Console()

    if args.session_dir:
        session_path = Path(args.session_dir).resolve()
    else:
        latest = find_latest_session_dir()
        if not latest:
            console.print(
                "[bold red]No session directory specified and no recorded sessions found in data/dual/.[/bold red]"
            )
            sys.exit(1)
        session_path = latest

    if not session_path.exists():
        console.print(
            f"[bold red]Session directory does not exist: {session_path}[/bold red]"
        )
        sys.exit(1)

    console.print(f"\n[bold cyan]Analyzing Session:[/bold cyan] {session_path.name}")
    console.print(f"[dim]Directory: {session_path}[/dim]\n")

    # 1. Load Session Data
    session = load_session(session_path)
    if not session:
        console.print("[bold red]Failed to load session data.[/bold red]")
        sys.exit(1)

    # 2. Signal Integrity Audit
    audit_data = verify_session_integrity(session_path)
    if audit_data:
        audit_table = Table(
            title="Signal Integrity & Sampling Rate Audit", title_style="bold cyan"
        )
        audit_table.add_column("Device / Stream", style="bold")
        audit_table.add_column("Actual (Hz)", justify="right")
        audit_table.add_column("Std Dev (Hz)", justify="right")
        audit_table.add_column("Samples", justify="right")
        audit_table.add_column("Duration (s)", justify="right")
        audit_table.add_column("Gaps (>2x)", justify="right")
        audit_table.add_column("Max Gap (s)", justify="right")

        for dev_key in ("h10", "sense", "streams"):
            if dev_key in audit_data and isinstance(audit_data[dev_key], dict):
                for s_name, a in audit_data[dev_key].items():
                    audit_table.add_row(
                        f"{dev_key.upper()} - {s_name}",
                        f"{a['average_hz']:.2f}",
                        f"{a['std_dev_hz']:.2f}",
                        str(a["sample_count"]),
                        f"{a['duration_s']:.1f}",
                        str(a["gap_count"]),
                        f"{a['max_gap_s']:.3f}",
                    )
        console.print(audit_table)
        console.print()

    # 3. Merged Summary & Cross-Validation
    df_merged = pd.DataFrame()
    if (
        session.is_dual
        and "h10" in session.dual_sessions
        and "sense" in session.dual_sessions
    ):
        h10_sum = session.dual_sessions["h10"].summary
        sense_sum = session.dual_sessions["sense"].summary
        if not h10_sum.empty and not sense_sum.empty:
            h10_sum = h10_sum.rename(
                columns={"HeartRate_BPM": "H10_HR", "HRV_RMSSD_ms": "H10_RMSSD"}
            )
            sense_sum = sense_sum.rename(
                columns={"HeartRate_BPM": "Sense_HR", "HRV_RMSSD_ms": "Sense_RMSSD"}
            )
            df_merged = (
                pd.merge(h10_sum, sense_sum, on="Timestamp", how="outer")
                .sort_values("Timestamp")
                .reset_index(drop=True)
            )

    # 4. PPG Optical Waveform Derivation (if raw PPG is recorded)
    ppg_epochs = pd.DataFrame()
    ppg_csv = session_path / "sense" / "raw" / "ppg.csv"
    if ppg_csv.exists():
        from polar_ble_sdk.research.ppg import derive_ppg_hr_epochs

        ppg_epochs = derive_ppg_hr_epochs(session_path)

    if (
        not df_merged.empty
        and "H10_HR" in df_merged.columns
        and "Sense_HR" in df_merged.columns
    ):
        metrics = compute_validation_metrics(df_merged)

        def _val_str(v: float, unit: str = "") -> str:
            import numpy as np

            return f"{v:.2f}{unit}" if not np.isnan(v) else "-"

        def _grade_fmt(grade: str) -> str:
            if grade == "valid":
                return "[bold green]EXCELLENT[/bold green]"
            if grade == "acceptable":
                return "[yellow]ACCEPTABLE[/yellow]"
            if grade == "poor":
                return "[red]POOR[/red]"
            return "[dim]N/A[/dim]"

        if metrics["n_samples"] > 0:
            val_table = Table(
                title="Cross-Validation Agreement & Reliability (Reported HR)",
                title_style="bold green",
            )
            val_table.add_column("Metric", style="bold")
            val_table.add_column("Value", justify="right")
            val_table.add_column("Grade", justify="center")
            val_table.add_column("Reference Target", justify="left")

            val_table.add_row(
                "Mean Absolute Error (MAE)",
                _val_str(metrics["mae"], " BPM"),
                _grade_fmt(metrics["mae_grade"]),
                "< 5.0 BPM",
            )
            val_table.add_row(
                "Mean Absolute % Error (MAPE)",
                _val_str(metrics["mape"], " %"),
                _grade_fmt(metrics["mape_grade"]),
                "< 5.0 %",
            )
            val_table.add_row(
                "Systematic Bias",
                _val_str(metrics["bias"], " BPM"),
                _grade_fmt(metrics["bias_grade"]),
                "|Bias| < 2.0 BPM",
            )
            val_table.add_row(
                "Lin's CCC",
                _val_str(metrics["lins_ccc"]),
                _grade_fmt(metrics["ccc_grade"]),
                "> 0.90",
            )
            val_table.add_row(
                "ICC (2,1) Agreement",
                _val_str(metrics["icc_2_1"]),
                _grade_fmt(metrics["icc_grade"]),
                "> 0.75",
            )
            val_table.add_row(
                "Pearson r",
                _val_str(metrics["pearson_r"]),
                _grade_fmt(metrics["r_grade"]),
                "> 0.90",
            )
            val_table.add_row(
                "Within-Subject CV",
                _val_str(metrics["wscv"], " %"),
                _grade_fmt(metrics["cv_grade"]),
                "< 5.0 %",
            )
            val_table.add_row(
                "Dropout Rate",
                _val_str(metrics["dropout_rate"], " %"),
                _grade_fmt(metrics["dropout_grade"]),
                "< 5.0 %",
            )

            console.print(val_table)
            console.print()

    if not ppg_epochs.empty:
        valid_ep = ppg_epochs.dropna(subset=["h10_hr", "ppg_hr"])
        if len(valid_ep) > 0:
            ppg_diff = valid_ep["ppg_hr"] - valid_ep["h10_hr"]
            ppg_mae = float(np.mean(np.abs(ppg_diff)))
            ppg_bias = float(np.mean(ppg_diff))
            ppg_r = (
                float(valid_ep["h10_hr"].corr(valid_ep["ppg_hr"]))
                if len(valid_ep) > 1
                else float("nan")
            )

            ppg_table = Table(
                title="Optical PPG Raw Waveform vs H10 ECG (10s Epochs)",
                title_style="bold magenta",
            )
            ppg_table.add_column("Metric", style="bold")
            ppg_table.add_column("Value", justify="right")
            ppg_table.add_column("Status / Assessment", justify="left")

            ppg_table.add_row(
                "Total 10s Epochs", str(len(ppg_epochs)), "Full recording analyzed"
            )
            ppg_table.add_row(
                "Valid Optical Epochs",
                str(len(valid_ep)),
                f"{len(valid_ep) / len(ppg_epochs) * 100:.1f}% tracking rate",
            )
            ppg_table.add_row(
                "PPG Derived MAE",
                f"{ppg_mae:.2f} BPM",
                (
                    "[bold green]Strong agreement[/bold green]"
                    if ppg_mae < 5
                    else "[yellow]Moderate[/yellow]"
                ),
            )
            ppg_table.add_row(
                "PPG Derived Bias", f"{ppg_bias:+.2f} BPM", "Optical fundamental offset"
            )
            ppg_table.add_row(
                "Correlation (r)",
                f"{ppg_r:.3f}",
                (
                    "[bold green]High linear correlation[/bold green]"
                    if ppg_r > 0.85
                    else "[yellow]Moderate[/yellow]"
                ),
            )

            ppg_metrics_dict = {
                "total_epochs": len(ppg_epochs),
                "valid_epochs": len(valid_ep),
                "tracking_rate": len(valid_ep) / len(ppg_epochs) * 100.0,
                "mae": ppg_mae,
                "bias": ppg_bias,
                "r": ppg_r,
            }

            console.print(ppg_table)
            console.print()
        else:
            ppg_metrics_dict = None
    else:
        ppg_metrics_dict = None

    # 5. Generate Reports & Plots
    reports_dir = session_path / "reports"
    plots = (
        generate_validation_plots(df_merged, reports_dir) if not df_merged.empty else []
    )
    report_md = (
        generate_markdown_report(
            metrics, session_path.name, ppg_metrics=ppg_metrics_dict
        )
        if "metrics" in locals()
        else ""
    )
    if report_md:
        report_file = reports_dir / "validation_report.md"
        reports_dir.mkdir(parents=True, exist_ok=True)
        with report_file.open("w", encoding="utf-8") as f:
            f.write(report_md)

    plot_info = f"\nPlots Generated: [cyan]{len(plots)} figures[/cyan]" if plots else ""
    console.print(
        Panel(
            f"[bold green]Analysis complete![/bold green]\n"
            f"Session: [cyan]{session_path.name}[/cyan]\n"
            f"Reports: [cyan]{reports_dir}[/cyan]{plot_info}",
            title="Analysis Status",
            border_style="green",
        )
    )


if __name__ == "__main__":
    main()
