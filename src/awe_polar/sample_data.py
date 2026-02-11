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


    if output_path.suffix == ".csv":


        df.to_csv(output_path, sep=";", index=False)


    elif output_path.suffix == ".xlsx":


        df.to_excel(output_path, index=False)


    elif output_path.suffix == ".parquet":


        df.to_parquet(output_path, index=False)


    else:


        raise ValueError(f"Unsupported file format: {output_path.suffix}")





    print(f"Generated {n_samples} samples")
    print(f"Saved to '{output_path}'")
    print("\nDataset Statistics:")
    print(f"  Total samples: {len(df)}")
    print(f"  No stress samples: {(df['label'] == 0).sum()}")
    print(f"  Stress samples: {(df['label'] == 1).sum()}")
    print("\nFeature Ranges:")
    print(f"  HR: {df['HR'].min():.1f} - {df['HR'].max():.1f} bpm")
    print(f"  RMSSD: {df['RMSSD'].min():.1f} - {df['RMSSD'].max():.1f} ms")





    return df


import argparse

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sample HRV data for AWE Polar Project.")
    parser.add_argument(
        "--output-file",
        type=str,
        default=DEFAULT_OUTPUT,
        help=f"Output file path. Supported formats: .csv, .xlsx, .parquet. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--n-samples",
        type=int,
        default=1000,
        help="Number of samples to generate. Default: 1000",
    )
    args = parser.parse_args()

    print(f"Generating sample HRV data for AWE Polar Project...\n")
    generate_sample_data(n_samples=args.n_samples, output_file=args.output_file)
    print("\nSample data generation complete!")
    print("\nYou can now run: python scripts/train_model.py")



if __name__ == "__main__":
    main()
