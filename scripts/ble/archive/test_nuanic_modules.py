#!/usr/bin/env python3
"""
Test Nuanic ring integration modules

Verifies that all modules can be imported and basic functions work.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

print("=" * 80)
print("NUANIC RING INTEGRATION - MODULE TEST")
print("=" * 80)
print()

# Test 1: Import modules
print("[TEST 1] Module imports...")
try:
    from awe_polar.nuanic_ring import NuanicConnector, NuanicMonitor, NuanicDataLogger
    print("  ✓ Core modules imported successfully")
except ImportError as e:
    print(f"  ✗ Failed to import core modules: {e}")
    sys.exit(1)

try:
    from awe_polar.nuanic_ring.eda_analyzer import NuanicEDAAnalyzer
    print("  ✓ EDA analyzer imported successfully")
except ImportError as e:
    print(f"  ✗ Failed to import EDA analyzer: {e}")
    sys.exit(1)

print()

# Test 2: Verify class instantiation
print("[TEST 2] Class instantiation...")
try:
    connector = NuanicConnector()
    print(f"  ✓ NuanicConnector created")
except Exception as e:
    print(f"  ✗ Failed to create NuanicConnector: {e}")
    sys.exit(1)

try:
    monitor = NuanicMonitor()
    print(f"  ✓ NuanicMonitor created")
except Exception as e:
    print(f"  ✗ Failed to create NuanicMonitor: {e}")
    sys.exit(1)

try:
    logger = NuanicDataLogger()
    print(f"  ✓ NuanicDataLogger created")
except Exception as e:
    print(f"  ✗ Failed to create NuanicDataLogger: {e}")
    sys.exit(1)

try:
    analyzer = NuanicEDAAnalyzer()
    print(f"  ✓ NuanicEDAAnalyzer created")
except Exception as e:
    print(f"  ✗ Failed to create NuanicEDAAnalyzer: {e}")
    sys.exit(1)

print()

# Test 3: Test stress packet parsing
print("[TEST 3] Stress packet parsing...")
try:
    # Create mock 92-byte packet
    mock_packet = bytearray(92)
    mock_packet[14] = 127  # Stress value (50%)
    
    # Parse with monitor
    result = monitor.parse_stress_packet(mock_packet)
    expected_stress = (127 / 255) * 100
    
    if result and abs(result['stress_percent'] - expected_stress) < 0.1:
        print(f"  ✓ Stress parsing correct: {result['stress_percent']:.1f}%")
    else:
        print(f"  ✗ Stress parsing failed: expected {expected_stress:.1f}%, got {result['stress_percent']:.1f}%")
        sys.exit(1)
except Exception as e:
    print(f"  ✗ Stress parsing error: {e}")
    sys.exit(1)

print()

# Test 4: Test EDA analysis
print("[TEST 4] EDA analysis...")
try:
    analyzer = NuanicEDAAnalyzer()
    
    # Simulate EDA readings
    test_values = [100, 102, 105, 110, 108, 105, 103, 100, 99, 101]
    results = []
    
    for val in test_values:
        stats = analyzer.add_reading(val)
        results.append(stats)
    
    # Check last result
    last_stat = results[-1]
    if 'phasic' in last_stat and 'baseline' in last_stat:
        print(f"  ✓ EDA analysis working")
        print(f"    - Baseline: {last_stat['baseline']:.1f}")
        print(f"    - Phasic: {last_stat['phasic']:.1f}")
        print(f"    - History: {last_stat['history_length']} readings")
    else:
        print(f"  ✗ EDA analysis didn't return expected fields")
        sys.exit(1)
except Exception as e:
    print(f"  ✗ EDA analysis error: {e}")
    sys.exit(1)

print()

# Test 5: Verify data directories exist
print("[TEST 5] Data directories...")
try:
    log_dir = Path(logger.log_dir)
    if not log_dir.exists():
        log_dir.mkdir(parents=True, exist_ok=True)
    
    if log_dir.exists():
        print(f"  ✓ Log directory ready: {log_dir}")
    else:
        print(f"  ✗ Failed to create log directory")
        sys.exit(1)
except Exception as e:
    print(f"  ✗ Directory error: {e}")
    sys.exit(1)

print()

# Test 6: Documentation
print("[TEST 6] Documentation...")
docs_dir = Path(__file__).parent.parent.parent / "docs" / "nuanic"
required_docs = [
    "MODULE_GUIDE.md",
    "EDA_ANALYSIS_GUIDE.md",
    "PROJECT_ORGANIZATION.md"
]

all_exist = True
for doc in required_docs:
    doc_path = docs_dir / doc
    if doc_path.exists():
        print(f"  ✓ {doc}")
    else:
        print(f"  ✗ {doc} not found")
        all_exist = False

if not all_exist:
    sys.exit(1)

print()
print("=" * 80)
print("ALL TESTS PASSED ✓")
print("=" * 80)
print()
print("Ready to use Nuanic integration!")
print()
print("Next steps:")
print("1. Run: python scripts/ble/log_nuanic_session.py --duration 60")
print("2. Analyze: python scripts/ble/analyze_nuanic_data.py <csv_file>")
print("3. Read: docs/nuanic/MODULE_GUIDE.md")
print()
