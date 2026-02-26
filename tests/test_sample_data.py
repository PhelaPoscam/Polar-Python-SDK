"""
Test suite for sample_data.py - Synthetic data generation
"""
import pytest
import pandas as pd
from pathlib import Path
from awe_polar.sample_data import generate_sample_data

class TestDataGeneration:
    """Test synthetic data generation"""

    def test_generate_sample_data_shape_and_columns(self):
        """Test the shape and columns of the generated DataFrame."""
        df = generate_sample_data(n_samples=100)
        assert df.shape == (100, 3)
        assert list(df.columns) == ["HR", "RMSSD", "label"]

    def test_generate_sample_data_ranges(self):
        """Test that the generated data is within the expected ranges."""
        df = generate_sample_data(n_samples=100)
        assert df["HR"].between(50, 120).all()
        assert df["RMSSD"].between(10, 80).all()
        assert df["label"].isin([0, 1]).all()

    def test_generate_sample_data_csv(self, tmp_path: Path):
        """Test that the data can be saved to a CSV file."""
        output_file = tmp_path / "sample_data.csv"
        generate_sample_data(n_samples=10, output_file=output_file)
        assert output_file.exists()
        df = pd.read_csv(output_file, sep=";")
        assert df.shape == (10, 3)

    def test_generate_sample_data_excel(self, tmp_path: Path):
        """Test that the data can be saved to an Excel file."""
        output_file = tmp_path / "sample_data.xlsx"
        generate_sample_data(n_samples=10, output_file=output_file)
        assert output_file.exists()
        df = pd.read_excel(output_file)
        assert df.shape == (10, 3)

    def test_generate_sample_data_parquet(self, tmp_path: Path):
        """Test that the data can be saved to a Parquet file."""
        output_file = tmp_path / "sample_data.parquet"
        generate_sample_data(n_samples=10, output_file=output_file)
        assert output_file.exists()
        df = pd.read_parquet(output_file)
        assert df.shape == (10, 3)
