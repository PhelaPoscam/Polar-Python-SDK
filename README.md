# AWE Polar Project

Stress monitoring application using Polar H10 heart rate monitor, machine learning, and LLM-based insights. The project now includes scaffolding for Phase 2 (TabNet pipeline) and Phase 3 (bio-adaptive game loop).

## Status Snapshot

- Core ML pipeline implemented for HR/RMSSD with Random Forest and Gradient Boosting.
- Hyperparameter tuning via GridSearchCV.
- Model versioning with timestamped artifacts.
- Streamlit dashboard with gauge chart and password-based access.
- Dataset helpers and sample data generator.
- CI pipeline via GitHub Actions.
- Phase 2/3 scaffolds and tests added for future work.

## Features

- Real-time heart rate monitoring via Bluetooth (Polar H10)
- ML-based stress detection (Random Forest, Gradient Boosting)
- Streamlit dashboard with gauge visualization
- LLM-based insights (OpenAI)
- HRV analysis (RMSSD)

## Prerequisites

- Python 3.8-3.11 (CI covers 3.8-3.11; runtime.txt targets 3.11.9)
- Polar H10 heart rate monitor
- Bluetooth-enabled device
- OpenAI API key (optional; enables LLM features)

## Setup

1. Create a virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

2. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   - Copy `.env.example` to `.env`
   - Add your OpenAI API key to `.env`

4. Prepare training data:
   - Place `all_hrv_data3.csv` in `data/raw/`
   - Run the ML training script:
   ```powershell
  python scripts/train/train_model.py
   ```

## Dataset Acquisition (WESAD, SWELL, UBFC-Phys)

These datasets have different access rules and may require registration or data-use approval.
Download them from their official sources and place the raw files locally.

Official sources (as referenced in Jui et al., 2026):

- WESAD (UCI ML Repository): https://archive.ics.uci.edu/ml/datasets/WESAD
- SWELL-KW (DANS / Radboud): https://cs.ru.nl/~skoldijk/SWELL-KW/Dataset.html
  - Kaggle mirror: https://www.kaggle.com/qiriro/swell-heart-rate-variability-hrv
- UBFC-Phys (IEEE DataPort): https://ieee-dataport.org/open-access/ubfc-phys
  - Author page: https://sites.google.com/view/ybenezeth/ubfc-phys

Recommended layout:
- datasets/WESAD
- datasets/SWELL
- datasets/UBFC-Phys

Use the helper script to verify local availability and optionally extract archives:

```powershell
python scripts/data/download_datasets.py --verify-only
```

If you have ZIP archives, place them under `datasets/` or `datasets/archives/` and run:

```powershell
python scripts/data/download_datasets.py --extract
```

## Usage

### Train the ML Model

```powershell
python scripts/train/train_model.py
```

This will:
- Load and process HRV data
- Train a Random Forest or Gradient Boosting classifier
- Save the model and scaler under `models/` with timestamps

### Run the Streamlit Application

```powershell
streamlit run scripts/app/app_streamlit.py
```

This will:
- Start the web interface
- Connect to your Polar H10 device
- Display real-time HR and HRV data
- Predict stress levels every 15 seconds
- Provide LLM-based insights (if configured)

### Helper Scripts

- PowerShell setup/start scripts live in `scripts/setup/`
- Test Streamlit stub app is in `scripts/app/test_app.py`

## Running Tests

```powershell
pytest tests/ -v --cov=.
```

Scaffold-only checks:

```powershell
pytest tests/test_advanced_models_scaffold.py -v
pytest tests/test_game_bridge_scaffold.py -v
```

## Project Structure

```
AWE_Polar_Project/
  data/
    logs/
    raw/
  datasets/
  models/
  scripts/
    app/
    ble/
    data/
    infer/
    setup/
    train/
  src/
    awe_polar/
      advanced_models/
      connector/
      game_bridge/
      reader/
  tests/
```

## Phase 2 Scaffolding (TabNet Pipeline)

Current scaffolds:
- `src/awe_polar/advanced_models/features.py` (windowed feature extraction)
- `src/awe_polar/advanced_models/tabnet_model.py` (TabNet config/build helpers)
- `src/awe_polar/advanced_models/tabnet_trainer.py` (LOSO training skeleton)
- `src/awe_polar/advanced_models/explainability.py` (SHAP/LIME entry points)

## Phase 3 Scaffolding (Bio-Adaptive Game Loop)

Current scaffolds:
- `src/awe_polar/game_bridge/stress_engine.py` (UATR-style smoothing skeleton)
- `src/awe_polar/game_bridge/game_connector.py` (game API connector)
- `src/awe_polar/game_bridge/cognitive_agent.py` (adaptive state selection)

## Work Completed

- Project planning checklist added to this README.
- Data preprocessing supports CSV, Excel, and Parquet with IQR outlier filtering.
- Gradient Boosting added alongside Random Forest.
- Hyperparameter tuning via GridSearchCV.
- Model versioning with timestamped artifacts.
- Streamlit UI with gauge chart and password-based authentication.
- Tests expanded for data generation and hyperparameter tuning.
- CI pipeline via GitHub Actions.
- Phase 2 and 3 module scaffolds with basic tests.

## TODO

- [ ] Enhance data preprocessing (additional cleaning and transformations)
- [ ] Add more visualizations to the Streamlit dashboard
- [ ] Add module-level documentation and a docs/ directory
- [x] Scaffold validation (advanced_models and game_bridge tests)
- [ ] Decide whether to wire the TabNet training loop to real metrics
- [ ] Implement a concrete UATR algorithm in the stress engine

## Next Steps

- [ ] Decide whether to wire the TabNet training loop to real metrics
- [ ] Implement a concrete UATR algorithm in the stress engine

## Nuanic Ring Integration (In Progress)

### Discovery Results (2026-02-26)

Successfully discovered and connected to Nuanic smart ring:
- **Device Name**: LHB-644B07F9 / LHB-6F0A2510
- **Connection**: ✅ BLE connection established (6-18 seconds)
- **GATT Services**: 6 services, 20 characteristics mapped
- **Key Characteristic**: `00001524-1212-efde-1523-785feabcd124` (notify, read, write)

### Status

- ✅ Scan and device discovery working
- ✅ GATT architecture mapping complete
- ❌ Data streaming not yet working (no notifications received)

### Next Steps

- [ ] Investigate ring activation protocol (may require write command to start streaming)
- [ ] Check Nuanic official app/documentation for BLE handshaking requirements
- [ ] Test alternative characteristics (`00001525`, `00008421`) via write commands
- [ ] Implement ring-specific protocol if needed

### Scripts

- `scripts/ble/ble_ring_streamer.py` - Full 3-phase BLE streamer (scan → discover → stream)
- `scripts/ble/discover_nuanic.py` - Ring discovery with GATT mapping
- `scripts/ble/test_nuanic_connection.py` - Connection test with 20s timeout
- `scripts/ble/test_all_characteristics.py` - Listen to all notify characteristics simultaneously
- Ring data logs are written to `data/logs/ring_data_log.csv`

## Notes

- Ensure your Polar H10 is paired and turned on before running the app.
- The application requires an active internet connection for OpenAI API calls.
- Model files (`*.pkl`) are generated after training and required for predictions.
- Nuanic ring integration is in progress; firmware may require activation commands for data streaming.

## Future Roadmap & Research Goals

### Phase 2: High-Fidelity Stress Detection (TabNet Pipeline)

Implementation of the architecture described by Jui et al. (2026):

- Advanced Feature Engineering (Jui et al., Table 2)
  - Extract the 21 features (Mean, Median, Std, Var, Min, Max, Skew, Kurtosis, Range) for EDA and HR
  - Interaction feature: covariance between EDA and HR
  - Sliding window logic: 25-second windows with 50% overlap
- TabNet Model Architecture
  - Integrate pytorch_tabnet library
  - Configure TabNetClassifier with paper-specific hyperparameters
- Validation Strategy
  - Leave-One-Subject-Out (LOSO) cross-validation loop
  - Subject-based Z-score normalization
- Explainable AI (XAI)
  - SHAP global feature importance
  - LIME local instance explanation

### Phase 3: Bio-Adaptive Game Director (Closed-Loop System)

Adaptation of the CPS framework by Yazdinejad et al. (2026):

- Game Integration Layer
  - Mock game environment (PyGame/Unity) accepting difficulty commands
  - API hooks: SetSpawnRate(), SetEnemyAccuracy(), SetGameSpeed()
- Stress Engine (Middleware)
  - Connect real-time Polar H10 stream to TabNet predictions
  - Utility-Aware Temporal Reasoner (UATR)
- Cognitive Agent Logic (AI Director)
  - SpeedyIBL-style rule set
  - Adaptive states: MONITOR, ASSIST, DE-ESCALATE, PROVOKE
- Validation Experiment
  - Control vs adaptive mode test protocol
  - Logging for time spent in high stress
