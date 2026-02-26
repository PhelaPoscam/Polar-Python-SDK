"""
Unit tests for BLE Ring Streamer script.

Tests CSV logging, notification handling, and data validation.
"""

import pytest
from pathlib import Path
from scripts.ble.ble_ring_streamer import RingDataLogger, Notificationhandler


class TestRingDataLogger:
    """Tests for the RingDataLogger class."""
    
    def test_csv_logger_creates_file(self):
        """Test CSV file is created with headers."""
        log_file = Path('pytest_ring_data_1.csv')
        log_file.unlink(missing_ok=True)
        
        logger = RingDataLogger(str(log_file))
        
        assert log_file.exists(), "CSV file was not created"
        
        with open(log_file) as f:
            headers = f.readline().strip()
            assert "timestamp" in headers
            assert "raw_data_hex" in headers
            assert "raw_data_bytes" in headers
        
        log_file.unlink()
    
    def test_csv_logger_appends_data(self):
        """Test data is correctly written to CSV."""
        log_file = Path('pytest_ring_data_2.csv')
        log_file.unlink(missing_ok=True)
        
        logger = RingDataLogger(str(log_file))
        test_data = bytes([0xFF, 0xEE, 0xDD])
        
        logger.log_data(test_data)
        
        with open(log_file) as f:
            lines = f.readlines()
            assert len(lines) == 2, "Header + 1 data row expected"
            assert "ffeedd" in lines[1].lower(), "Hex data not found in CSV"
        
        log_file.unlink()
    
    def test_csv_logger_multiple_entries(self):
        """Test multiple data entries are appended correctly."""
        log_file = Path('pytest_ring_data_3.csv')
        log_file.unlink(missing_ok=True)
        
        logger = RingDataLogger(str(log_file))
        
        test_entries = [
            bytes([0x01, 0x02]),
            bytes([0x03, 0x04]),
            bytes([0x05, 0x06])
        ]
        
        for entry in test_entries:
            logger.log_data(entry)
        
        with open(log_file) as f:
            lines = f.readlines()
            assert len(lines) == 4, "Header + 3 data rows expected"
            assert "0102" in lines[1].lower()
            assert "0304" in lines[2].lower()
            assert "0506" in lines[3].lower()
        
        log_file.unlink()
    
    def test_csv_file_persistence(self):
        """Test that existing CSV file is reused."""
        log_file = Path('pytest_ring_data_4.csv')
        log_file.unlink(missing_ok=True)
        
        logger1 = RingDataLogger(str(log_file))
        logger1.log_data(bytes([0x11]))
        
        logger2 = RingDataLogger(str(log_file))
        logger2.log_data(bytes([0x22]))
        
        with open(log_file) as f:
            lines = f.readlines()
            assert len(lines) == 3, "Header + 2 data rows expected"
            assert "11" in lines[1].lower()
            assert "22" in lines[2].lower()
        
        log_file.unlink()


class TestNotificationHandler:
    """Tests for the Notificationhandler class."""
    
    def test_notification_handler_counts(self):
        """Test notification counter increments."""
        logger = RingDataLogger('pytest_handler_test.csv')
        handler = Notificationhandler(logger)
        
        assert handler.notification_count == 0
        
        handler.callback("uuid-1", bytes([0x01]))
        assert handler.notification_count == 1
        
        handler.callback("uuid-2", bytes([0x02]))
        assert handler.notification_count == 2
        
        Path('pytest_handler_test.csv').unlink()
    
    def test_notification_handler_data_types(self):
        """Test handler correctly processes different data types."""
        log_file = Path('pytest_handler_data.csv')
        log_file.unlink(missing_ok=True)
        
        logger = RingDataLogger(str(log_file))
        handler = Notificationhandler(logger)
        
        # Test various byte sequences
        test_cases = [
            bytes([0x00]),           # Single zero
            bytes([0xFF]),           # Single max
            bytes([0x41, 0x42, 0x43]),  # ASCII "ABC"
            bytes(range(256)),       # All possible byte values
        ]
        
        for data in test_cases:
            handler.callback("test-uuid", data)
        
        assert handler.notification_count == 4
        
        with open(log_file) as f:
            lines = f.readlines()
            assert len(lines) == 5  # Header + 4 data rows
        
        log_file.unlink()
    
    def test_notification_handler_csv_integration(self):
        """Test that callback data is correctly logged to CSV."""
        log_file = Path('pytest_handler_integration.csv')
        log_file.unlink(missing_ok=True)
        
        logger = RingDataLogger(str(log_file))
        handler = Notificationhandler(logger)
        
        test_data = bytes([0x78, 0x9A, 0xBC])
        handler.callback("heart-rate-uuid", test_data)
        
        with open(log_file) as f:
            lines = f.readlines()
            data_row = lines[1]
            
            # Verify CSV contains hex representation
            assert "789abc" in data_row.lower()
            # Verify CSV contains timestamp
            assert ":" in data_row  # HH:MM:SS format in timestamp
        
        log_file.unlink()


class TestDataValidation:
    """Tests for data validity and edge cases."""
    
    def test_empty_byte_sequence(self):
        """Test handling of empty byte data."""
        log_file = Path('pytest_empty.csv')
        log_file.unlink(missing_ok=True)
        
        logger = RingDataLogger(str(log_file))
        handler = Notificationhandler(logger)
        
        handler.callback("uuid", bytes([]))
        
        assert handler.notification_count == 1
        
        Path('pytest_empty.csv').unlink()
    
    def test_large_byte_sequence(self):
        """Test handling of large byte sequences."""
        log_file = Path('pytest_large.csv')
        log_file.unlink(missing_ok=True)
        
        logger = RingDataLogger(str(log_file))
        handler = Notificationhandler(logger)
        
        # Simulate a large sensor data packet (1KB)
        large_data = bytes(range(256)) * 4
        handler.callback("uuid", large_data)
        
        assert handler.notification_count == 1
        
        with open(log_file) as f:
            lines = f.readlines()
            data_row = lines[1]
            # Check that hex string is present
            assert len(data_row) > 1000  # Large hex string
        
        Path('pytest_large.csv').unlink()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
