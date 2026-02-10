# Quick start script for AWE Polar Project

Write-Host "Starting AWE Polar Project..." -ForegroundColor Green

# Check if virtual environment exists
if (-Not (Test-Path "venv")) {
    Write-Host "Virtual environment not found. Running setup first..." -ForegroundColor Yellow
    .\setup.ps1
    exit
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
.\venv\Scripts\Activate.ps1

# Check for required files
if (-Not (Test-Path ".env")) {
    Write-Host "`nWarning: .env file not found!" -ForegroundColor Red
    Write-Host "Please copy .env.example to .env and add your OpenAI API key" -ForegroundColor Yellow
    exit
}

if (-Not (Test-Path "models\improved_stress_model.pkl")) {
    Write-Host "`nWarning: Model file not found!" -ForegroundColor Red
    Write-Host "Please run 'python scripts/train_model.py' first to train the model" -ForegroundColor Yellow
    exit
}

# Start the Streamlit app
Write-Host "`nStarting Streamlit app..." -ForegroundColor Green
streamlit run scripts/app_streamlit.py
