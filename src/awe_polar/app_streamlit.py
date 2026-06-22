# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT / "src"))

import asyncio
import hashlib
import os
import queue
import time
from collections import deque
import threading
import warnings

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Fallback for older Streamlit versions (< 1.33) without fragment support
if hasattr(st, "fragment"):
    fragment = st.fragment
else:

    def fragment(*args, **kwargs):  # type: ignore
        return lambda f: f


from dotenv import load_dotenv
from openai import OpenAI

from awe_polar.connector.ble_discovery import discover_polar_device
from awe_polar.connector.exporters.queue_sink import QueueSink
from awe_polar.connector.schemas import SignalPacket
from awe_polar.connector.stream.polar_h10_ble import HeartRate
from awe_polar.reader import StressPredictor, load_model_bundle
from awe_polar.reader.realtime import ReaderConfig, run_reader

# ==========================================
# Configuration and Prompts
# ==========================================
MODEL_PATH = PROJECT_ROOT / "models" / "improved_stress_model.pkl"
SCALER_PATH = PROJECT_ROOT / "models" / "scaler.pkl"
PREDICTION_INTERVAL = 15  # seconds
LLM_MODEL = "gpt-4o-mini"

LLM_TREND_PROMPT = """Please analyse trends in stress.
Right now I am presenting in big meeting. Here is data
{trend}.
Current HR: {hr:.1f},
Current RMSSD: {rmssd:.4f},
Stress Status: {status}
from ML model with confidence {confidence:.1%}.
{prompt} Give response in 10 words"""

LLM_INSIGHT_PROMPT = """Analyze and suggest actionable
insight based on average heart rate {hr:.1f},
average RMSSD {rmssd:.4f},
and stress predicted from ML model which is
{status} with confidence {confidence:.1%}.
Right now I am giving a presentation on big meeting.
Please suggest actionable insight in 10 words"""

# ==========================================
# Setup & Initialization
# ==========================================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
llm_enabled = bool(OPENAI_API_KEY)
client = OpenAI(api_key=OPENAI_API_KEY) if llm_enabled else None
warnings.filterwarnings("ignore")

# Define global queue for background thread communication
if "GLOBAL_BLE_QUEUE" not in st.session_state:
    st.session_state.GLOBAL_BLE_QUEUE = queue.Queue()


def check_password() -> bool:
    """Returns `True` if the user had a correct password."""

    def password_entered():
        if "password" in st.session_state:
            if (
                hashlib.sha256(st.session_state["password"].encode()).hexdigest()
                == st.secrets["PASSWORD"]
            ):
                st.session_state["password_correct"] = True
                del st.session_state["password"]
            else:
                st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.write("Please enter the password to use the app.")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    return True


@st.cache_resource
def load_predictor():
    """Load model and scaler once and cache it."""
    try:
        bundle = load_model_bundle(MODEL_PATH, SCALER_PATH)
        predictor = StressPredictor(bundle, feature_order=["hr_bpm", "rmssd"])
        print("Stress prediction model loaded successfully!")
        return predictor
    except FileNotFoundError:
        print("Model or scaler file not found.")
        return None


def calculate_rmssd(rr_intervals: list) -> float | None:
    """Calculate RMSSD from RR intervals."""
    if len(rr_intervals) < 2:
        return None
    try:
        rr_array = np.array(
            [float(rr) for rr in rr_intervals if rr is not None and rr > 0]
        )
        if len(rr_array) < 2:
            return None
        return float(np.sqrt(np.mean(np.diff(rr_array) ** 2)))
    except Exception:
        return None


# ==========================================
# Background BLE Task
# ==========================================
def ble_background_task(data_queue: queue.Queue, is_mock: bool):
    """Background thread to handle BLE connectivity or Mock data."""
    if is_mock:
        mock_hr = 70.0
        mock_hrv = 40.0
        ecg_phase = 0
        ppg_phase = 0
        acc_time = 0.0
        while True:
            time.sleep(0.1)  # 10 Hz chunk generation

            # Generate HR/HRV once per second (10% probability at 10Hz)
            if np.random.random() < 0.1:
                mock_hr = float(np.clip(mock_hr + np.random.randint(-2, 3), 60, 100))
                mock_hrv = float(np.clip(mock_hrv + np.random.randint(-3, 4), 30, 60))
                data_queue.put(("data", (mock_hr, [mock_hrv])))

            # Generate ECG (13 samples at 10Hz = 130Hz)
            mock_ecg = []
            for _ in range(13):
                t = ecg_phase % 130
                if t < 10:  # P-wave
                    val = 100 * np.sin(np.pi * t / 10)
                elif t < 15:  # Flat
                    val = 0
                elif t == 16:  # Q-wave
                    val = -150
                elif t == 17 or t == 18:  # R-wave spike
                    val = 1200 if t == 17 else 800
                elif t == 19:  # S-wave
                    val = -300
                elif t < 25:  # Flat
                    val = 0
                elif t < 40:  # T-wave
                    val = 250 * np.sin(np.pi * (t - 25) / 15)
                else:
                    val = 0
                val += np.random.randint(-15, 16)  # Add noise
                mock_ecg.append(int(val))
                ecg_phase += 1
            data_queue.put(("ecg", mock_ecg))

            # Generate PPG (6 samples at 10Hz = 60Hz)
            mock_ppg = []
            for _ in range(6):
                t = ppg_phase % 60
                val = (
                    50000
                    + 4000 * np.sin(2 * np.pi * t / 60)
                    + 1500 * np.sin(4 * np.pi * t / 60)
                )
                val += np.random.randint(-100, 101)
                mock_ppg.append(
                    [int(val), int(val * 0.9), int(val * 0.85), int(val * 0.8)]
                )
                ppg_phase += 1
            data_queue.put(("ppg", mock_ppg))

            # Generate ACC (2 samples at 10Hz = 20Hz)
            mock_acc = []
            for _ in range(2):
                x = int(100 * np.sin(acc_time) + np.random.randint(-5, 6))
                y = int(50 * np.cos(acc_time) + np.random.randint(-5, 6))
                z = int(980 + 20 * np.sin(acc_time * 2) + np.random.randint(-5, 6))
                mock_acc.append((x, y, z))
                acc_time += 0.05
            data_queue.put(("acc", mock_acc))
    else:

        async def run_ble():
            heartrate = None
            try:
                device = await discover_polar_device(timeout=20.0)

                if not device:
                    data_queue.put(("error", "Polar device not found"))
                    return

                def _callback(data):
                    if isinstance(data, tuple) and len(data) >= 2:
                        hr_val, rr_ints = data
                        data_queue.put(("data", (hr_val, rr_ints if rr_ints else None)))

                def _ecg_callback(data):
                    data_queue.put(("ecg", data[1]))

                def _ppg_callback(data):
                    data_queue.put(("ppg", data[1]))

                def _acc_callback(data):
                    data_queue.put(("acc", data[1]))

                def _ppi_callback(data):
                    data_queue.put(("data", (None, data[1])))

                def _gyro_callback(data):
                    data_queue.put(("gyro", data[1]))

                def _mag_callback(data):
                    data_queue.put(("mag", data[1]))

                heartrate = HeartRate(
                    device,
                    callback=_callback,
                    ecg_callback=_ecg_callback,
                    ppg_callback=_ppg_callback,
                    acc_callback=_acc_callback,
                    ppi_callback=_ppi_callback,
                    gyro_callback=_gyro_callback,
                    mag_callback=_mag_callback,
                )
                await heartrate.start_notify()
                while True:
                    await asyncio.sleep(1)
            except Exception as e:
                data_queue.put(("error", str(e)))
            finally:
                if heartrate:
                    await heartrate.stop_notify()

        asyncio.run(run_ble())


def start_ble_thread_once(is_mock: bool):
    """Start the BLE background thread if not already running."""
    if "ble_thread_started" not in st.session_state:
        st.session_state.ble_thread_started = True
        thread = threading.Thread(
            target=ble_background_task,
            args=(st.session_state.GLOBAL_BLE_QUEUE, is_mock),
            daemon=True,
        )
        thread.start()


# ==========================================
# State processing
# ==========================================
def process_queue_data(predictor):
    """Process incoming data from the BLE queue."""
    current_time = time.time()
    queue_sink = QueueSink(queue.Queue())  # Temporary sink for realtime reader

    while not st.session_state.GLOBAL_BLE_QUEUE.empty():
        msg_type, payload = st.session_state.GLOBAL_BLE_QUEUE.get_nowait()

        if msg_type == "data":
            hr, hrv = payload
            if hr is not None:
                st.session_state.hr_list.append(hr)
                new_data = pd.DataFrame([[hr, hrv]], columns=["hr", "hrv"])
                st.session_state.df = pd.concat(
                    [st.session_state.df, new_data], ignore_index=True
                )

            if hrv is not None:
                if isinstance(hrv, list):
                    st.session_state.hrv_list.extend(hrv)
                elif isinstance(hrv, (int, float)):
                    st.session_state.hrv_list.append(hrv)

            # Every interval process stress
            if (
                current_time - st.session_state.last_prediction_time
            ) >= PREDICTION_INTERVAL:
                if (
                    len(st.session_state.hr_list) >= 5
                    and len(st.session_state.hrv_list) >= 3
                ):
                    hr_avg = np.mean(st.session_state.hr_list[-10:])
                    recent_rr = st.session_state.hrv_list[-20:]
                    rmssd = calculate_rmssd(recent_rr)

                    if rmssd is not None and predictor is not None:
                        # Feed the batch to the predictor
                        packet = SignalPacket(
                            source="polar_h10",
                            signals={"hr_bpm": hr_avg},
                            features={"rmssd": rmssd},
                        )
                        queue_sink.send(packet)

                        def on_prediction(prediction):
                            st.session_state.stress_result = prediction.label.upper()
                            st.session_state.confidence = prediction.confidence
                            st.session_state.stress_auto = (
                                st.session_state.stress_result
                            )

                        run_reader(
                            predictor,
                            queue_sink._queue,
                            on_prediction,
                            config=ReaderConfig(poll_interval=0.0),
                            stop_on_empty=True,
                        )

                        st.session_state.hr_avg = hr_avg
                        st.session_state.rmssd = rmssd

                        # Add to trend
                        trend_msg = f"{st.session_state.stress_result}: Avg HR={hr_avg:.1f}, Avg RMSSD={rmssd:.4f} (Confidence: {st.session_state.confidence:.1%}) "
                        st.session_state.stress_trend += trend_msg

                        # Trigger LLM auto-insight periodically (simulate a=10 logic)
                        st.session_state.prediction_counter += 1
                        if st.session_state.prediction_counter >= 10 and llm_enabled:
                            prompt = LLM_INSIGHT_PROMPT.format(
                                hr=hr_avg,
                                rmssd=rmssd,
                                status=st.session_state.stress_auto,
                                confidence=st.session_state.confidence,
                            )
                            stream = client.chat.completions.create(
                                model=LLM_MODEL,
                                messages=[{"role": "user", "content": prompt}],
                                stream=True,
                            )
                            response = ""
                            for chunk in stream:
                                if chunk.choices[0].delta.content:
                                    response += chunk.choices[0].delta.content
                            st.session_state.insight_response = response
                            st.session_state.prediction_counter = 0

                    st.session_state.last_prediction_time = current_time

            # Cleanup memory
            if len(st.session_state.hr_list) > 50:
                st.session_state.hr_list = st.session_state.hr_list[-30:]
            if len(st.session_state.hrv_list) > 100:
                st.session_state.hrv_list = st.session_state.hrv_list[-50:]
        elif msg_type == "ecg":
            st.session_state.ecg_deque.extend(payload)
        elif msg_type == "ppg":
            st.session_state.ppg_deque.extend([s[0] for s in payload])
        elif msg_type == "acc":
            st.session_state.acc_deque.extend(payload)
        elif msg_type == "gyro":
            st.session_state.gyro_deque.extend(payload)
        elif msg_type == "mag":
            st.session_state.mag_deque.extend(payload)


# ==========================================
# UI Components
# ==========================================
@fragment(run_every="1s")
def render_metrics_and_charts(predictor):
    """Render the dynamically updating top metrics and charts."""
    process_queue_data(predictor)

    # State aliases
    hr = st.session_state.hr_list[-1] if st.session_state.hr_list else "--"
    hrv = st.session_state.hrv_list[-1] if st.session_state.hrv_list else "--"
    stress_res = st.session_state.stress_result
    conf = st.session_state.confidence

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(
            f"<span style='font-size:60px;'>❤</span><br><span style='font-size:40px;'>HR: {hr} bpm</span>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"<span style='font-size:60px;'>📈</span><br><span style='font-size:40px;'>HRV: {hrv} ms</span>",
            unsafe_allow_html=True,
        )
    with col3:
        g_val = conf if stress_res == "HIGH STRESS" else 1 - conf
        g_color = "Red" if stress_res == "HIGH STRESS" else "Green"
        fig = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=g_val,
                domain={"x": [0, 1], "y": [0, 1]},
                title={"text": "Stress Level"},
                gauge={
                    "axis": {"range": [None, 1]},
                    "bar": {"color": g_color},
                    "steps": [
                        {"range": [0, 0.5], "color": "lightgray"},
                        {"range": [0.5, 1], "color": "gray"},
                    ],
                    "threshold": {
                        "line": {"color": "red", "width": 4},
                        "thickness": 0.75,
                        "value": 0.8,
                    },
                },
            )
        )
        st.plotly_chart(fig, use_container_width=True, key="stress_gauge")
    with col4:
        # Format the stress UI output based on label
        if stress_res == "NEUTRAL":
            icon, text = "😐", "Predicting..."
        elif stress_res == "HIGH STRESS":
            icon, text = "😰", "Stress"
        elif stress_res == "LOW STRESS":
            icon, text = "😌", "Low Stress"
        else:
            icon, text = "😊", "Baseline"

        st.markdown(
            f"<span style='font-size:60px;'>ML {icon}</span><br><span style='font-size:40px;'>{text}</span>",
            unsafe_allow_html=True,
        )
        if st.session_state.rmssd > 0:
            st.markdown(
                f"<span>HR={st.session_state.hr_avg:.1f}, RMSSD={st.session_state.rmssd:.4f} ({conf:.1%})</span>",
                unsafe_allow_html=True,
            )
    with col5:
        st.markdown(
            f"<span style='font-size:60px;'>LLM 📄</span><br><span style='font-size:20px;'>{st.session_state.insight_response}</span>",
            unsafe_allow_html=True,
        )

    st.markdown("<hr style='margin: 2rem 0;'>", unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["Overview", "ECG", "PPG", "IMU"])

    with tab1:
        col6, col7 = st.columns(2)
        with col6:
            st.subheader("Chart: Heart Rate")
            if len(st.session_state.df) > 0:
                fig1 = go.Figure(
                    go.Scatter(
                        x=st.session_state.df.index,
                        y=st.session_state.df["hr"],
                        mode="lines",
                        name="HR",
                    )
                )
                fig1.update_layout(
                    title="Heart Rate",
                    xaxis_title="Time",
                    yaxis_title="BPM",
                    margin=dict(t=30, b=10, l=10, r=10),
                )
                st.plotly_chart(fig1, use_container_width=True, key="hr_chart")
        with col7:
            st.subheader("Chart: Heart Rate Variability (RR)")
            if len(st.session_state.df) > 0:
                fig2 = go.Figure(
                    go.Scatter(
                        x=st.session_state.df.index,
                        y=st.session_state.df["hrv"],
                        mode="lines",
                        name="HRV",
                    )
                )
                fig2.update_layout(
                    title="Heart Rate Variability (RMSSD)",
                    xaxis_title="Time",
                    yaxis_title="ms",
                    margin=dict(t=30, b=10, l=10, r=10),
                )
                st.plotly_chart(fig2, use_container_width=True, key="hrv_chart")

    with tab2:
        st.subheader("Live ECG Waveform")
        ecg_data = list(st.session_state.ecg_deque)
        if len(ecg_data) > 0:
            fig_ecg = go.Figure(
                go.Scatter(
                    y=ecg_data,
                    mode="lines",
                    name="ECG",
                    line=dict(color="#00D2C4", width=1.5),
                )
            )
            fig_ecg.update_layout(
                title="ECG Waveform (130Hz)",
                xaxis_title="Sample Index",
                yaxis_title="Voltage (µV)",
                margin=dict(t=30, b=10, l=10, r=10),
                height=400,
            )
            st.plotly_chart(fig_ecg, use_container_width=True, key="live_ecg_chart")
        else:
            st.info(
                "ECG stream inactive or waiting for data. Note: ECG is exclusive to Polar H10 chest strap."
            )

    with tab3:
        st.subheader("Live PPG Optical Pulse Waveform")
        ppg_data = list(st.session_state.ppg_deque)
        if len(ppg_data) > 0:
            fig_ppg = go.Figure(
                go.Scatter(
                    y=ppg_data,
                    mode="lines",
                    name="PPG",
                    line=dict(color="#FF7F0E", width=2),
                )
            )
            fig_ppg.update_layout(
                title="PPG Optical Waveform",
                xaxis_title="Sample Index",
                yaxis_title="Reflectance (Raw)",
                margin=dict(t=30, b=10, l=10, r=10),
                height=400,
            )
            st.plotly_chart(fig_ppg, use_container_width=True, key="live_ppg_chart")
        else:
            st.info(
                "PPG stream inactive or waiting for data. Note: PPG is exclusive to Polar Verity Sense / OH1."
            )

    with tab4:
        st.subheader("Inertial Measurement Unit (IMU) Data")
        acc_data = list(st.session_state.acc_deque)
        gyro_data = list(st.session_state.gyro_deque)
        mag_data = list(st.session_state.mag_deque)

        def parse_imu_deque(dq):
            x_vals, y_vals, z_vals = [], [], []
            for sample in dq:
                if hasattr(sample, "x"):
                    x_vals.append(sample.x)
                    y_vals.append(sample.y)
                    z_vals.append(sample.z)
                elif isinstance(sample, (list, tuple)) and len(sample) >= 3:
                    x_vals.append(sample[0])
                    y_vals.append(sample[1])
                    z_vals.append(sample[2])
            return x_vals, y_vals, z_vals

        if len(acc_data) > 0:
            ax, ay, az = parse_imu_deque(acc_data)
            fig_acc = go.Figure()
            fig_acc.add_trace(
                go.Scatter(y=ax, mode="lines", name="X", line=dict(color="#FF4B4B"))
            )
            fig_acc.add_trace(
                go.Scatter(y=ay, mode="lines", name="Y", line=dict(color="#00D2C4"))
            )
            fig_acc.add_trace(
                go.Scatter(y=az, mode="lines", name="Z", line=dict(color="#FF7F0E"))
            )
            fig_acc.update_layout(
                title="Accelerometer (3-Axis)",
                xaxis_title="Sample Index",
                yaxis_title="mg",
                margin=dict(t=30, b=10, l=10, r=10),
                height=300,
            )
            st.plotly_chart(fig_acc, use_container_width=True, key="live_acc_chart")
        else:
            st.info("Accelerometer stream inactive or waiting for data.")

        if len(gyro_data) > 0:
            gx, gy, gz = parse_imu_deque(gyro_data)
            fig_gyro = go.Figure()
            fig_gyro.add_trace(
                go.Scatter(
                    y=gx, mode="lines", name="X (Pitch)", line=dict(color="#FF4B4B")
                )
            )
            fig_gyro.add_trace(
                go.Scatter(
                    y=gy, mode="lines", name="Y (Roll)", line=dict(color="#00D2C4")
                )
            )
            fig_gyro.add_trace(
                go.Scatter(
                    y=gz, mode="lines", name="Z (Yaw)", line=dict(color="#FF7F0E")
                )
            )
            fig_gyro.update_layout(
                title="Gyroscope (3-Axis)",
                xaxis_title="Sample Index",
                yaxis_title="deg/s",
                margin=dict(t=30, b=10, l=10, r=10),
                height=300,
            )
            st.plotly_chart(fig_gyro, use_container_width=True, key="live_gyro_chart")
        else:
            st.info("Gyroscope stream inactive or waiting for data.")

        if len(mag_data) > 0:
            mx, my, mz = parse_imu_deque(mag_data)
            fig_mag = go.Figure()
            fig_mag.add_trace(
                go.Scatter(y=mx, mode="lines", name="X", line=dict(color="#FF4B4B"))
            )
            fig_mag.add_trace(
                go.Scatter(y=my, mode="lines", name="Y", line=dict(color="#00D2C4"))
            )
            fig_mag.add_trace(
                go.Scatter(y=mz, mode="lines", name="Z", line=dict(color="#FF7F0E"))
            )
            fig_mag.update_layout(
                title="Magnetometer (3-Axis)",
                xaxis_title="Sample Index",
                yaxis_title="µT",
                margin=dict(t=30, b=10, l=10, r=10),
                height=300,
            )
            st.plotly_chart(fig_mag, use_container_width=True, key="live_mag_chart")
        else:
            st.info("Magnetometer stream inactive or waiting for data.")


def render_chatbox():
    """Render the LLM chat input and history."""
    st.subheader("LLM Chat Box")
    with st.expander("Chat with the LLM", expanded=True):
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        if llm_enabled:
            prompt = st.chat_input("Ask about your performance and strategy...")
            if prompt:
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)

                modified_prompt = LLM_TREND_PROMPT.format(
                    trend=st.session_state.stress_trend,
                    hr=st.session_state.hr_avg,
                    rmssd=st.session_state.rmssd,
                    status=st.session_state.stress_result,
                    confidence=st.session_state.confidence,
                    prompt=prompt,
                )

                api_messages = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages[:-1]
                ]
                api_messages.append({"role": "user", "content": modified_prompt})

                with st.chat_message("assistant"):
                    stream = client.chat.completions.create(
                        model=LLM_MODEL, messages=api_messages, stream=True
                    )
                    response = st.write_stream(stream)
                st.session_state.messages.append(
                    {"role": "assistant", "content": response}
                )
        else:
            st.info(
                "LLM features are disabled. Add your OpenAI API key to .env to enable chat and insights."
            )


def register_session_state():
    """Initialize Streamlit session state variables."""
    if "stress_result" not in st.session_state:
        st.session_state.update(
            {
                "stress_result": "NEUTRAL",
                "stress_auto": "NEUTRAL",
                "stress_trend": "",
                "insight_response": "Waiting for data...",
                "confidence": 0.0,
                "hr_avg": 0.0,
                "rmssd": 0.0,
                "prediction_counter": 0,
                "last_prediction_time": time.time(),
                "messages": [],
                "df": pd.DataFrame(columns=["hr", "hrv"]),
                "hr_list": [],
                "hrv_list": [],
                "ecg_deque": deque(maxlen=500),
                "ppg_deque": deque(maxlen=300),
                "acc_deque": deque(maxlen=200),
                "gyro_deque": deque(maxlen=200),
                "mag_deque": deque(maxlen=200),
            }
        )


def main_app():
    """Defines the main user interface."""
    st.set_page_config(page_title="Polar AWE", page_icon="❤", layout="wide")
    st.title("Polar AWE: Stress Monitoring with ML and LLM")
    st.markdown("<hr style='margin: 0.5rem 0;'>", unsafe_allow_html=True)

    register_session_state()
    predictor = load_predictor()

    is_mock = str(st.query_params.get("mock", "")).lower() in {"1", "true", "yes"}
    start_ble_thread_once(is_mock)

    main_col1, main_col2 = st.columns([2, 1])

    with main_col1:
        render_metrics_and_charts(predictor)

    with main_col2:
        render_chatbox()


if __name__ == "__main__":
    if "PASSWORD" not in st.secrets or check_password():
        main_app()
