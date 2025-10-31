from bleak import BleakScanner, BleakClient
import asyncio as aio
import bleakheart as bh
import numpy as np
import joblib
import pandas as pd
import time
import warnings
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
import queue
import os

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
    llm_enabled = True
else:
    client = None
    llm_enabled = False
warnings.filterwarnings('ignore')
stress_trend = ""

st.set_page_config(
    page_title="Polar AWE",
    page_icon="❤️",
    layout="wide"
)

st.title("Polar AWE: Stress Monitoring with ML and LLM")
st.markdown("<hr style='margin: 0.5rem 0;'>", unsafe_allow_html=True)

# Initialize session state for persistent data
if 'hr_data' not in st.session_state:
    st.session_state.hr_data = pd.DataFrame(columns=["hr", "hrv"])
if 'stress_result' not in st.session_state:
    st.session_state.stress_result = "NEUTRAL"
if 'column4_response' not in st.session_state:
    st.session_state.column4_response = "Waiting for data..."
if 'stress_trend' not in st.session_state:
    st.session_state.stress_trend = ""
if 'hr_avg' not in st.session_state:
    st.session_state.hr_avg = 0
if 'rmssd' not in st.session_state:
    st.session_state.rmssd = 0
if 'confidence' not in st.session_state:
    st.session_state.confidence = 0
if 'ble_data_queue' not in st.session_state:
    st.session_state.ble_data_queue = queue.Queue()
if 'ble_running' not in st.session_state:
    st.session_state.ble_running = False
if 'latest_hr' not in st.session_state:
    st.session_state.latest_hr = 0
if 'latest_hrv' not in st.session_state:
    st.session_state.latest_hrv = 0
if "messages" not in st.session_state:
    st.session_state.messages = []
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame(columns=["hr", "hrv"])

# Top 4 columns for metrics
col1, col2, col3, col4 = st.columns(4)
with col1:
    ph1 = st.empty()
    ph1.markdown(
        "<span style='font-size:60px;'>❤️</span>",
        unsafe_allow_html=True
    )
    ph1.markdown(
        "<span style='font-size:40px;'>HR: -- bpm</span>",
        unsafe_allow_html=True
    )
with col2:
    ph2 = st.empty()
    ph2.markdown(
        "<span style='font-size:60px;'>📈</span>",
        unsafe_allow_html=True
    )
    ph2.markdown(
        "<span style='font-size:40px;'>HRV: -- ms</span>",
        unsafe_allow_html=True
    )
with col3:
    ph3 = st.empty()
    ph3.markdown(
        "<span style='font-size:60px;'>😊</span>",
        unsafe_allow_html=True
    )
    ph3.markdown(
        "<span style='font-size:40px;'>No Stress</span>",
        unsafe_allow_html=True
    )
with col4:
    ph4 = st.empty()
    ph4.markdown(
        "<span style='font-size:60px;'>📄</span>",
        unsafe_allow_html=True
    )
    ph4.markdown(
        "<span style='font-size:20px;'>--</span>",
        unsafe_allow_html=True
    )

st.markdown("<hr style='margin: 2rem 0;'>", unsafe_allow_html=True)

# Bottom 3 columns for charts and chat
col5, col6, col7 = st.columns(3)
with col5:
    st.subheader("Chart: Heart Rate")
    chart1 = st.line_chart(st.session_state.df[["hr"]])
with col6:
    st.subheader("Chart: Heart Rate Variability (RR)")
    chart2 = st.line_chart(st.session_state.df[["hrv"]])

# Chatbox
with col7:
    st.subheader("LLM Chat Box")
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

        prompt = st.chat_input(
            "Ask about your performance and strategy..."
        )
        if prompt:
            st.session_state.messages.append(
                {"role": "user", "content": prompt}
            )
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
            st.session_state.messages.append(
                {"role": "assistant", "content": response}
            )
    else:
        st.info(
            "LLM features are disabled. Add your OpenAI API key "
            "to .env to enable chat and insights."
        )

st.markdown("<hr style='margin: 2rem 0;'>", unsafe_allow_html=True)

# Load your trained model and scaler
try:
    model = joblib.load('stress_prediction_model.pkl')
    scaler = joblib.load('scaler.pkl')
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
        rr_array = np.array([
            float(rr) for rr in rr_intervals
            if rr is not None and rr > 0
        ])

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
                st.session_state.df = pd.concat(
                    [st.session_state.df, new_data],
                    ignore_index=True
                )

                if len(st.session_state.df) > 0:
                    chart1.add_rows(new_data[["hr"]])
                    chart2.add_rows(new_data[["hrv"]])

            time_since_last = current_time - last_stress_prediction_time
            if time_since_last >= prediction_interval:
                if len(hr_list) >= 5 and len(hrv_list) >= 3:
                    hr_avg = np.mean(hr_list[-10:])
                    recent_rr = (hrv_list[-20:]
                                 if len(hrv_list) >= 20
                                 else hrv_list)
                    rmssd = calculate_rmssd(recent_rr)
                    a = 1

                    if rmssd is not None and model is not None:
                        stress_result, confidence = predict_stress(
                            hr_avg, rmssd
                        )

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
                st.markdown(
                    "<span style='font-size:60px;'>❤️</span>",
                    unsafe_allow_html=True
                )
                st.markdown(
                    f"<span style='font-size:40px;'>HR:{hr} bpm</span>",
                    unsafe_allow_html=True
                )
            with ph2.container():
                st.markdown(
                    "<span style='font-size:60px;'>📈</span>",
                    unsafe_allow_html=True
                )
                st.markdown(
                    f"<span style='font-size:40px;'>HRV:{hrv} ms</span>",
                    unsafe_allow_html=True
                )
            with ph3.container():
                if stress_result == "NEUTRAL":
                    st.markdown(
                        "<span style='font-size:60px;'>ML 😐</span>",
                        unsafe_allow_html=True
                    )
                    st.markdown(
                        "<span style='font-size:40px;'>"
                        "Predicting Stress...</span>",
                        unsafe_allow_html=True
                    )
                elif stress_result == "STRESS":
                    st.markdown(
                        "<span style='font-size:60px;'>ML 😰</span>",
                        unsafe_allow_html=True
                    )
                    st.markdown(
                        "<span style='font-size:40px;'>Stress</span>",
                        unsafe_allow_html=True
                    )
                    if rmssd is not None:
                        st.markdown(
                            f"<span style='font-size:20px;'>"
                            f"HR={hr_avg:.1f}, RMSSD={rmssd:.4f} "
                            f"(Confidence: {confidence:.1%})</span>",
                            unsafe_allow_html=True
                        )
                else:
                    st.markdown(
                        "<span style='font-size:60px;'>ML 😊</span>",
                        unsafe_allow_html=True
                    )
                    st.markdown(
                        "<span style='font-size:40px;'>No Stress</span>",
                        unsafe_allow_html=True
                    )
                    if rmssd is not None:
                        st.markdown(
                            f"<span style='font-size:20px;'>"
                            f"HR={hr_avg:.1f}, RMSSD={rmssd:.4f} "
                            f"(Confidence: {confidence:.1%})</span>",
                            unsafe_allow_html=True
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

            with ph4.container():
                st.markdown(
                    "<span style='font-size:60px;'>LLM 📄</span>",
                    unsafe_allow_html=True
                )
                st.markdown(
                    f"<span style='font-size:20px;'>"
                    f"{column4_response}</span>",
                    unsafe_allow_html=True
                )


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
                unpack=True
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


if __name__ == "__main__":
    try:
        aio.run(main())
    except KeyboardInterrupt:
        print("Goodbye!")
