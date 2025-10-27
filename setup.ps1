# Setup script for AWE Polar Project
# This script creates a virtual environment and installs all dependencies

Write-Host "Setting up AWE Polar Project environment..." -ForegroundColor Green

# Create virtual environment
Write-Host "`nCreating virtual environment..." -ForegroundColor Yellow
python -m venv venv

# Activate virtual environment
Write-Host "`nActivating virtual environment..." -ForegroundColor Yellow
.\venv\Scripts\Activate.ps1

# Upgrade pip
Write-Host "`nUpgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install dependencies
Write-Host "`nInstalling dependencies from requirements.txt..." -ForegroundColor Yellow
pip install -r requirements.txt

Write-Host "`n✓ Setup complete!" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "1. Copy .env.example to .env and add your OpenAI API key"
Write-Host "2. Place your 'all_hrv_data3.csv' file in this directory"
Write-Host "3. Run 'python ML_model3.py' to train the model"
Write-Host "4. Run 'streamlit run polar_awe9.py' to start the app"
Write-Host "`nTo run tests: pytest tests/ -v --cov=." -ForegroundColor Cyan
