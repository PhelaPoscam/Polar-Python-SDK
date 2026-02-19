"""
Configuration for pytest
"""
import pytest
import sys
import os

# Add project root and src to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
src_root = os.path.join(project_root, "src")
sys.path.insert(0, project_root)
sys.path.insert(0, src_root)


@pytest.fixture(scope="session")
def test_data_dir(tmp_path_factory):
    """Create a temporary directory for test data"""
    return tmp_path_factory.mktemp("test_data")


@pytest.fixture
def sample_csv_data():
    """Sample CSV data for testing"""
    return """HR;RMSSD;label
70;45.5;0
75;50.2;0
80;35.3;1
85;30.1;1
72;48.7;0
88;28.5;1
73;52.1;0
90;25.8;1
"""


@pytest.fixture(autouse=True)
def reset_matplotlib():
    """Reset matplotlib after each test to prevent memory leaks"""
    import matplotlib.pyplot as plt
    yield
    plt.close('all')
