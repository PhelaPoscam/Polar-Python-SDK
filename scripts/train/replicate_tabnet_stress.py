"""
Replicable TabNet-based Stress Detection System (Jui et al., 2026)
- Uses pytorch_tabnet, scikit-learn, shap, lime, pandas, numpy
- Implements LOSO cross-validation
- Includes feature extraction and windowing utilities
- Loads WESAD and SWELL (if available) or falls back to mock data
"""

import argparse
import os
import pickle

import numpy as np
import pandas as pd
import joblib

from sklearn.datasets import make_classification
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import LeaveOneGroupOut, train_test_split

import torch
from pytorch_tabnet.tab_model import TabNetClassifier

import shap
from lime.lime_tabular import LimeTabularExplainer


VALID_LABELS = {1, 2, 3, 4}
STRESS_LABEL = 2
SWELL_STRESS_CONDITIONS = {"T", "I"}


def detect_r_peaks(ecg: np.ndarray, fs: int) -> np.ndarray:
    """
    Simple R-peak detection for ECG.
    This is a lightweight heuristic to estimate HR without external dependencies.
    """
    signal = np.asarray(ecg, dtype=np.float64).squeeze()
    if signal.size < 3:
        return np.array([], dtype=np.int64)

    signal = (signal - np.mean(signal)) / (np.std(signal) + 1e-8)
    threshold = np.percentile(signal, 90)
    candidates = np.where(signal > threshold)[0]

    peaks = []
    min_distance = int(0.3 * fs)
    last_peak = -min_distance

    for idx in candidates:
        if idx <= 0 or idx >= signal.size - 1:
            continue
        if signal[idx] <= signal[idx - 1] or signal[idx] < signal[idx + 1]:
            continue
        if idx - last_peak < min_distance:
            if peaks and signal[idx] > signal[peaks[-1]]:
                peaks[-1] = idx
                last_peak = idx
            continue
        peaks.append(idx)
        last_peak = idx

    return np.asarray(peaks, dtype=np.int64)


def ecg_to_hr(ecg: np.ndarray, fs: int) -> np.ndarray:
    """
    Estimate an HR signal from ECG using R-peak detection and interpolation.
    Returns a per-sample HR signal (bpm) aligned to ECG length.
    """
    peaks = detect_r_peaks(ecg, fs)
    if peaks.size < 2:
        return np.zeros_like(ecg, dtype=np.float32).squeeze()

    rr_intervals = np.diff(peaks) / float(fs)
    hr_values = 60.0 / np.maximum(rr_intervals, 1e-6)
    hr_times = (peaks[:-1] + peaks[1:]) / 2.0 / float(fs)

    times = np.arange(ecg.shape[0], dtype=np.float64) / float(fs)
    hr_signal = np.interp(times, hr_times, hr_values, left=hr_values[0], right=hr_values[-1])
    return hr_signal.astype(np.float32)


def window_features_with_labels(
    eda: np.ndarray,
    hr: np.ndarray,
    labels: np.ndarray,
    fs: int,
    window_s: int = 25,
    overlap: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Window signals and derive labels by majority vote over valid label values.
    """
    window_len = window_s * fs
    step = int(window_len * (1 - overlap))
    if step <= 0:
        raise ValueError("Overlap too high; step must be > 0")

    features_list = []
    label_list = []

    for start in range(0, len(eda) - window_len + 1, step):
        end = start + window_len
        eda_win = eda[start:end]
        hr_win = hr[start:end]
        label_win = labels[start:end]

        valid = label_win[np.isin(label_win, list(VALID_LABELS))]
        if valid.size == 0:
            continue

        counts = np.bincount(valid.astype(int))
        majority_label = int(np.argmax(counts))
        binary_label = 1 if majority_label == STRESS_LABEL else 0

        features = extract_features(eda_win, hr_win)
        features_list.append(features)
        label_list.append(binary_label)

    if not features_list:
        return np.empty((0, 21), dtype=np.float32), np.empty((0,), dtype=np.int64)

    X = np.vstack(features_list)
    y = np.asarray(label_list, dtype=np.int64)
    return X, y


def window_features_with_binary_labels(
    eda: np.ndarray,
    hr: np.ndarray,
    labels: np.ndarray,
    window_len: int,
    overlap: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Window signals with pre-binarized labels (0/1) and majority vote per window.
    """
    step = int(window_len * (1 - overlap))
    if step <= 0:
        raise ValueError("Overlap too high; step must be > 0")

    features_list = []
    label_list = []

    for start in range(0, len(eda) - window_len + 1, step):
        end = start + window_len
        eda_win = eda[start:end]
        hr_win = hr[start:end]
        label_win = labels[start:end]

        if label_win.size == 0:
            continue

        majority_label = int(np.round(np.mean(label_win)))
        features = extract_features(eda_win, hr_win)
        features_list.append(features)
        label_list.append(majority_label)

    if not features_list:
        return np.empty((0, 21), dtype=np.float32), np.empty((0,), dtype=np.int64)

    X = np.vstack(features_list)
    y = np.asarray(label_list, dtype=np.int64)
    return X, y


def load_wesad_dataset(
    datasets_dir: str,
    fs: int = 700,
    window_s: int = 25,
    overlap: float = 0.5,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """
    Load WESAD chest EDA/ECG, compute HR, and build windowed features.
    """
    wesad_dir = os.path.join(datasets_dir, "WESAD")
    if not os.path.isdir(wesad_dir):
        return None

    X_list = []
    y_list = []
    group_list = []

    for subject_dir in sorted(os.listdir(wesad_dir)):
        if not subject_dir.startswith("S"):
            continue
        pkl_path = os.path.join(wesad_dir, subject_dir, f"{subject_dir}.pkl")
        if not os.path.isfile(pkl_path):
            continue

        with open(pkl_path, "rb") as handle:
            data = pickle.load(handle, encoding="latin1")

        eda = data["signal"]["chest"]["EDA"].astype(np.float32).squeeze()
        ecg = data["signal"]["chest"]["ECG"].astype(np.float32).squeeze()
        labels = data["label"].astype(np.int64)

        if eda.shape[0] != labels.shape[0] or ecg.shape[0] != labels.shape[0]:
            continue

        hr = ecg_to_hr(ecg, fs)
        X_sub, y_sub = window_features_with_labels(eda, hr, labels, fs, window_s, overlap)
        if X_sub.size == 0:
            continue

        subject_id = int(subject_dir[1:]) if subject_dir[1:].isdigit() else len(group_list)
        X_list.append(X_sub)
        y_list.append(y_sub)
        group_list.append(np.full(y_sub.shape, subject_id, dtype=np.int64))

    if not X_list:
        return None

    X = np.vstack(X_list)
    y = np.concatenate(y_list)
    groups = np.concatenate(group_list)
    summary = {
        "subjects": len(np.unique(groups)),
        "windows": int(X.shape[0]),
        "stress_windows": int(np.sum(y == 1)),
        "non_stress_windows": int(np.sum(y == 0)),
    }
    return X, y, groups, summary


def load_mock_dataset() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Create a mock dataset for quick execution when real data is unavailable.
    """
    X, y = make_classification(
        n_samples=1000,
        n_features=21,
        n_informative=15,
        n_redundant=2,
        n_repeated=0,
        n_classes=2,
        random_state=42,
    )

    n_subjects = 10
    groups = np.repeat(np.arange(n_subjects), X.shape[0] // n_subjects)
    if len(groups) < X.shape[0]:
        groups = np.concatenate([groups, np.arange(X.shape[0] - len(groups))])

    return X, y, groups


def load_swell_dataset(
    datasets_dir: str,
    window_min: int = 25,
    overlap: float = 0.5,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """
    Load SWELL physiology features (HR, SCL) and compute windowed features.

    Note: The SWELL physiology file is minute-level. We treat each row as one
    sample per minute and use window_min as a window length in minutes.
    """
    swell_path = os.path.join(
        datasets_dir,
        "SWELL",
        "3 - Feature dataset",
        "per sensor",
        "D - Physiology features (HR_HRV_SCL - final).csv",
    )
    if not os.path.isfile(swell_path):
        return None

    df = pd.read_csv(swell_path)
    df = df.loc[:, ~df.columns.str.contains(r"^Unnamed", na=False)]
    df = df.replace(999, np.nan)

    for col in ("HR", "SCL"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["PP", "Condition", "HR", "SCL"])
    if df.empty:
        return None

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="%Y%m%dT%H%M%S%f", errors="coerce")

    X_list = []
    y_list = []
    group_list = []

    for subject_id, subject_df in df.groupby("PP"):
        if "timestamp" in subject_df.columns:
            subject_df = subject_df.sort_values("timestamp")

        eda = subject_df["SCL"].to_numpy(dtype=np.float32)
        hr = subject_df["HR"].to_numpy(dtype=np.float32)
        labels = (
            subject_df["Condition"]
            .apply(lambda c: 1 if c in SWELL_STRESS_CONDITIONS else 0)
            .to_numpy(dtype=np.int64)
        )

        if eda.size < window_min:
            continue

        X_sub, y_sub = window_features_with_binary_labels(
            eda,
            hr,
            labels,
            window_len=window_min,
            overlap=overlap,
        )
        if X_sub.size == 0:
            continue

        subject_num = int(str(subject_id).replace("PP", "")) if str(subject_id).startswith("PP") else len(group_list)
        X_list.append(X_sub)
        y_list.append(y_sub)
        group_list.append(np.full(y_sub.shape, subject_num, dtype=np.int64))

    if not X_list:
        return None

    X = np.vstack(X_list)
    y = np.concatenate(y_list)
    groups = np.concatenate(group_list)
    summary = {
        "subjects": len(np.unique(groups)),
        "windows": int(X.shape[0]),
        "stress_windows": int(np.sum(y == 1)),
        "non_stress_windows": int(np.sum(y == 0)),
    }
    return X, y, groups, summary


def extract_features(eda_signal: np.ndarray, hr_signal: np.ndarray) -> np.ndarray:
    """
    Extract the 21 features defined in the paper from EDA and HR signals.
    Returns a 1D array of shape (21,).
    """

    def stats(x: np.ndarray) -> list:
        mean = np.mean(x)
        median = np.median(x)
        std = np.std(x)
        var = np.var(x)
        min_v = np.min(x)
        max_v = np.max(x)
        skew = pd.Series(x).skew()
        kurt = pd.Series(x).kurt()
        dyn_range = max_v - min_v
        return [mean, median, std, var, min_v, max_v, skew, kurt, dyn_range]

    eda_feats = stats(eda_signal)
    hr_feats = stats(hr_signal)

    # Interaction feature
    cov = np.cov(eda_signal, hr_signal)[0, 1]

    # Physiological features
    # Skin resistance is inverse of EDA (avoid division by zero)
    skin_resistance = np.mean(1.0 / (eda_signal + 1e-6))
    # HRV approximation (std of HR)
    hrv = np.std(hr_signal)

    features = np.array(eda_feats + hr_feats + [cov, skin_resistance, hrv], dtype=np.float32)
    return np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)


def window_signals(
    eda: np.ndarray,
    hr: np.ndarray,
    fs: int,
    window_s: int = 25,
    overlap: float = 0.5,
) -> np.ndarray:
    """
    Sliding window feature extraction.
    window_s: window size in seconds
    overlap: fraction overlap (0.5 => 50%)
    Returns X (n_windows, 21).
    """
    window_len = window_s * fs
    step = int(window_len * (1 - overlap))
    if step <= 0:
        raise ValueError("Overlap too high; step must be > 0")

    features_list = []
    for start in range(0, len(eda) - window_len + 1, step):
        eda_win = eda[start : start + window_len]
        hr_win = hr[start : start + window_len]
        features_list.append(extract_features(eda_win, hr_win))

    return np.vstack(features_list) if features_list else np.empty((0, 21), dtype=np.float32)


def build_tabnet() -> TabNetClassifier:
    """
    Initialize TabNetClassifier with the exact hyperparameters from the paper.
    """
    return TabNetClassifier(
        n_d=41,
        n_a=41,
        n_steps=4,
        gamma=1.559,
        lambda_sparse=0.0067,
        optimizer_fn=torch.optim.Adam,
        optimizer_params=dict(lr=0.0088),
        mask_type="sparsemax",
        scheduler_params=dict(step_size=10, gamma=0.9),
    )


def generate_explanations(
    model: TabNetClassifier,
    X_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
) -> None:
    """
    Global feature importance via SHAP and local explanation via LIME.
    """
    # SHAP global explanation (uses a small background sample for speed)
    bg_size = min(100, X_train.shape[0])
    background = X_train[np.random.choice(X_train.shape[0], bg_size, replace=False)]
    explainer = shap.Explainer(model.predict_proba, background)
    _ = explainer(X_test[:200])
    print("SHAP global explanation computed.")

    # LIME local explanation for a single "High Stress" instance (label = 1)
    stress_indices = np.where(y_test == 1)[0]
    idx = stress_indices[0] if len(stress_indices) > 0 else 0

    lime_explainer = LimeTabularExplainer(
        training_data=X_train,
        feature_names=[f"f{i + 1}" for i in range(X_train.shape[1])],
        class_names=["Non-Stress", "Stress"],
        mode="classification",
        discretize_continuous=True,
    )

    explanation = lime_explainer.explain_instance(
        X_test[idx],
        model.predict_proba,
        num_features=10,
    )
    print("LIME local explanation (top 10 features):")
    print(explanation.as_list())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TabNet stress detection (WESAD/Mock).")
    parser.add_argument("--datasets-dir", default="datasets", help="Datasets folder (default: datasets).")
    parser.add_argument("--use-mock", action="store_true", help="Force mock data instead of WESAD.")
    parser.add_argument("--no-wesad", action="store_true", help="Skip WESAD loading.")
    parser.add_argument("--no-swell", action="store_true", help="Skip SWELL loading.")
    parser.add_argument("--skip-xai", action="store_true", help="Skip SHAP/LIME explanations.")
    parser.add_argument("--fs", type=int, default=700, help="WESAD chest sampling rate (default: 700 Hz).")
    parser.add_argument("--window-s", type=int, default=25, help="Window size in seconds (default: 25).")
    parser.add_argument("--swell-window-min", type=int, default=25, help="SWELL window size in minutes (default: 25).")
    parser.add_argument("--overlap", type=float, default=0.5, help="Window overlap fraction (default: 0.5).")
    parser.add_argument("--no-train-final", action="store_true", help="Skip training a final model.")
    parser.add_argument("--model-dir", default="models", help="Directory to save final model/scaler.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.use_mock:
        X, y, groups = load_mock_dataset()
        print("Using mock dataset.")
    else:
        X_parts = []
        y_parts = []
        group_parts = []
        group_offset = 0

        if not args.no_wesad:
            wesad_data = load_wesad_dataset(
                args.datasets_dir,
                fs=args.fs,
                window_s=args.window_s,
                overlap=args.overlap,
            )
            if wesad_data is not None:
                X_wesad, y_wesad, g_wesad, summary = wesad_data
                X_parts.append(X_wesad)
                y_parts.append(y_wesad)
                group_parts.append(g_wesad)
                group_offset = int(g_wesad.max()) + 1
                print(
                    "Loaded WESAD | "
                    f"subjects={summary['subjects']} "
                    f"windows={summary['windows']} "
                    f"stress={summary['stress_windows']} "
                    f"non_stress={summary['non_stress_windows']}"
                )
            else:
                print("WESAD dataset not found or empty.")

        if not args.no_swell:
            swell_data = load_swell_dataset(
                args.datasets_dir,
                window_min=args.swell_window_min,
                overlap=args.overlap,
            )
            if swell_data is not None:
                X_swell, y_swell, g_swell, summary = swell_data
                g_swell = g_swell + group_offset
                X_parts.append(X_swell)
                y_parts.append(y_swell)
                group_parts.append(g_swell)
                group_offset = int(g_swell.max()) + 1
                print(
                    "Loaded SWELL | "
                    f"subjects={summary['subjects']} "
                    f"windows={summary['windows']} "
                    f"stress={summary['stress_windows']} "
                    f"non_stress={summary['non_stress_windows']}"
                )
            else:
                print("SWELL dataset not found or empty.")

        if not X_parts:
            print("No datasets loaded. Falling back to mock data.")
            X, y, groups = load_mock_dataset()
        else:
            X = np.vstack(X_parts)
            y = np.concatenate(y_parts)
            groups = np.concatenate(group_parts)
            print(
                "Combined | "
                f"subjects={len(np.unique(groups))} "
                f"windows={X.shape[0]} "
                f"stress={int(np.sum(y == 1))} "
                f"non_stress={int(np.sum(y == 0))}"
            )

    logo = LeaveOneGroupOut()

    print("Starting LOSO cross-validation...")
    for fold, (train_idx, test_idx) in enumerate(logo.split(X, y, groups=groups), start=1):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
            print(f"Subject {groups[test_idx][0]} | Fold {fold} skipped (single-class fold).")
            continue

        X_train_full, X_val, y_train_full, y_val = train_test_split(
            X_train,
            y_train,
            test_size=0.1,
            stratify=y_train,
            random_state=42,
        )

        # StandardScaler inside the loop (fit on train, transform on val/test)
        scaler = StandardScaler()
        X_train_full = scaler.fit_transform(X_train_full)
        X_val = scaler.transform(X_val)
        X_test = scaler.transform(X_test)

        model = build_tabnet()
        model.fit(
            X_train_full,
            y_train_full,
            eval_set=[(X_val, y_val)],
            eval_metric=["accuracy"],
            max_epochs=100,
            patience=10,
            batch_size=4096,
            virtual_batch_size=128,
            num_workers=0,
            drop_last=False,
        )

        y_pred = model.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, zero_division=0)

        subject_id = groups[test_idx][0]
        print(f"Subject {subject_id} | Fold {fold} | Accuracy: {acc:.4f} | F1: {f1:.4f}")

        # Generate explanations only for the first fold to keep runtime reasonable
        if fold == 1 and not args.skip_xai:
            generate_explanations(model, X_train_full, X_test, y_test)

    print("LOSO evaluation complete.")

    if not args.no_train_final:
        X_train_full, X_val, y_train_full, y_val = train_test_split(
            X,
            y,
            test_size=0.1,
            stratify=y,
            random_state=42,
        )

        scaler = StandardScaler()
        X_train_full = scaler.fit_transform(X_train_full)
        X_val = scaler.transform(X_val)

        final_model = build_tabnet()
        final_model.fit(
            X_train_full,
            y_train_full,
            eval_set=[(X_val, y_val)],
            eval_metric=["accuracy"],
            max_epochs=100,
            patience=10,
            batch_size=4096,
            virtual_batch_size=128,
            num_workers=0,
            drop_last=False,
        )

        os.makedirs(args.model_dir, exist_ok=True)
        model_path = os.path.join(args.model_dir, "tabnet_stress_model")
        scaler_path = os.path.join(args.model_dir, "tabnet_stress_scaler.joblib")

        final_model.save_model(model_path)
        joblib.dump(scaler, scaler_path)

        print(f"Saved final model to: {model_path}.zip")
        print(f"Saved scaler to: {scaler_path}")


if __name__ == "__main__":
    main()
