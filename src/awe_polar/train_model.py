from __future__ import annotations

import argparse
import datetime
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import cross_val_score, train_test_split, GridSearchCV
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "all_hrv_data3.csv"
MODEL_PATH = PROJECT_ROOT / "models"
SCALER_PATH = PROJECT_ROOT / "models"

FEATURE_COLUMNS = ["HR", "RMSSD"]


def load_dataset(data_path: Path) -> pd.DataFrame:
    """Load and preprocess the dataset from the given path.

    Args:
        data_path: The path to the dataset file.

    Returns:
        The preprocessed DataFrame.
    """
    if data_path.suffix == ".csv":
        df = pd.read_csv(data_path, sep=";")
    elif data_path.suffix == ".xlsx":
        df = pd.read_excel(data_path)
    elif data_path.suffix == ".parquet":
        df = pd.read_parquet(data_path)
    else:
        raise ValueError(f"Unsupported file format: {data_path.suffix}")

    df["RMSSD"] = pd.to_numeric(df["RMSSD"], errors="coerce")
    df = df.dropna()

    # Outlier removal using IQR
    for col in FEATURE_COLUMNS:
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        df = df[(df[col] >= lower_bound) & (df[col] <= upper_bound)]

    return df


def tune_hyperparameters(model_name: str, X_train: np.ndarray, y_train: np.ndarray) -> dict:
    """
    Tune hyperparameters for the specified model using GridSearchCV.
    """
    if model_name == "random_forest":
        param_grid = {
            "n_estimators": [100, 200, 300],
            "max_depth": [10, 20, None],
            "min_samples_split": [2, 5, 10],
            "min_samples_leaf": [1, 2, 4],
        }
        model = RandomForestClassifier(random_state=42, class_weight="balanced")
    elif model_name == "gradient_boosting":
        param_grid = {
            "n_estimators": [100, 200, 300],
            "max_depth": [3, 5, 10],
            "learning_rate": [0.01, 0.1, 0.2],
        }
        model = GradientBoostingClassifier(random_state=42)
    else:
        raise ValueError(f"Unsupported model: {model_name}")

    grid_search = GridSearchCV(
        estimator=model, param_grid=param_grid, cv=5, n_jobs=-1, verbose=2
    )
    grid_search.fit(X_train, y_train)

    print(f"Best parameters for {model_name}: {grid_search.best_params_}")
    return grid_search.best_params_


def train_model(
    df: pd.DataFrame,
    model_name: str = "random_forest",
    best_params: dict | None = None,
) -> tuple[RandomForestClassifier | GradientBoostingClassifier, StandardScaler]:
    """Train the stress detection model.

    Args:
        df: The preprocessed DataFrame.
        model_name: The name of the model to train.
        best_params: The best hyperparameters for the model.

    Returns:
        A tuple containing the trained model and the scaler.
    """
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

    if best_params:
        print(f"\nUsing tuned parameters: {best_params}")
    else:
        print("\nUsing default parameters.")

    if model_name == "random_forest":
        params = best_params or {
            "n_estimators": 200,
            "max_depth": 10,
            "min_samples_split": 5,
            "min_samples_leaf": 3,
            "random_state": 42,
            "class_weight": "balanced",
        }
        model = RandomForestClassifier(**params)
    elif model_name == "gradient_boosting":
        params = best_params or {
            "n_estimators": 200,
            "max_depth": 10,
            "min_samples_split": 5,
            "min_samples_leaf": 3,
            "random_state": 42,
        }
        model = GradientBoostingClassifier(**params)
    else:
        raise ValueError(f"Unsupported model: {model_name}")

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
    model: object,
    scaler: StandardScaler,
    model_path: Path = MODEL_PATH,
    scaler_path: Path = SCALER_PATH,
) -> None:
    """Save the trained model and scaler to disk.

    Args:
        model: The trained model.
        scaler: The scaler used for preprocessing.
        model_path: The path to save the model.
        scaler_path: The path to save the scaler.
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    model_filename = f"stress_model_{timestamp}.pkl"
    scaler_filename = f"scaler_{timestamp}.pkl"

    model_path.mkdir(parents=True, exist_ok=True)
    scaler_path.mkdir(parents=True, exist_ok=True)

    model_filepath = model_path / model_filename
    scaler_filepath = scaler_path / scaler_filename

    joblib.dump(model, model_filepath)
    joblib.dump(scaler, scaler_filepath)

    print(f"\nModel saved as '{model_filepath}'")
    print(f"Scaler saved as '{scaler_filepath}'")


def main() -> None:
    """Main function to train the stress detection model."""
    parser = argparse.ArgumentParser(description="Train a stress detection model.")
    parser.add_argument(
        "--model-name",
        type=str,
        default="random_forest",
        choices=["random_forest", "gradient_boosting"],
        help="The name of the model to train.",
    )
    parser.add_argument(
        "--tune",
        action="store_true",
        help="Whether to perform hyperparameter tuning.",
    )
    args = parser.parse_args()

    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found at {DATA_PATH}. "
            "Place your CSV in data/raw/ or update DATA_PATH."
        )

    df = load_dataset(DATA_PATH)

    best_params = {}
    if args.tune:
        X = df[FEATURE_COLUMNS]
        y = df["label"]
        X_train, _, y_train, _ = train_test_split(
            X, y, test_size=0.3, random_state=42, stratify=y
        )
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        best_params = tune_hyperparameters(args.model_name, X_train_scaled, y_train)

    model, scaler = train_model(
        df, model_name=args.model_name, best_params=best_params
    )
    save_artifacts(model, scaler)


if __name__ == "__main__":
    main()