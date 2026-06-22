# Quick start script for Polar BLE Python SDK

Write-Host "Starting Polar BLE Python SDK..." -ForegroundColor Green

# Check if virtual environment exists
if (-Not (Test-Path ".venv")) {
    Write-Host "Virtual environment not found. Running setup first..." -ForegroundColor Yellow
    .\setup.ps1
    exit
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
.\.venv\Scripts\Activate.ps1

# Check for required files
if (-Not (Test-Path ".env")) {
    Write-Host "`nWarning: .env file not found!" -ForegroundColor Red
    Write-Host "Please copy .env.example to .env and add your OpenAI API key" -ForegroundColor Yellow
    exit
}

if (-Not (Test-Path "models\improved_stress_model.pkl")) {
    Write-Host "`nWarning: Model file not found!" -ForegroundColor Red
    Write-Host "Please run 'python src/polar_ble_sdk/ml/train_model.py' first to train the model" -ForegroundColor Yellow
    exit
}

# Start the Streamlit app
Write-Host "`nStarting Streamlit app..." -ForegroundColor Green
$env:PYTHONPATH = "src"
streamlit run src/polar_ble_sdk/app_streamlit.py
