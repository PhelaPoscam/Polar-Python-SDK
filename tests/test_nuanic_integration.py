"""
Tests for Nuanic ring integration modules

pytest test_nuanic_integration.py -v
"""
import pytest
import asyncio
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
import struct
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from awe_polar.nuanic_ring import NuanicConnector, NuanicMonitor, NuanicDataLogger
from awe_polar.nuanic_ring.eda_analyzer import NuanicEDAAnalyzer


class TestNuanicConnector:
    """Tests for BLE connection management"""
    
    def test_connector_initialization(self):
        """Test connector can be instantiated"""
        connector = NuanicConnector()
        assert connector is not None
        assert connector.timeout == 15.0
        assert connector.max_scan_attempts == 3
        assert connector.client is None
        assert connector.device is None
    
    def test_connector_custom_timeout(self):
        """Test connector with custom timeout"""
        connector = NuanicConnector(timeout=30.0, max_scan_attempts=5)
        assert connector.timeout == 30.0
        assert connector.max_scan_attempts == 5
    
    def test_battery_characteristic_uuid(self):
        """Verify battery characteristic UUID"""
        connector = NuanicConnector()
        assert connector.BATTERY_CHARACTERISTIC == "00002a19-0000-1000-8000-00805f9b34fb"
    
    def test_stress_characteristic_uuid(self):
        """Verify stress characteristic UUID"""
        connector = NuanicConnector()
        assert connector.STRESS_CHARACTERISTIC == "468f2717-6a7d-46f9-9eb7-f92aab208bae"


class TestNuanicMonitor:
    """Tests for real-time stress monitoring"""
    
    def test_monitor_initialization(self):
        """Test monitor can be instantiated"""
        monitor = NuanicMonitor()
        assert monitor is not None
        assert monitor.connector is not None
        assert monitor.current_stress is None
        assert monitor.current_eda_raw is None
    
    def test_parse_stress_packet_basic(self):
        """Test parsing a basic 92-byte stress packet"""
        monitor = NuanicMonitor()
        
        # Create mock packet with stress at byte 14
        packet = bytearray(92)
        packet[14] = 127  # 50% stress
        
        result = monitor.parse_stress_packet(packet)
        
        assert result is not None
        assert result['stress_raw'] == 127
        assert abs(result['stress_percent'] - 49.8) < 0.1
        assert 'timestamp' in result
        assert 'eda_raw' in result
        assert 'full_data' in result
    
    def test_parse_stress_packet_boundaries(self):
        """Test stress parsing at boundary values"""
        monitor = NuanicMonitor()
        
        # Test minimum (0%)
        packet_min = bytearray(92)
        packet_min[14] = 0
        result_min = monitor.parse_stress_packet(packet_min)
        assert result_min['stress_percent'] == 0.0
        
        # Test maximum (100%)
        packet_max = bytearray(92)
        packet_max[14] = 255
        result_max = monitor.parse_stress_packet(packet_max)
        assert abs(result_max['stress_percent'] - 100.0) < 0.1
    
    def test_parse_stress_packet_mid_range(self):
        """Test various mid-range stress values"""
        monitor = NuanicMonitor()
        
        test_cases = [
            (32, 12.5),      # 25% area
            (64, 25.1),      # 25% area
            (128, 50.2),     # midpoint
            (192, 75.3),     # 75% area
            (224, 87.8),     # high stress
        ]
        
        for raw_val, expected_percent in test_cases:
            packet = bytearray(92)
            packet[14] = raw_val
            result = monitor.parse_stress_packet(packet)
            assert abs(result['stress_percent'] - expected_percent) < 1.0, \
                f"Raw {raw_val} should be ~{expected_percent}%, got {result['stress_percent']:.1f}%"
    
    def test_parse_stress_packet_eda_extraction(self):
        """Test EDA data extraction (bytes 15-91)"""
        monitor = NuanicMonitor()
        
        packet = bytearray(92)
        packet[14] = 100  # stress value
        
        # Set some data in EDA section
        packet[15] = 0xAA
        packet[16] = 0xBB
        packet[91] = 0xFF
        
        result = monitor.parse_stress_packet(packet)
        
        # EDA should be hex representation of bytes 15-91
        assert result['eda_raw'].startswith('aabb')
        assert result['eda_raw'].endswith('ff')
        assert len(result['eda_raw']) == 77 * 2  # 77 bytes = 154 hex chars
    
    def test_parse_stress_packet_undersized(self):
        """Test handling of undersized packets"""
        monitor = NuanicMonitor()
        
        small_packet = bytearray(10)  # Too small
        result = monitor.parse_stress_packet(small_packet)
        
        assert result is None
    
    def test_parse_stress_packet_exact_minimum(self):
        """Test packet at minimum size needed (15 bytes for stress at [14])"""
        monitor = NuanicMonitor()
        
        min_packet = bytearray(15)
        min_packet[14] = 127
        
        result = monitor.parse_stress_packet(min_packet)
        assert result is not None
        assert result['stress_raw'] == 127
    
    def test_notification_callback(self):
        """Test notification callback updates current values"""
        monitor = NuanicMonitor()
        
        packet = bytearray(92)
        packet[14] = 150  # stress
        packet[15] = 0x12  # EDA start
        packet[16] = 0x34
        
        monitor.notification_callback("sender", packet)
        
        assert monitor.current_stress is not None
        assert abs(monitor.current_stress - 58.8) < 0.1
        assert monitor.current_eda_raw is not None
        assert monitor.current_eda_raw.startswith('1234')
    
    def test_get_current_stress(self):
        """Test retrieving current stress"""
        monitor = NuanicMonitor()
        
        assert monitor.get_current_stress() is None
        
        packet = bytearray(92)
        packet[14] = 100
        monitor.notification_callback("sender", packet)
        
        stress = monitor.get_current_stress()
        assert abs(stress - 39.2) < 0.1
    
    def test_get_current_eda(self):
        """Test retrieving current EDA"""
        monitor = NuanicMonitor()
        
        assert monitor.get_current_eda() is None
        
        packet = bytearray(92)
        packet[15:20] = b'\x01\x02\x03\x04\x05'
        monitor.notification_callback("sender", packet)
        
        eda = monitor.get_current_eda()
        assert eda is not None
        assert eda.startswith('01020304')


class TestNuanicDataLogger:
    """Tests for CSV data logging"""
    
    def test_logger_initialization(self):
        """Test logger can be instantiated"""
        logger = NuanicDataLogger()
        assert logger is not None
        assert logger.log_dir.exists()
        assert logger.connector is not None
        assert logger.row_count == 0
    
    def test_logger_custom_directory(self):
        """Test logger with custom directory"""
        custom_dir = "data/test_nuanic_logs"
        logger = NuanicDataLogger(log_dir=custom_dir)
        # Normalize paths for cross-platform compatibility
        assert str(logger.log_dir).replace("\\", "/") == custom_dir
    
    def test_logger_creates_correct_file_format(self):
        """Test that CSV file follows expected naming convention"""
        logger = NuanicDataLogger()
        logger._create_log_file()
        
        filename = logger.csv_file.name
        
        # Should match: nuanic_YYYY-MM-DD_HH-MM-SS.csv
        assert filename.startswith("nuanic_")
        assert filename.endswith(".csv")
    
    def test_logger_csv_headers(self):
        """Test CSV file has correct headers"""
        import tempfile
        import csv
        
        logger = NuanicDataLogger()
        logger._create_log_file()
        
        with open(logger.csv_file, 'r') as f:
            reader = csv.reader(f)
            headers = next(reader)
        
        expected_headers = [
            'timestamp',
            'stress_raw',
            'stress_percent',
            'eda_hex',
            'full_packet_hex'
        ]
        
        assert headers == expected_headers
    
    def test_logger_notification_callback(self):
        """Test logging a notification"""
        logger = NuanicDataLogger()
        logger._create_log_file()
        
        packet = bytearray(92)
        packet[14] = 100
        packet[15:20] = b'\xAA\xBB\xCC\xDD\xEE'
        
        logger.notification_callback("sender", packet)
        
        assert logger.row_count == 1
        
        # Verify data was written
        with open(logger.csv_file, 'r') as f:
            lines = f.readlines()
        
        assert len(lines) == 2  # header + 1 data row
    
    def test_logger_multiple_notifications(self):
        """Test logging multiple notifications"""
        logger = NuanicDataLogger()
        logger._create_log_file()
        
        for i in range(10):
            packet = bytearray(92)
            packet[14] = 50 + i
            logger.notification_callback("sender", packet)
        
        assert logger.row_count == 10


class TestNuanicEDAAnalyzer:
    """Tests for EDA analysis"""
    
    def test_analyzer_initialization(self):
        """Test analyzer can be instantiated"""
        analyzer = NuanicEDAAnalyzer()
        assert analyzer is not None
        assert analyzer.baseline is None
        assert len(analyzer.eda_history) == 0
    
    def test_update_baseline_initial(self):
        """Test initial baseline setting"""
        analyzer = NuanicEDAAnalyzer()
        
        analyzer.update_baseline(100.0)
        
        assert analyzer.baseline == 100.0
    
    def test_update_baseline_exponential_moving_average(self):
        """Test baseline updates with exponential moving average"""
        analyzer = NuanicEDAAnalyzer()
        analyzer.baseline = 100.0
        
        # New reading: 110
        analyzer.update_baseline(110.0)
        alpha = 0.02
        expected = alpha * 110.0 + (1 - alpha) * 100.0
        
        assert abs(analyzer.baseline - expected) < 0.01
    
    def test_add_reading(self):
        """Test adding EDA readings"""
        analyzer = NuanicEDAAnalyzer()
        
        stats = analyzer.add_reading(100.0)
        
        assert stats is not None
        assert stats['current_value'] == 100.0
        assert 'baseline' in stats
        assert 'phasic' in stats
        assert 'is_peak' in stats
        assert len(analyzer.eda_history) == 1
    
    def test_eda_history_limit(self):
        """Test that EDA history is limited to 60 readings"""
        analyzer = NuanicEDAAnalyzer()
        
        # Add 100 readings
        for i in range(100):
            analyzer.add_reading(100.0 + i % 10)
        
        # Should only have 60
        assert len(analyzer.eda_history) <= 60
    
    def test_baseline_vs_phasic(self):
        """Test baseline and phasic component calculation"""
        analyzer = NuanicEDAAnalyzer()
        
        # Add stable readings to set baseline
        for _ in range(20):
            analyzer.add_reading(100.0)
        
        baseline_before = analyzer.baseline
        
        # Add a spike
        stats = analyzer.add_reading(150.0)
        
        # Baseline may have drifted slightly due to exponential moving average
        assert abs(stats['baseline'] - baseline_before) < 2.0
        assert stats['phasic'] > 0  # Phasic component is positive (above baseline)
    
    def test_peak_detection_threshold(self):
        """Test peak detection responds to large changes"""
        analyzer = NuanicEDAAnalyzer()
        
        # Establish baseline
        for _ in range(20):
            analyzer.add_reading(100.0)
        
        baseline = analyzer.baseline
        
        # Large spike
        stats = analyzer.add_reading(baseline + 50)
        assert stats['is_peak'] is True
        
        # Small change
        stats = analyzer.add_reading(baseline + 1)
        assert stats['is_peak'] is False
    
    def test_analyze_session(self):
        """Test session-level analysis"""
        analyzer = NuanicEDAAnalyzer()
        
        # Create test session with peaks
        readings = []
        base_time = datetime.now()
        
        for i in range(30):
            timestamp = base_time
            if i < 10:
                value = 100.0
            elif i < 15:
                value = 130.0  # Peak
            else:
                value = 105.0  # Recovery
            
            readings.append((timestamp, value))
        
        stats = analyzer.analyze_session(readings)
        
        assert stats is not None
        assert stats['reading_count'] == 30
        assert 'min_value' in stats
        assert 'max_value' in stats
        assert 'mean_value' in stats
        assert 'peak_count' in stats
    
    def test_analyze_empty_session(self):
        """Test analysis with empty session"""
        analyzer = NuanicEDAAnalyzer()
        
        stats = analyzer.analyze_session([])
        
        assert stats is None
    
    def test_interpretation_high_arousal(self):
        """Test interpretation identifies high arousal"""
        analyzer = NuanicEDAAnalyzer()
        
        stats = {
            'duration_seconds': 60,
            'reading_count': 60,
            'min_value': 100,
            'max_value': 160,
            'mean_value': 120,
            'range': 60,  # > 50 for LARGE range
            'peak_count': 20,
            'peaks_per_minute': 20.0
        }
        
        interpretation = analyzer.get_interpretation(stats)
        
        assert 'HIGH emotional reactivity' in interpretation
        assert 'LARGE dynamic range' in interpretation
    
    def test_interpretation_low_arousal(self):
        """Test interpretation identifies low arousal"""
        analyzer = NuanicEDAAnalyzer()
        
        stats = {
            'duration_seconds': 60,
            'reading_count': 60,
            'min_value': 100,
            'max_value': 110,
            'mean_value': 105,
            'range': 10,
            'peak_count': 1,
            'peaks_per_minute': 1.0
        }
        
        interpretation = analyzer.get_interpretation(stats)
        
        assert 'LOW emotional reactivity' in interpretation
        assert 'SMALL dynamic range' in interpretation


class TestDataIntegration:
    """Integration tests for data flow"""
    
    def test_stress_raw_to_percent_conversion(self):
        """Test stress value conversion across modules"""
        monitor = NuanicMonitor()
        
        # Test multiple conversions
        conversions = [
            (0, 0.0),
            (64, 25.1),
            (128, 50.2),
            (192, 75.3),
            (255, 100.0),
        ]
        
        for raw, expected_percent in conversions:
            packet = bytearray(92)
            packet[14] = raw
            result = monitor.parse_stress_packet(packet)
            actual = result['stress_percent']
            assert abs(actual - expected_percent) < 1.0
    
    def test_eda_hex_format_consistency(self):
        """Test EDA hex encoding is consistent"""
        monitor = NuanicMonitor()
        
        packet1 = bytearray(92)
        packet1[15] = 0xAB
        packet1[16] = 0xCD
        packet1[17] = 0xEF
        
        result = monitor.parse_stress_packet(packet1)
        eda_hex = result['eda_raw']
        
        # Should be lowercase hex starting with abcdef
        assert eda_hex.startswith('abcdef')
        assert all(c in '0123456789abcdef' for c in eda_hex)


# Async test fixtures
@pytest.fixture
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Test data fixtures
@pytest.fixture
def mock_stress_packet():
    """Create a mock 92-byte stress packet"""
    packet = bytearray(92)
    packet[14] = 100  # Stress 39.2%
    return packet


@pytest.fixture
def mock_eda_packet():
    """Create a mock packet with EDA data"""
    packet = bytearray(92)
    packet[14] = 100  # Stress
    
    # Fill EDA section with test data
    for i in range(15, 92):
        packet[i] = (i % 256)
    
    return packet
