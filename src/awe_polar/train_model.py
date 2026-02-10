from __future__ import annotations

from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "all_hrv_data3.csv"
MODEL_PATH = PROJECT_ROOT / "models" / "improved_stress_model.pkl"
SCALER_PATH = PROJECT_ROOT / "models" / "scaler.pkl"

FEATURE_COLUMNS = ["HR", "RMSSD"]


def load_dataset(data_path: Path) -> pd.DataFrame:
    df = pd.read_csv(data_path, sep=";")
    df["RMSSD"] = pd.to_numeric(df["RMSSD"], errors="coerce")
    df = df.dropna()
    return df


def train_model(data_path: Path = DATA_PATH) -> tuple[RandomForestClassifier, StandardScaler]:
    df = load_dataset(data_path)

    print(f"Dataset shape: {df.shape}")
    print(f"Label distribution:\n{df['label'].value_counts()}")

    X = df[FEATURE_COLUMNS]
    y = df["label"]

    print(f"Using {len(FEATURE_COLUMNS)} features: {FEATURE_COLUMNS}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    print("\nTraining Model (Random Forest)...")

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=10,
        min_samples_split=5,
        min_samples_leaf=3,
        random_state=42,
        class_weight="balanced",
    )

    cv_scores = cross_val_score(model, X_train_scaled, y_train, cv=5)
    print(f"Cross-validation mean: {cv_scores.mean():.3f}")

    model.fit(X_train_scaled, y_train)

    y_pred = model.predict(X_test_scaled)
    accuracy = accuracy_score(y_test, y_pred)
    print(f"\nModel Accuracy: {accuracy:.3f}")

    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=["no stress", "stress"]))

    feature_importance = pd.DataFrame(
        {
            "feature": FEATURE_COLUMNS,
            "importance": model.feature_importances_,
        }
    ).sort_values("importance", ascending=False)

    print("\nFeature Importance:")
    print(feature_importance)

    plt.figure(figsize=(10, 6))
    sns.barplot(data=feature_importance, x="importance", y="feature")
    plt.title("Feature Importance for Stress Prediction")
    plt.tight_layout()
    plt.show()

    return model, scaler


def save_artifacts(
    model: RandomForestClassifier,
    scaler: StandardScaler,
    model_path: Path = MODEL_PATH,
    scaler_path: Path = SCALER_PATH,
) -> None:
    model_path.parent.mkdir(parents=True, exist_ok=True)
    scaler_path.parent.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)

    print(f"\nModel saved as '{model_path}'")
    print(f"Scaler saved as '{scaler_path}'")


def main() -> None:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found at {DATA_PATH}. "
            "Place your CSV in data/raw/ or update DATA_PATH."
        )

    model, scaler = train_model(DATA_PATH)
    save_artifacts(model, scaler, MODEL_PATH, SCALER_PATH)


if __name__ == "__main__":
    main()
