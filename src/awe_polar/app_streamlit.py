from __future__ import annotations

import asyncio as aio
import hashlib
import os
import queue
import time
import warnings
from pathlib import Path

from . import bleakheart as bh
import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from bleak import BleakClient, BleakScanner
from dotenv import load_dotenv
from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = PROJECT_ROOT / "models" / "improved_stress_model.pkl"
SCALER_PATH = PROJECT_ROOT / "models" / "scaler.pkl"

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
    llm_enabled = True
else:
    client = None
    llm_enabled = False
warnings.filterwarnings("ignore")
stress_trend = ""

def check_password():
    """Returns `True` if the user had a correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if hashlib.sha256(st.session_state["password"].encode()).hexdigest() == st.secrets["PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.write("Please enter the password to use the app.")
        return False
    elif not st.session_state["password_correct"]:
        # Password not correct, show input + error.
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        # Password correct.
        return True

def main_app():
    """Defines the main user interface of the Streamlit application."""
    st.set_page_config(
        page_title="Polar AWE",
        page_icon="❤",
        layout="wide",
    )

    st.title("Polar AWE: Stress Monitoring with ML and LLM")
    st.markdown("<hr style='margin: 0.5rem 0;'>", unsafe_allow_html=True)

    # Initialize session state for persistent data
    if "hr_data" not in st.session_state:
        st.session_state.hr_data = pd.DataFrame(columns=["hr", "hrv"])
    if "stress_result" not in st.session_state:
        st.session_state.stress_result = "NEUTRAL"
    if "column4_response" not in st.session_state:
        st.session_state.column4_response = "Waiting for data..."
    if "stress_trend" not in st.session_state:
        st.session_state.stress_trend = ""
    if "hr_avg" not in st.session_state:
        st.session_state.hr_avg = 0
    if "rmssd" not in st.session_state:
        st.session_state.rmssd = 0
    if "confidence" not in st.session_state:
        st.session_state.confidence = 0
    if "ble_data_queue" not in st.session_state:
        st.session_state.ble_data_queue = queue.Queue()
    if "ble_running" not in st.session_state:
        st.session_state.ble_running = False
    if "latest_hr" not in st.session_state:
        st.session_state.latest_hr = 0
    if "latest_hrv" not in st.session_state:
        st.session_state.latest_hrv = 0
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "df" not in st.session_state:
        st.session_state.df = pd.DataFrame(columns=["hr", "hrv"])

    # Main content with two columns
    main_col1, main_col2 = st.columns([2, 1])

    with main_col1:
        # Top 5 columns for metrics
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            ph1 = st.empty()
            ph1.markdown("<span style='font-size:60px;'>❤</span>", unsafe_allow_html=True)
            ph1.markdown("<span style='font-size:40px;'>HR: -- bpm</span>", unsafe_allow_html=True)
        with col2:
            ph2 = st.empty()
            ph2.markdown("<span style='font-size:60px;'>📈</span>", unsafe_allow_html=True)
            ph2.markdown("<span style='font-size:40px;'>HRV: -- ms</span>", unsafe_allow_html=True)
        with col3:
            ph3 = st.empty()
        with col4:
            ph4 = st.empty()
            ph4.markdown("<span style='font-size:60px;'>😊</span>", unsafe_allow_html=True)
            ph4.markdown("<span style='font-size:40px;'>No Stress</span>", unsafe_allow_html=True)
        with col5:
            ph5 = st.empty()
            ph5.markdown("<span style='font-size:60px;'>📄</span>", unsafe_allow_html=True)
            ph5.markdown("<span style='font-size:20px;'>--</span>", unsafe_allow_html=True)

        st.markdown("<hr style='margin: 2rem 0;'>", unsafe_allow_html=True)

        # Bottom 2 columns for charts
        col6, col7 = st.columns(2)
        with col6:
            st.subheader("Chart: Heart Rate")
            chart1 = st.empty()
        with col7:
            st.subheader("Chart: Heart Rate Variability (RR)")
            chart2 = st.empty()

    # Chatbox
    with main_col2:
        st.subheader("LLM Chat Box")
        with st.expander("Chat with the LLM", expanded=True):
            placeholder = st.empty()
            if llm_enabled:
                if "openai_model" not in st.session_state:
                    st.session_state["openai_model"] = "gpt-4o-mini"

                if "messages" not in st.session_state:
                    st.session_state.messages = []

                with placeholder.container():
                    for message in st.session_state.messages:
                        with st.chat_message(message["role"]):
                            st.markdown(message["content"])

                prompt = st.chat_input("Ask about your performance and strategy...")
                if prompt:
                    st.session_state.messages.append({"role": "user", "content": prompt})
                    with placeholder.container():
                        with st.chat_message("user"):
                            st.markdown(prompt)

                    modified_prompt = f'''Please analyse trends in stress.
                    Right now I am presenting in big meeting. Here is data
                    {st.session_state.stress_trend}.
                    Current HR: {st.session_state.hr_avg:.1f},
                    Current RMSSD: {st.session_state.rmssd:.4f},
                    Stress Status: {st.session_state.stress_result}
                    from ML model with confidence
                    {st.session_state.confidence:.1%}).
                    {prompt} Give response in 10 words'''
                    api_messages = [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.messages[:-1]
                    ] + [{"role": "user", "content": modified_prompt}]

                    with placeholder.container():
                        with st.chat_message("assistant"):
                            stream = client.chat.completions.create(
                                model=st.session_state["openai_model"],
                                messages=api_messages,
                                stream=True,
                            )
                            response = st.write_stream(stream)
                    st.session_state.messages.append({"role": "assistant", "content": response})
            else:
                st.info(
                    "LLM features are disabled. Add your OpenAI API key "
                    "to .env to enable chat and insights."
                )

    st.markdown("<hr style='margin: 2rem 0;'>", unsafe_allow_html=True)


    # Load your trained model and scaler
    try:
        model = joblib.load(MODEL_PATH)
        scaler = joblib.load(SCALER_PATH)
        print("Stress prediction model and scaler loaded successfully!")
    except FileNotFoundError:
        print("Model or scaler file not found.")
        model = None
        scaler = None

    hrv_list = []
    hr_list = []
    last_stress_prediction_time = 0
    prediction_interval = 15  # seconds
    stress_result = "NEUTRAL"
    column4_response = ""
    stress_auto = ""
    a = 0
    rmssd = 0


    def predict_stress(hr, rmssd):
        """Predict stress level using the trained model"""
        if model is None:
            return "MODEL_NOT_LOADED", 0.0

        try:
            hr_float = float(hr)
            rmssd_float = float(rmssd)
        except (ValueError, TypeError):
            return "INVALID_INPUT", 0.0

        features = np.array([[hr_float, rmssd_float]])

        # Scale features using the scaler
        if scaler is not None:
            features_scaled = scaler.transform(features)
        else:
            features_scaled = features

        try:
            prediction = model.predict(features_scaled)[0]
            probability = model.predict_proba(features_scaled)[0][1]

            if prediction == 1:
                result = "STRESS"
                confidence = probability
            else:
                result = "NO_STRESS"
                confidence = 1 - probability

            return result, confidence
        except Exception:
            return "PREDICTION_ERROR", 0.0


    def calculate_rmssd(rr_intervals):
        """Calculate RMSSD from RR intervals"""
        global rmssd
        if len(rr_intervals) < 2:
            return None

        try:
            rr_array = np.array([float(rr) for rr in rr_intervals if rr is not None and rr > 0])

            if len(rr_array) < 2:
                return None

            diff_rr = np.diff(rr_array)
            sq_diff_rr = diff_rr ** 2
            mean_sq_diff = np.mean(sq_diff_rr)
            rmssd = np.sqrt(mean_sq_diff)

            return rmssd
        except Exception:
            return None


    def print_hr_data(data):
        """Callback to print HR/HRV and stress prediction"""
        global hrv_list, hr_list, last_stress_prediction_time
        global stress_result, column4_response, stress_auto
        global a, confidence, hr_avg, rmssd

        if isinstance(data, tuple) and len(data) >= 3:
            hr_data = data[2]

            if isinstance(hr_data, tuple) and len(hr_data) >= 1:
                hr = hr_data[0]
                hrv = hr_data[1] if len(hr_data) > 1 else None

                current_time = time.time()

                if hr is not None:
                    hr_list.append(hr)

                if hrv is not None:
                    if isinstance(hrv, list):
                        hrv_list.extend(hrv)
                    elif isinstance(hrv, (int, float)):
                        hrv_list.append(hrv)

                if hr is not None:
                    print(f"HR: {hr} bpm, HRV in RR:{hrv} ms")

                    new_data = pd.DataFrame([[hr, hrv]], columns=["hr", "hrv"])
                    st.session_state.df = pd.concat([st.session_state.df, new_data], ignore_index=True)

                    if len(st.session_state.df) > 0:
                        fig1 = go.Figure()
                        fig1.add_trace(go.Scatter(x=st.session_state.df.index, y=st.session_state.df['hr'], mode='lines', name='HR'))
                        fig1.update_layout(title='Heart Rate', xaxis_title='Time', yaxis_title='BPM')
                        chart1.plotly_chart(fig1, use_container_width=True)

                        fig2 = go.Figure()
                        fig2.add_trace(go.Scatter(x=st.session_state.df.index, y=st.session_state.df['hrv'], mode='lines', name='HRV'))
                        fig2.update_layout(title='Heart Rate Variability (RMSSD)', xaxis_title='Time', yaxis_title='ms')
                        chart2.plotly_chart(fig2, use_container_width=True)

                time_since_last = current_time - last_stress_prediction_time
                if time_since_last >= prediction_interval:
                    if len(hr_list) >= 5 and len(hrv_list) >= 3:
                        hr_avg = np.mean(hr_list[-10:])
                        recent_rr = hrv_list[-20:] if len(hrv_list) >= 20 else hrv_list
                        rmssd = calculate_rmssd(recent_rr)
                        a = 1

                        if rmssd is not None and model is not None:
                            stress_result, confidence = predict_stress(hr_avg, rmssd)

                            if stress_result == "STRESS":
                                stress_auto = "STRESS"
                                print(
                                    f"STRESS: HR={hr_avg:.1f}, "
                                    f"RMSSD={rmssd:.4f} "
                                    f"(Confidence: {confidence:.1%})"
                                )
                                trend_msg = (
                                    f"STRESS: Avg HR={hr_avg:.1f}, "
                                    f"Avg in 15 seconds RMSSD={rmssd:.4f} "
                                    f"(Confidence Score: {confidence:.1%})"
                                )
                                st.session_state.stress_trend += trend_msg
                            else:
                                print(
                                    f"NO STRESS: HR={hr_avg:.1f}, "
                                    f"RMSSD={rmssd:.4f} "
                                    f"(Confidence: {confidence:.1%})"
                                )
                                stress_auto = "NO STRESS"
                                trend_msg = (
                                    f"NO STRESS: Avg HR={hr_avg:.1f}, "
                                    f"Avg in 15 seconds RMSSD={rmssd:.4f} "
                                    f"(Confidence Score: {confidence:.1%})"
                                )
                                st.session_state.stress_trend += trend_msg
                            print(st.session_state.stress_trend)
                        last_stress_prediction_time = current_time

                    if len(hr_list) > 50:
                        hr_list = hr_list[-30:]
                    if len(hrv_list) > 100:
                        hrv_list = hrv_list[-50:]

                with ph1.container():
                    st.markdown("<span style='font-size:60px;'>❤</span>", unsafe_allow_html=True)
                    st.markdown(
                        f"<span style='font-size:40px;'>HR:{hr} bpm</span>",
                        unsafe_allow_html=True,
                    )
                with ph2.container():
                    st.markdown("<span style='font-size:60px;'>📈</span>", unsafe_allow_html=True)
                    st.markdown(
                        f"<span style='font-size:40px;'>HRV:{hrv} ms</span>",
                        unsafe_allow_html=True,
                    )
                with ph3.container():
                    if stress_result == "STRESS":
                        gauge_value = confidence
                        gauge_color = "Red"
                    else:
                        gauge_value = 1 - confidence
                        gauge_color = "Green"

                    fig = go.Figure(go.Indicator(
                        mode = "gauge+number",
                        value = gauge_value,
                        domain = {'x': [0, 1], 'y': [0, 1]},
                        title = {'text': "Stress Level"},
                        gauge = {'axis': {'range': [None, 1]},
                                 'bar': {'color': gauge_color},
                                 'steps' : [
                                     {'range': [0, 0.5], 'color': "lightgray"},
                                     {'range': [0.5, 1], 'color': "gray"}],
                                 'threshold' : {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 0.8}}))
                    ph3.plotly_chart(fig, use_container_width=True)

                with ph4.container():
                    if stress_result == "NEUTRAL":
                        st.markdown(
                            "<span style='font-size:60px;'>ML 😐</span>",
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            "<span style='font-size:40px;'>Predicting Stress...</span>",
                            unsafe_allow_html=True,
                        )
                    elif stress_result == "STRESS":
                        st.markdown(
                            "<span style='font-size:60px;'>ML 😰</span>",
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            "<span style='font-size:40px;'>Stress</span>",
                            unsafe_allow_html=True,
                        )
                        if rmssd is not None:
                            st.markdown(
                                f"<span style='font-size:20px;'>"
                                f"HR={hr_avg:.1f}, RMSSD={rmssd:.4f} "
                                f"(Confidence: {confidence:.1%})</span>",
                                unsafe_allow_html=True,
                            )
                    else:
                        st.markdown(
                            "<span style='font-size:60px;'>ML 😊</span>",
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            "<span style='font-size:40px;'>No Stress</span>",
                            unsafe_allow_html=True,
                        )
                        if rmssd is not None:
                            st.markdown(
                                f"<span style='font-size:20px;'>"
                                f"HR={hr_avg:.1f}, RMSSD={rmssd:.4f} "
                                f"(Confidence: {confidence:.1%})</span>",
                                unsafe_allow_html=True,
                            )

                if a == 10:  # this is should be 1
                    hardcoded_prompt = f'''Analyze and suggest actionable
                    insight based on average heart rate {hr_avg},
                    average RMSSD {rmssd},
                    and stress predicted from ML model which is
                    {stress_auto} with confidence {confidence}.
                    Right now I am giving a presentation on big meeting.
                    Please suggest actionable insight in 10 words'''

                    stream = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": hardcoded_prompt}],
                        stream=True,
                    )
                    column4_response = ""
                    for chunk in stream:
                        if chunk.choices[0].delta.content is not None:
                            column4_response += chunk.choices[0].delta.content
                    a = 0

                with ph5.container():
                    st.markdown("<span style='font-size:60px;'>LLM 📄</span>", unsafe_allow_html=True)
                    st.markdown(
                        f"<span style='font-size:20px;'>"
                        f"{column4_response}</span>",
                        unsafe_allow_html=True,
                    )


    def mock_ble_data():
        """Generate mock heart rate data for UI testing."""
        hr = 70
        hrv = 40
        while True:
            hr += np.random.randint(-2, 3)
            hrv += np.random.randint(-3, 4)
            hr = np.clip(hr, 60, 100)
            hrv = np.clip(hrv, 30, 60)
            print_hr_data((None, None, (hr, [hrv])))
            time.sleep(1)


    async def main():
        global last_stress_prediction_time

        print("Searching for Polar H10...")

        last_stress_prediction_time = time.time()

        try:
            device = await BleakScanner.find_device_by_filter(
                lambda dev, adv: dev.name and "polar h10" in dev.name.lower()
            )

            if not device:
                print("Polar H10 device not found")
                return

            print(f"Found: {device.name}")

            async with BleakClient(device) as client:
                heartrate = bh.HeartRate(
                    client,
                    callback=print_hr_data,
                    instant_rate=True,
                    unpack=True,
                )
                await heartrate.start_notify()

                try:
                    while True:
                        await aio.sleep(1)
                except KeyboardInterrupt:
                    await heartrate.stop_notify()
                    print("Stopped")

        except Exception as e:
            print(f"Error: {e}")

    if "mock" in st.query_params and st.query_params["mock"][0] == "true":
        mock_ble_data()
    else:
        try:
            aio.run(main())
        except KeyboardInterrupt:
            print("Goodbye!")
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    if check_password():
        main_app()
