"""Cross-validation and statistical metrics for dual Polar recordings (H10 vs Verity Sense).

Calculates accuracy, agreement, reliability, artifact detection, and epoch binning.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd


def calculate_lins_ccc(x: Any, y: Any) -> float:
    """Calculate Lin's Concordance Correlation Coefficient (CCC)."""
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    valid = (~np.isnan(x_arr)) & (~np.isnan(y_arr))
    x_arr, y_arr = x_arr[valid], y_arr[valid]

    if len(x_arr) < 2:
        return float("nan")

    mean_x = float(np.mean(x_arr))
    mean_y = float(np.mean(y_arr))
    var_x = float(np.var(x_arr, ddof=1))
    var_y = float(np.var(y_arr, ddof=1))

    if var_x == 0 and var_y == 0:
        return 1.0 if mean_x == mean_y else 0.0

    cov_xy = float(np.cov(x_arr, y_arr)[0, 1])
    denom = var_x + var_y + (mean_x - mean_y) ** 2
    if denom == 0:
        return float("nan")
    return (2.0 * cov_xy) / denom


def calculate_icc_2_1(x: Any, y: Any) -> float:
    """Calculate Two-way random/mixed, single-measurement absolute agreement ICC(2,1)."""
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    valid = (~np.isnan(x_arr)) & (~np.isnan(y_arr))
    x_arr, y_arr = x_arr[valid], y_arr[valid]

    n = len(x_arr)
    if n < 3:
        return float("nan")

    data = np.column_stack((x_arr, y_arr))
    grand_mean = float(np.mean(data))

    ss_total = float(np.sum((data - grand_mean) ** 2))
    row_means = np.mean(data, axis=1)
    ss_rows = 2.0 * float(np.sum((row_means - grand_mean) ** 2))
    col_means = np.mean(data, axis=0)
    ss_cols = n * float(np.sum((col_means - grand_mean) ** 2))
    ss_error = ss_total - ss_rows - ss_cols

    ms_rows = ss_rows / (n - 1)
    ms_cols = ss_cols / (2 - 1)
    ms_error = max(0.0, ss_error / ((n - 1) * (2 - 1)))

    denom = ms_rows + ms_error + (2.0 / n) * (ms_cols - ms_error)
    if denom == 0:
        return float("nan")
    return float((ms_rows - ms_error) / denom)


def bootstrap_ci(
    data: Any,
    stat_fn: Callable[[np.ndarray], float],
    n_boot: int = 500,
    ci: float = 95.0,
    seed: int = 42,
) -> tuple[float, float]:
    """Calculate percentile bootstrap confidence intervals."""
    data_arr = np.asarray(data, dtype=float)
    data_arr = data_arr[~np.isnan(data_arr)]
    if len(data_arr) < 2:
        return float("nan"), float("nan")

    rng = np.random.default_rng(seed)
    boot_stats = np.empty(n_boot)
    n = len(data_arr)

    for i in range(n_boot):
        sample = rng.choice(data_arr, size=n, replace=True)
        boot_stats[i] = stat_fn(sample)

    alpha = (100.0 - ci) / 2.0
    lo = float(np.percentile(boot_stats, alpha))
    hi = float(np.percentile(boot_stats, 100.0 - alpha))
    return lo, hi


def detect_sense_artifacts(
    df: pd.DataFrame,
    min_plateau_sec: int = 20,
    min_diff_sec: int = 15,
    diff_threshold: float = 15.0,
    min_contact_sec: int = 15,
    min_error_ms: int = 200,
) -> pd.DataFrame:
    """Detect optical PPG sensor artifacts in Sense_HR:

    1. Exact constant plateaus >= min_plateau_sec while H10 varies.
    2. Sustained large differences (|Sense_HR - H10_HR| > diff_threshold) for >= min_diff_sec.
    3. Device-reported PPI quality: sustained loss of skin contact or large PPI error estimates.
    """
    df = df.copy()
    df["artifact"] = False
    df["artifact_layer"] = None

    if "H10_HR" not in df.columns or "Sense_HR" not in df.columns:
        return df

    n = len(df)
    if n == 0:
        return df

    sense_hr = df["Sense_HR"].values
    h10_hr = df["H10_HR"].values

    artifact_mask = np.zeros(n, dtype=bool)
    artifact_layers: list[str | None] = [None] * n

    # 1. Plateau detection (exact constant non-zero value for >= min_plateau_sec while H10 varies)
    curr_val: float | None = None
    curr_start = 0

    def _check_and_mark_plateau(start_idx: int, end_idx: int) -> None:
        length = end_idx - start_idx
        if length >= min_plateau_sec:
            sub_h10 = h10_hr[start_idx:end_idx]
            valid_h10 = sub_h10[(~np.isnan(sub_h10)) & (sub_h10 > 0)]
            if len(valid_h10) > 0 and np.std(valid_h10) > 0:
                for idx in range(start_idx, end_idx):
                    artifact_mask[idx] = True
                    artifact_layers[idx] = "plateau"

    for i in range(n):
        val = sense_hr[i]
        if np.isnan(val) or val <= 0:
            if curr_val is not None:
                _check_and_mark_plateau(curr_start, i)
            curr_val = None
        elif val == curr_val:
            continue
        else:
            if curr_val is not None:
                _check_and_mark_plateau(curr_start, i)
            curr_val = val
            curr_start = i

    if curr_val is not None:
        _check_and_mark_plateau(curr_start, n)

    # 2. Sustained large diff detection
    diff = np.abs(sense_hr - h10_hr)
    large_diff = (
        (~np.isnan(diff)) & (diff > diff_threshold) & (sense_hr > 0) & (h10_hr > 0)
    )

    diff_start: int | None = None
    for i in range(n):
        if large_diff[i]:
            if diff_start is None:
                diff_start = i
        else:
            if diff_start is not None:
                length = i - diff_start
                if length >= min_diff_sec:
                    for idx in range(diff_start, i):
                        artifact_mask[idx] = True
                        if artifact_layers[idx] is None:
                            artifact_layers[idx] = "diff"
            diff_start = None

    if diff_start is not None:
        length = n - diff_start
        if length >= min_diff_sec:
            for idx in range(diff_start, n):
                artifact_mask[idx] = True
                if artifact_layers[idx] is None:
                    artifact_layers[idx] = "diff"

    # 3. Device-reported PPI quality
    contact_col = "PPI_SkinContact"
    err_col = "PPI_ErrEst_ms"
    if contact_col in df.columns or err_col in df.columns:
        poor = np.zeros(n, dtype=bool)
        if contact_col in df.columns:
            contact = pd.to_numeric(df[contact_col], errors="coerce")
            poor |= contact.notna() & (contact == 0)
        if err_col in df.columns:
            err = pd.to_numeric(df[err_col], errors="coerce")
            poor |= err.notna() & (err > min_error_ms)

        run_start: int | None = None
        for i in range(n):
            if poor[i]:
                if run_start is None:
                    run_start = i
            else:
                if run_start is not None and (i - run_start) >= min_contact_sec:
                    for idx in range(run_start, i):
                        artifact_mask[idx] = True
                        if artifact_layers[idx] is None:
                            artifact_layers[idx] = "ppi_quality"
                run_start = None
        if run_start is not None and (n - run_start) >= min_contact_sec:
            for idx in range(run_start, n):
                artifact_mask[idx] = True
                if artifact_layers[idx] is None:
                    artifact_layers[idx] = "ppi_quality"

    df["artifact"] = artifact_mask
    df["artifact_layer"] = artifact_layers
    return df


def build_epochs(
    df: pd.DataFrame, epoch_sec: int = 10, min_samples: int = 5
) -> pd.DataFrame:
    """Bin 1-second rows into N-second epochs with paired validity verification."""
    if df.empty or "Timestamp" not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    if "artifact" not in df.columns:
        df["artifact"] = False

    df["epoch_start"] = pd.to_datetime(df["Timestamp"]).dt.floor(f"{epoch_sec}s")

    epochs = []
    for ep_start, group in df.groupby("epoch_start"):
        h10_valid = group[(group["H10_HR"].notna()) & (group["H10_HR"] > 0)]
        h10_n = len(h10_valid)
        h10_hr = float(h10_valid["H10_HR"].mean()) if h10_n > 0 else float("nan")

        sense_valid = group[
            (group["Sense_HR"].notna()) & (group["Sense_HR"] > 0) & (~group["artifact"])
        ]
        sense_n = len(sense_valid)
        sense_hr = (
            float(sense_valid["Sense_HR"].mean()) if sense_n > 0 else float("nan")
        )

        hr_paired_valid = (h10_n >= min_samples) and (sense_n >= min_samples)

        if not hr_paired_valid:
            h10_hr = float("nan")
            sense_hr = float("nan")

        hr_diff = sense_hr - h10_hr if hr_paired_valid else float("nan")
        hr_abs_err = abs(hr_diff) if hr_paired_valid else float("nan")

        epochs.append(
            {
                "epoch_start": ep_start,
                "h10_n": h10_n,
                "sense_n": sense_n,
                "h10_hr": h10_hr,
                "sense_hr": sense_hr,
                "h10_rmssd": (
                    float(group["H10_RMSSD"].mean())
                    if "H10_RMSSD" in group
                    else float("nan")
                ),
                "sense_rmssd": (
                    float(group["Sense_RMSSD"].mean())
                    if "Sense_RMSSD" in group
                    else float("nan")
                ),
                "hr_paired_valid": hr_paired_valid,
                "hr_diff": hr_diff,
                "hr_abs_err": hr_abs_err,
            }
        )

    return pd.DataFrame(epochs)


def grade_metrics(metrics: dict[str, Any]) -> dict[str, str]:
    """Grade metrics into performance tiers ('valid', 'acceptable', 'poor', or 'n/a')."""

    def grade_val(
        val: Any,
        thresh_valid: float,
        thresh_acceptable: float | None = None,
        lower_is_better: bool = True,
    ) -> str:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return "n/a"
        if lower_is_better:
            if val <= thresh_valid:
                return "valid"
            if thresh_acceptable is not None and val <= thresh_acceptable:
                return "acceptable"
            return "poor"
        else:
            if val >= thresh_valid:
                return "valid"
            if thresh_acceptable is not None and val >= thresh_acceptable:
                return "acceptable"
            return "poor"

    bias_val = metrics.get("bias")
    bias_mag: float | None = None
    if bias_val is not None:
        try:
            b_float = float(bias_val)
            if not np.isnan(b_float):
                bias_mag = abs(b_float)
        except (ValueError, TypeError):
            pass

    return {
        "mae_grade": grade_val(metrics.get("mae"), 5.0, lower_is_better=True),
        "mape_grade": grade_val(metrics.get("mape"), 5.0, 10.0, lower_is_better=True),
        "bias_grade": grade_val(
            bias_mag,
            2.0,
            lower_is_better=True,
        ),
        "ccc_grade": grade_val(
            metrics.get("lins_ccc"), 0.90, 0.70, lower_is_better=False
        ),
        "icc_grade": grade_val(
            metrics.get("icc_2_1"), 0.75, 0.60, lower_is_better=False
        ),
        "r_grade": grade_val(
            metrics.get("pearson_r"), 0.90, 0.70, lower_is_better=False
        ),
        "cv_grade": grade_val(metrics.get("wscv"), 5.0, 10.0, lower_is_better=True),
        "dropout_grade": grade_val(
            metrics.get("dropout_rate"), 5.0, 10.0, lower_is_better=True
        ),
    }


def compute_validation_metrics(df: pd.DataFrame) -> dict[str, Any]:
    """Compute comprehensive cross-validation metrics across accuracy, agreement, and reliability."""
    if df.empty:
        return {
            "n_samples": 0,
            "n_artifact_seconds": 0,
            "artifact_rate": 0.0,
            "artifact_runs": [],
            "n_epochs": 0,
            "total_records": 0,
            "dropout_rate": 0.0,
        }

    df = df.copy()
    if "H10_HR" in df.columns and "Sense_HR" in df.columns:
        if "HR_Diff" not in df.columns:
            df["HR_Diff"] = df["Sense_HR"] - df["H10_HR"]
        if "HR_Abs_Error" not in df.columns:
            df["HR_Abs_Error"] = np.abs(df["HR_Diff"])

    df = detect_sense_artifacts(df)
    n_artifact_seconds = int(df["artifact"].sum()) if "artifact" in df.columns else 0
    total_records = len(df)
    artifact_rate = (
        (n_artifact_seconds / total_records) * 100.0 if total_records > 0 else 0.0
    )

    epochs = build_epochs(df)
    n_epochs = (
        int(epochs["hr_paired_valid"].sum())
        if not epochs.empty and "hr_paired_valid" in epochs.columns
        else 0
    )

    valid_hr = df.dropna(subset=["H10_HR", "Sense_HR"])
    valid_hr = valid_hr[
        (valid_hr["H10_HR"] > 0)
        & (valid_hr["Sense_HR"] > 0)
        & (~valid_hr.get("artifact", False))
    ]
    n = len(valid_hr)
    dropout_rate = (
        ((total_records - n) / total_records) * 100.0 if total_records > 0 else 0.0
    )

    if n == 0:
        base: dict[str, Any] = {
            "n_samples": 0,
            "n_artifact_seconds": n_artifact_seconds,
            "artifact_rate": artifact_rate,
            "n_epochs": n_epochs,
            "total_records": total_records,
            "dropout_rate": dropout_rate,
            "h10_mean": float("nan"),
            "h10_std": float("nan"),
            "h10_min": float("nan"),
            "h10_max": float("nan"),
            "sense_mean": float("nan"),
            "sense_std": float("nan"),
            "sense_min": float("nan"),
            "sense_max": float("nan"),
            "mae": float("nan"),
            "mape": float("nan"),
            "rmse": float("nan"),
            "bias": float("nan"),
            "sd_diff": float("nan"),
            "loa_upper": float("nan"),
            "loa_lower": float("nan"),
            "pearson_r": float("nan"),
            "spearman_r": float("nan"),
            "lins_ccc": float("nan"),
            "icc_2_1": float("nan"),
            "wscv": float("nan"),
            "within_1bpm": float("nan"),
            "within_2bpm": float("nan"),
            "within_5bpm": float("nan"),
        }
        base.update(grade_metrics(base))
        return base

    x = valid_hr["H10_HR"].values.astype(float)
    y = valid_hr["Sense_HR"].values.astype(float)

    h10_mean, h10_std = float(np.mean(x)), float(np.std(x, ddof=1)) if n > 1 else 0.0
    h10_min, h10_max = float(np.min(x)), float(np.max(x))

    sense_mean, sense_std = (
        float(np.mean(y)),
        float(np.std(y, ddof=1)) if n > 1 else 0.0,
    )
    sense_min, sense_max = float(np.min(y)), float(np.max(y))

    diff = y - x
    abs_err = np.abs(diff)
    ape = (abs_err / x) * 100.0

    mae = float(np.mean(abs_err))
    mape = float(np.mean(ape))
    rmse = float(np.sqrt(np.mean(diff**2)))
    bias = float(np.mean(diff))
    sd_diff = float(np.std(diff, ddof=1)) if n > 1 else 0.0
    loa_upper = bias + 1.96 * sd_diff
    loa_lower = bias - 1.96 * sd_diff

    pearson_r = (
        float(valid_hr["H10_HR"].corr(valid_hr["Sense_HR"], method="pearson"))
        if n > 1
        else float("nan")
    )
    spearman_r = (
        float(valid_hr["H10_HR"].corr(valid_hr["Sense_HR"], method="spearman"))
        if n > 1
        else float("nan")
    )
    lins_ccc = calculate_lins_ccc(x, y)
    icc_2_1 = calculate_icc_2_1(x, y)

    paired_means = (x + y) / 2.0
    paired_stds = np.abs(x - y) / np.sqrt(2.0)
    wscv_per_pair = (paired_stds / paired_means) * 100.0
    wscv = float(np.mean(wscv_per_pair))

    within_1bpm = float(np.sum(abs_err <= 1) / n * 100.0)
    within_2bpm = float(np.sum(abs_err <= 2) / n * 100.0)
    within_5bpm = float(np.sum(abs_err <= 5) / n * 100.0)

    metrics: dict[str, Any] = {
        "n_samples": n,
        "n_artifact_seconds": n_artifact_seconds,
        "artifact_rate": artifact_rate,
        "n_epochs": n_epochs,
        "total_records": total_records,
        "dropout_rate": dropout_rate,
        "h10_mean": h10_mean,
        "h10_std": h10_std,
        "h10_min": h10_min,
        "h10_max": h10_max,
        "sense_mean": sense_mean,
        "sense_std": sense_std,
        "sense_min": sense_min,
        "sense_max": sense_max,
        "mae": mae,
        "mape": mape,
        "rmse": rmse,
        "bias": bias,
        "sd_diff": sd_diff,
        "loa_upper": loa_upper,
        "loa_lower": loa_lower,
        "pearson_r": pearson_r,
        "spearman_r": spearman_r,
        "lins_ccc": lins_ccc,
        "icc_2_1": icc_2_1,
        "wscv": wscv,
        "within_1bpm": within_1bpm,
        "within_2bpm": within_2bpm,
        "within_5bpm": within_5bpm,
    }

    metrics.update(grade_metrics(metrics))
    return metrics
