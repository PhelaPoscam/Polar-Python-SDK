# AWE Polar Project

A stress monitoring application using Polar H10 heart rate monitor, machine learning, and LLM for real-time stress detection and insights.

## Features

- **Real-time Heart Rate Monitoring**: Connect to Polar H10 via Bluetooth
- **ML-based Stress Detection**: Random Forest classifier for stress prediction
- **Interactive Dashboard**: Streamlit-based web interface
- **LLM Insights**: OpenAI-powered actionable recommendations
- **HRV Analysis**: RMSSD calculation for stress assessment

## Prerequisites

- Python 3.8+
- Polar H10 heart rate monitor
- Bluetooth-enabled device
- OpenAI API key

## Setup

1. **Create a virtual environment**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

2. **Install dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:
   - Copy `.env.example` to `.env`
   - Add your OpenAI API key to `.env`

4. **Prepare training data**:
   - Place your `all_hrv_data3.csv` file in the project directory
   - Run the ML model training script:
   ```powershell
   python ML_model3.py
   ```

## Usage

### Train the ML Model

```powershell
python ML_model3.py
```

This will:
- Load and process HRV data
- Train a Random Forest classifier
- Save the model as `improved_stress_model.pkl`
- Save the scaler as `scaler.pkl`

### Run the Streamlit Application

```powershell
streamlit run polar_awe9.py
```

This will:
- Start the web interface
- Connect to your Polar H10 device
- Display real-time HR and HRV data
- Predict stress levels every 15 seconds
- Provide LLM-based insights

## Running Tests

```powershell
pytest tests/ -v --cov=.
```

## Project Structure

- `ML_model3.py`: Machine learning model training script
- `polar_awe9.py`: Main Streamlit application
- `requirements.txt`: Python dependencies
- `tests/`: Unit tests directory

## Model Details

- **Algorithm**: Random Forest Classifier
- **Features**: Heart Rate (HR) and RMSSD
- **Prediction Interval**: 15 seconds
- **Output**: Stress/No Stress with confidence score

## Notes

- Ensure your Polar H10 is paired and turned on before running the app
- The application requires an active internet connection for OpenAI API calls
- Model files (`*.pkl`) are generated after training and required for predictions
