from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "raw" / "all_hrv_data3.csv"


def generate_sample_data(n_samples: int = 1000, output_file: Path | str = DEFAULT_OUTPUT) -> pd.DataFrame:
    """
    Generate synthetic heart rate and RMSSD data for stress detection.
    """
    output_path = Path(output_file)
    np.random.seed(42)

    n_no_stress = n_samples // 2
    n_stress = n_samples - n_no_stress

    hr_no_stress = np.random.normal(70, 8, n_no_stress)
    rmssd_no_stress = np.random.normal(48, 10, n_no_stress)
    label_no_stress = np.zeros(n_no_stress, dtype=int)

    hr_stress = np.random.normal(88, 10, n_stress)
    rmssd_stress = np.random.normal(28, 8, n_stress)
    label_stress = np.ones(n_stress, dtype=int)

    hr = np.concatenate([hr_no_stress, hr_stress])
    rmssd = np.concatenate([rmssd_no_stress, rmssd_stress])
    label = np.concatenate([label_no_stress, label_stress])

    df = pd.DataFrame(
        {
            "HR": hr.clip(50, 120),
            "RMSSD": rmssd.clip(10, 80),
            "label": label,
        }
    )

    df = df.sample(frac=1, random_state=42).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, sep=";", index=False)

    print(f"✓ Generated {n_samples} samples")
    print(f"✓ Saved to '{output_path}'")
    print("\nDataset Statistics:")
    print(f"  Total samples: {len(df)}")
    print(f"  No stress samples: {(df['label'] == 0).sum()}")
    print(f"  Stress samples: {(df['label'] == 1).sum()}")
    print("\nFeature Ranges:")
    print(f"  HR: {df['HR'].min():.1f} - {df['HR'].max():.1f} bpm")
    print(f"  RMSSD: {df['RMSSD'].min():.1f} - {df['RMSSD'].max():.1f} ms")

    return df


def main() -> None:
    print("Generating sample HRV data for AWE Polar Project...\n")
    generate_sample_data(n_samples=1000)
    print("\n✓ Sample data generation complete!")
    print("\nYou can now run: python scripts/train_model.py")


if __name__ == "__main__":
    main()
