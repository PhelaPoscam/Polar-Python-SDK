# Setup script for Polar BLE Python SDK
# This script creates a virtual environment and installs all dependencies

Write-Host "Setting up Polar BLE Python SDK environment..." -ForegroundColor Green

# Create virtual environment
Write-Host "`nCreating virtual environment..." -ForegroundColor Yellow
python -m venv .venv

# Activate virtual environment
Write-Host "`nActivating virtual environment..." -ForegroundColor Yellow
.\.venv\Scripts\Activate.ps1

# Upgrade pip
Write-Host "`nUpgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install dependencies
Write-Host "`nInstalling dependencies from requirements.txt..." -ForegroundColor Yellow
pip install -r requirements.txt

Write-Host "`n✓ Setup complete!" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "1. Run 'python -m pytest tests/' to run tests"
Write-Host "2. Run 'monitor-polar' or 'python scripts/monitor_polar_terminal.py' for the CLI dashboard"
Write-Host "3. Run 'python scripts/monitor_dual_polar.py' for dual-device monitoring"
Write-Host "4. See README.md for the full API reference" -ForegroundColor Cyan
