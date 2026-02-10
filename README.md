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
   - Place your `all_hrv_data3.csv` file in `data/raw/`
   - Run the ML model training script:
   ```powershell
   python scripts/train_model.py
   ```

## Dataset Acquisition (WESAD, SWELL, UBFC-Phys)

These datasets have different access rules and may require registration or data-use approval.
For compliance, download them from their official sources and place the raw files locally.

Official sources (as referenced in Jui et al., 2026):

- WESAD (UCI ML Repository): https://archive.ics.uci.edu/ml/datasets/WESAD
- SWELL-KW (DANS / Radboud): https://cs.ru.nl/~skoldijk/SWELL-KW/Dataset.html
   - Kaggle mirror: https://www.kaggle.com/qiriro/swell-heart-rate-variability-hrv
- UBFC-Phys (IEEE DataPort): https://ieee-dataport.org/open-access/ubfc-phys
   - Author page: https://sites.google.com/view/ybenezeth/ubfc-phys

Recommended layout:
- [datasets/WESAD](datasets/WESAD)
- [datasets/SWELL](datasets/SWELL)
- [datasets/UBFC-Phys](datasets/UBFC-Phys)

Use the helper script to verify local availability and optionally extract archives:

```powershell
python scripts/download_datasets.py --verify-only
```

If you have ZIP archives, place them under [datasets](datasets) or [datasets/archives](datasets/archives) and run:

```powershell
python scripts/download_datasets.py --extract
```

## Usage

### Train the ML Model

```powershell
python scripts/train_model.py
```

This will:
- Load and process HRV data
- Train a Random Forest classifier
- Save the model as `models/improved_stress_model.pkl`
- Save the scaler as `models/scaler.pkl`

### Run the Streamlit Application

```powershell
streamlit run scripts/app_streamlit.py
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

- `src/awe_polar/`: Core application and training modules
- `scripts/`: Entrypoints for training, data generation, and Streamlit
- `data/raw/`: Raw HRV datasets
- `models/`: Trained model artifacts
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
