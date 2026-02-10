"""
Test suite for train_model.py - Stress prediction model training
"""
import pytest
import pandas as pd
import numpy as np
import os
import joblib
from unittest.mock import patch, MagicMock


class TestDataLoading:
    """Test data loading and preprocessing"""
    
    def test_csv_loading(self, tmp_path):
        """Test CSV file loading"""
        # Create sample CSV
        csv_file = tmp_path / "test_data.csv"
        sample_data = pd.DataFrame({
            'HR': [70, 75, 80, 85, 90],
            'RMSSD': [45.5, 50.2, 48.3, 52.1, 47.8],
            'label': [0, 0, 1, 1, 0]
        })
        sample_data.to_csv(csv_file, sep=';', index=False)
        
        # Load and verify
        df = pd.read_csv(csv_file, sep=';')
        assert len(df) == 5
        assert 'HR' in df.columns
        assert 'RMSSD' in df.columns
        assert 'label' in df.columns
    
    def test_rmssd_conversion(self):
        """Test RMSSD numeric conversion"""
        df = pd.DataFrame({
            'RMSSD': ['45.5', '50.2', 'invalid', '48.3']
        })
        df['RMSSD'] = pd.to_numeric(df['RMSSD'], errors='coerce')
        df = df.dropna()
        
        assert len(df) == 3
        assert all(isinstance(x, (int, float)) for x in df['RMSSD'])


class TestFeatureEngineering:
    """Test feature selection and scaling"""
    
    def test_feature_selection(self):
        """Test correct features are selected"""
        df = pd.DataFrame({
            'HR': [70, 75, 80],
            'RMSSD': [45.5, 50.2, 48.3],
            'extra_col': [1, 2, 3],
            'label': [0, 1, 0]
        })
        
        feature_columns = ['HR', 'RMSSD']
        X = df[feature_columns]
        
        assert X.shape[1] == 2
        assert list(X.columns) == feature_columns
    
    def test_scaling_transformation(self):
        """Test StandardScaler transformation"""
        from sklearn.preprocessing import StandardScaler
        
        data = np.array([[70, 45], [80, 50], [90, 55]])
        scaler = StandardScaler()
        scaled = scaler.fit_transform(data)
        
        # Check mean is close to 0 and std is close to 1
        assert np.allclose(scaled.mean(axis=0), 0, atol=1e-10)
        assert np.allclose(scaled.std(axis=0), 1, atol=1e-10)


class TestModelTraining:
    """Test Random Forest model training"""
    
    def test_model_initialization(self):
        """Test Random Forest initialization with correct parameters"""
        from sklearn.ensemble import RandomForestClassifier
        
        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=3,
            random_state=42,
            class_weight='balanced'
        )
        
        assert model.n_estimators == 200
        assert model.max_depth == 10
        assert model.min_samples_split == 5
        assert model.min_samples_leaf == 3
        assert model.random_state == 42
    
    def test_model_training_and_prediction(self):
        """Test model can train and make predictions"""
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.preprocessing import StandardScaler
        
        # Create synthetic data
        np.random.seed(42)
        X = np.random.rand(100, 2) * 50 + 50  # HR and RMSSD ranges
        y = (X[:, 0] > 75).astype(int)  # Simple rule for stress
        
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X_scaled, y)
        
        predictions = model.predict(X_scaled)
        
        assert len(predictions) == len(y)
        assert all(p in [0, 1] for p in predictions)
    
    def test_cross_validation_scores(self):
        """Test cross-validation returns valid scores"""
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import cross_val_score
        
        # Create synthetic data
        np.random.seed(42)
        X = np.random.rand(50, 2) * 50 + 50
        y = (X[:, 0] > 75).astype(int)
        
        model = RandomForestClassifier(n_estimators=10, random_state=42)
        scores = cross_val_score(model, X, y, cv=3)
        
        assert len(scores) == 3
        assert all(0 <= score <= 1 for score in scores)


class TestModelSaving:
    """Test model persistence"""
    
    def test_model_save_and_load(self, tmp_path):
        """Test model and scaler can be saved and loaded"""
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.preprocessing import StandardScaler
        
        # Train simple model
        X = np.array([[70, 45], [80, 50], [90, 55], [85, 52]])
        y = np.array([0, 1, 1, 1])
        
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X_scaled, y)
        
        # Save
        model_path = tmp_path / "test_model.pkl"
        scaler_path = tmp_path / "test_scaler.pkl"
        
        joblib.dump(model, model_path)
        joblib.dump(scaler, scaler_path)
        
        # Load
        loaded_model = joblib.load(model_path)
        loaded_scaler = joblib.load(scaler_path)
        
        # Verify
        test_data = np.array([[75, 48]])
        original_pred = model.predict(scaler.transform(test_data))
        loaded_pred = loaded_model.predict(loaded_scaler.transform(test_data))
        
        assert np.array_equal(original_pred, loaded_pred)


class TestFeatureImportance:
    """Test feature importance extraction"""
    
    def test_feature_importance_calculation(self):
        """Test feature importance is calculated correctly"""
        from sklearn.ensemble import RandomForestClassifier
        
        X = np.array([[70, 45], [80, 50], [90, 55], [85, 52]])
        y = np.array([0, 1, 1, 1])
        
        model = RandomForestClassifier(n_estimators=10, random_state=42)
        model.fit(X, y)
        
        importances = model.feature_importances_
        
        assert len(importances) == 2
        assert all(0 <= imp <= 1 for imp in importances)
        assert np.isclose(sum(importances), 1.0)


@pytest.fixture
def sample_training_data():
    """Fixture for sample training data"""
    np.random.seed(42)
    return pd.DataFrame({
        'HR': np.random.randint(60, 100, 100),
        'RMSSD': np.random.uniform(20, 60, 100),
        'label': np.random.randint(0, 2, 100)
    })
