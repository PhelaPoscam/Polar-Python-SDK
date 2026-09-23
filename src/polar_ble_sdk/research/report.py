"""Figures and Markdown report for window-level cross-device validation.

Artifact windows are always drawn (as open markers / shading), never silently
dropped: the primary result is on all windows, the artifact-free one is a
sensitivity analysis.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .validation import agreement  # noqa: E402

REF = "#2ca02c"
TEST = "#ff7f0e"


def _bland_altman(
    ax: Any, w: pd.DataFrame, ref: str, test: str, art: str, log_ratio: bool, unit: str
) -> None:
    ok = w[[ref, test]].notna().all(axis=1)
    if log_ratio:
        ok &= (w[ref] > 0) & (w[test] > 0)
    d = w[ok]
    x, y = d[ref].to_numpy(dtype=float), d[test].to_numpy(dtype=float)
    mean = (x + y) / 2.0
    diff = y / x if log_ratio else y - x
    is_art = d[art].to_numpy(dtype=bool) if art in d else np.zeros(len(d), bool)
    ax.scatter(mean[~is_art], diff[~is_art], c=TEST, label="clean window")
    ax.scatter(
        mean[is_art],
        diff[is_art],
        facecolors="none",
        edgecolors=TEST,
        label="artifact window",
    )
    a = agreement(x, y, log_ratio=log_ratio, n_boot=200)
    if a.get("n", 0) >= 3:
        for key, style in (("bias", "-"), ("loa_lower", "--"), ("loa_upper", "--")):
            ax.axhline(a[key], color="k", linestyle=style, linewidth=1)
            if key != "bias":
                ax.axhspan(
                    a[f"{key}_ci_low"], a[f"{key}_ci_high"], color="grey", alpha=0.15
                )
    if log_ratio:
        ax.set_xscale("log")
        ax.set_yscale("log")
    ax.set_xlabel(f"Mean of methods ({unit})")
    ax.set_ylabel(
        "Ratio test / reference" if log_ratio else f"Test - reference ({unit})"
    )
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, linestyle="--", alpha=0.4)


def generate_validation_plots(windows: pd.DataFrame, output_dir: Path) -> list[Path]:
    """Bland-Altman (HR, RMSSD) and time-series figures; returns the saved paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    if windows.empty or "ref_hr" not in windows:
        return paths
    w = windows[windows["ref_ok"]] if "ref_ok" in windows else windows

    for ref, test, art, log_ratio, unit, name, title in (
        ("ref_hr", "ppg_hr", "artifact", False, "BPM", "bland_altman_hr.png", "HR"),
        (
            "ref_rmssd",
            "ppg_rmssd",
            "artifact",
            True,
            "ms",
            "bland_altman_rmssd.png",
            "RMSSD",
        ),
    ):
        if test not in w or w[test].notna().sum() < 3:
            continue
        fig, ax = plt.subplots(figsize=(7, 5))
        _bland_altman(ax, w, ref, test, art, log_ratio, unit)
        ax.set_title(f"Bland-Altman: PPG {title} vs H10 RR (bands: 95 % CI of LoA)")
        fig.tight_layout()
        fig.savefig(output_dir / name, dpi=150)
        plt.close(fig)
        paths.append(output_dir / name)

    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    for ax, ref, test, unit in (
        (axes[0], "ref_hr", "ppg_hr", "HR (BPM)"),
        (axes[1], "ref_rmssd", "ppg_rmssd", "RMSSD (ms)"),
    ):
        ax.plot(w["start"], w[ref], "o-", color=REF, label="H10 RR (reference)")
        if test in w:
            ax.plot(w["start"], w[test], "s--", color=TEST, label="Verity Sense PPG")
        if "artifact" in w:
            for start in w.loc[w["artifact"].astype(bool), "start"]:
                ax.axvspan(
                    start, start + (w["start"].diff().median()), color="red", alpha=0.1
                )
        ax.set_ylabel(unit)
        ax.grid(True, linestyle="--", alpha=0.4)
    axes[0].legend(loc="best", fontsize=8)
    axes[0].set_title("Per-window agreement (red = Sense artifact window)")
    fig.tight_layout()
    fig.savefig(output_dir / "time_series.png", dpi=150)
    plt.close(fig)
    paths.append(output_dir / "time_series.png")
    return paths


def _fmt(v: Any, spec: str = ".2f") -> str:
    return "-" if v is None or not np.isfinite(v) else format(v, spec)


def _result_rows(label: str, res: dict[str, Any]) -> list[str]:
    ratio = res.get("log_ratio")
    unit = "×" if ratio else ""
    if res.get("n", 0) < 3:
        return [f"| {label} | {res.get('n', 0)} | - | - | - | - | - | - | - |"]
    loa = (
        f"{_fmt(res['loa_lower'])}{unit} [{_fmt(res['loa_lower_ci_low'])}, "
        f"{_fmt(res['loa_lower_ci_high'])}] to {_fmt(res['loa_upper'])}{unit} "
        f"[{_fmt(res['loa_upper_ci_low'])}, {_fmt(res['loa_upper_ci_high'])}]"
    )
    bias = f"{_fmt(res['bias'])}{unit} [{_fmt(res['bias_ci_low'])}, {_fmt(res['bias_ci_high'])}]"
    grades = res.get("grades", {})
    return [
        f"| {label} | {res['n']} | {bias} | {loa} "
        f"| {_fmt(res['prop_bias_slope'], '.3f')} (p={_fmt(res['prop_bias_p'], '.3f')}) "
        f"| {_fmt(res['mae'])} [{_fmt(res['mae_ci_low'])}, {_fmt(res['mae_ci_high'])}] "
        f"| {_fmt(res['mape'])} % {('(' + grades['mape'] + ')') if grades else ''} "
        f"| {_fmt(res['lins_ccc'], '.3f')} {('(' + grades['lins_ccc'] + ')') if grades else ''} "
        f"| {_fmt(res['icc_2_1'], '.3f')} {('(' + grades['icc_2_1'] + ')') if grades else ''} |"
    ]


def generate_markdown_report(
    results: list[dict[str, Any]],
    session_id: str,
    windows: pd.DataFrame,
    window_s: int,
    pooled: list[dict[str, Any]] | None = None,
) -> str:
    """Markdown report: methods, per-comparison agreement (all / clean), windows."""
    n_art = int(windows["artifact"].sum()) if "artifact" in windows else 0
    lines = [
        "# Polar Verity Sense vs H10: Agreement Report",
        "",
        f"**Session**: `{session_id}`  ",
        f"**Windows**: {len(windows)} × {window_s} s, non-overlapping, host clock  ",
        "**Reference**: H10 RR intervals (ECG-derived on device, 1/1024 s), cleaned "
        "(300-2000 ms, ±20 % of local median; invalid beats excluded, successive "
        "differences only between adjacent valid intervals)  ",
        "**Test**: Verity Sense raw PPG beats (band-pass 0.5-4 Hz, interpolated peaks, "
        "best channel per window by spectral SQI) and, if recorded, the Sense PPI stream  ",
        f"**Artifact windows**: {n_art} (Sense accelerometer motion, PPG SQI, coverage, "
        "skin contact; never the reference)",
        "",
        "Bias and limits of agreement (LoA) are shown with 95 % CIs; RMSSD uses "
        "log-transformed limits reported as ratios (test/reference). MAE CIs come from "
        "a moving-block bootstrap over windows. Proportional bias = slope of the "
        "difference on the mean. Grades only where a published standard exists "
        "(MAPE: ANSI/CTA-2065; CCC: McBride 2005; ICC: Koo & Li 2016).",
        "",
    ]
    header = [
        "| Comparison | n | Bias [95 % CI] | LoA [95 % CI] | Prop. bias | MAE [95 % CI] | MAPE | CCC | ICC(2,1) |",
        "| :--- | ---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for key, title in (
        ("all", "## Primary: all windows with a valid reference"),
        ("clean", "## Sensitivity: artifact windows excluded"),
    ):
        lines += [title, "", *header]
        for res in results:
            if key in res:
                lines += _result_rows(res["label"], res[key])
        lines.append("")

    if pooled:
        lines += [
            "## Pooled over participants (Bland & Altman 2007, cluster bootstrap)",
            "",
            "| Comparison | Participants | Windows | Bias [95 % CI] | LoA [95 % CI] |",
            "| :--- | ---: | ---: | :--- | :--- |",
        ]
        for p in pooled:
            if "bias" not in p:
                continue
            u = "×" if p["log_ratio"] else ""
            lines.append(
                f"| {p['label']} | {p['n_subjects']} | {p['n_windows']} "
                f"| {_fmt(p['bias'])}{u} [{_fmt(p['bias_ci_low'])}, {_fmt(p['bias_ci_high'])}] "
                f"| {_fmt(p['loa_lower'])}{u} [{_fmt(p['loa_lower_ci_low'])}, {_fmt(p['loa_lower_ci_high'])}]"
                f" to {_fmt(p['loa_upper'])}{u} [{_fmt(p['loa_upper_ci_low'])}, {_fmt(p['loa_upper_ci_high'])}] |"
            )
        lines.append("")

    cols = [
        c
        for c in (
            "start",
            "ref_hr",
            "ppg_hr",
            "ref_rmssd",
            "ppg_rmssd",
            "ppg_sqi",
            "motion_frac",
            "artifact_reason",
            "markers",
        )
        if c in windows
    ]
    lines += [
        "## Windows",
        "",
        "| " + " | ".join(cols) + " |",
        "|" + " --- |" * len(cols),
    ]
    for _, row in windows[cols].iterrows():
        cells = [
            row[c].strftime("%H:%M:%S")
            if c == "start"
            else _fmt(row[c])
            if isinstance(row[c], float)
            else str(row[c])
            for c in cols
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
