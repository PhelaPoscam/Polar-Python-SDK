# Nuanic Documentation Index

## Primary Reference
- **[Nuanic Master Guide](00_master_guide.md)**

This is the canonical Nuanic document and includes:
- Environment setup and quick start
- CLI usage and options
- Python API reference
- Packet/hex decoding details
- EDA analysis methods
- Troubleshooting and historical investigation notes

## Common Commands
```bash
python scripts/nuanic_monitor_cli.py --duration 60
python scripts/nuanic_logger_cli.py --duration 300
python scripts/nuanic_analyzer_cli.py data/nuanic_logs/nuanic_stress_YYYY-MM-DD_HH-MM-SS.csv
python scripts/discover_nuanic_services.py
```

## Notes
- Ring discovery is name-based (`Nuanic`) because BLE addresses can rotate.
- For packet byte mapping and UUID details, use `00_master_guide.md`.
