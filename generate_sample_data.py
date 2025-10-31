"""
Sample data generator for testing the AWE Polar Project
Creates synthetic HRV data for model training when real data is not available
"""
import pandas as pd
import numpy as np

def generate_sample_data(n_samples=1000, output_file='all_hrv_data3.csv'):
    """
    Generate synthetic heart rate and RMSSD data for stress detection
    
    Parameters:
    -----------
    n_samples : int
        Number of samples to generate
    output_file : str
        Output CSV filename
    
    Returns:
    --------
    pd.DataFrame
        Generated data
    """
    np.random.seed(42)
    
    # Generate data for two classes
    n_no_stress = n_samples // 2
    n_stress = n_samples - n_no_stress
    
    # No stress: Lower HR, higher RMSSD
    hr_no_stress = np.random.normal(70, 8, n_no_stress)  # Mean 70, std 8
    rmssd_no_stress = np.random.normal(48, 10, n_no_stress)  # Mean 48, std 10
    label_no_stress = np.zeros(n_no_stress, dtype=int)
    
    # Stress: Higher HR, lower RMSSD
    hr_stress = np.random.normal(88, 10, n_stress)  # Mean 88, std 10
    rmssd_stress = np.random.normal(28, 8, n_stress)  # Mean 28, std 8
    label_stress = np.ones(n_stress, dtype=int)
    
    # Combine data
    hr = np.concatenate([hr_no_stress, hr_stress])
    rmssd = np.concatenate([rmssd_no_stress, rmssd_stress])
    label = np.concatenate([label_no_stress, label_stress])
    
    # Create DataFrame
    df = pd.DataFrame({
        'HR': hr.clip(50, 120),  # Realistic HR range
        'RMSSD': rmssd.clip(10, 80),  # Realistic RMSSD range
        'label': label
    })
    
    # Shuffle the data
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    
    # Save to CSV with semicolon delimiter
    df.to_csv(output_file, sep=';', index=False)

    print(f"✓ Generated {n_samples} samples")
    print(f"✓ Saved to '{output_file}'")
    print("\nDataset Statistics:")
    print(f"  Total samples: {len(df)}")
    print(f"  No stress samples: {(df['label'] == 0).sum()}")
    print(f"  Stress samples: {(df['label'] == 1).sum()}")
    print("\nFeature Ranges:")
    print(f"  HR: {df['HR'].min():.1f} - {df['HR'].max():.1f} bpm")
    print(f"  RMSSD: {df['RMSSD'].min():.1f} - {df['RMSSD'].max():.1f} ms")
    
    return df


if __name__ == "__main__":
    print("Generating sample HRV data for AWE Polar Project...\n")
    df = generate_sample_data(n_samples=1000)
    print("\n✓ Sample data generation complete!")
    print("\nYou can now run: python ML_model3.py")
