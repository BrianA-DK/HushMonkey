#-----------------------------------------------------------------------------
# Copyright (C) 2026 Brian J. Andersen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#-----------------------------------------------------------------------------


import gevent
from gevent import monkey
monkey.patch_all()

from flask import Flask, send_from_directory, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room  ### NYT
import numpy as np
import sounddevice as sd
from scipy.signal import bilinear, lfilter
import threading 
import time
from collections import deque
import json
#import multiprocessing
import os
import datetime
import signal
from gevent.queue import Queue
import queue
import sys
import subprocess


# =========================
# Init
# =========================
app = Flask(__name__)
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins="*")
threadstop = False;



t = None # Thread reference
audio_queue = Queue(maxsize=10) # We have boundaries

WATERFALL_HISTORY = deque(maxlen=300)
        
# =========================
# CLEAN SHUTDOWN
# =========================
def shutdown_clean():
    global threadstop
    print("\\nShutting down background threads...", flush=True)
    threadstop = True
    
    start_wait = time.time()
    
    # Wait for audio-thread (t) and dsp-thred (t_dsp) to die in a nice way
    while (t and t.is_alive()) or (t_dsp and t_dsp.is_alive()):
        # Timeout 3 sec, then we kill kill kill
        if (time.time() - start_wait) > 3.0:
            print("Thread timeout reached. Forcing exit.", flush=True)
            break
        time.sleep(0.1)
        
    print("All threads stopped. Exiting.", flush=True)
    os._exit(0)

# =========================
# CLEAN KILL
# =========================
def kill_clean(exit_cmd):
    global threadstop
    print("\\nShutting down background threads...", flush=True)
    threadstop = True
    
    start_wait = time.time()
    
    # Wait for audio-thread (t) and dsp-thred (t_dsp) to die in a nice way - wait a minute, I've seen this before... -^
    while (t and t.is_alive()) or (t_dsp and t_dsp.is_alive()):
        # Timeout yada yada yada, same again
        if (time.time() - start_wait) > 3.0:
            print("Thread timeout reached. Forcing exit.", flush=True)
            break
        time.sleep(0.1)
        
    print("All threads stopped. Killing.", flush=True)
    try:
        with open("/tmp/hushmonkey_panic", "w") as f:
            f.write(exit_cmd)
    except Exception as e:
        print(f"Could not write to panicfile: {e}")
    master_pid = os.getppid()
    os.kill(master_pid, signal.SIGTERM) # Kill Gunicorn master
    sys.exit(0) # kill worker
    
# =========================
# RECONFIG SOUNDDEVICE
# =========================
def resound():
    bash_script = """
    USB_LINE=$(grep -i "usb" /proc/asound/cards | head -n 1)

    if [ -n "$USB_LINE" ]; then
        USB_CARD_NUM=$(echo "$USB_LINE" | awk '{print $1}')
        USB_CARD_ID=$(echo "$USB_LINE" | cut -d '[' -f2 | cut -d ']' -f1 | xargs)
        USB_CARD_DESC=$(echo "$USB_LINE" | cut -d ':' -f2- | xargs)
        
        echo "resound: Found: $USB_CARD_DESC"
        echo "resound: ALSA-Setup: Using device-index $USB_CARD_NUM [$USB_CARD_ID]"
        
        SCONTROL=$(amixer -c "$USB_CARD_NUM" scontrols | head -n 1 | cut -d"'" -f2)
        
        if [ -n "$SCONTROL" ]; then
            echo "resound: Adjust volumen-control '$SCONTROL' to 100%..."
            amixer -c "$USB_CARD_NUM" sset "$SCONTROL" 100% unmute > /dev/null 2>&1
            echo "resound: USB-sounddevice is configured and unmuted!"
        else
            echo "resound: WARNING: USB-device found, but no mixer-control."
        fi
    else
        echo "resound: INFO: No USB sound device found in ALSA. Using system defaults (This might go wrong)"
    fi
    """
    # run scriptet in a bash-shell 
    resultat = subprocess.run(
        bash_script, 
        shell=True, 
        executable="/bin/bash", # bash, only bash
        capture_output=True, 
        text=True
    )

    return resultat.stdout



# =========================
# A-weighting
# =========================
def a_weighting(fs):
    f1, f2, f3, f4 = 20.598997, 107.65265, 737.86223, 12194.217
    A1000 = 1.9997

    nums = [(2*np.pi*f4)**2 * (10**(A1000/20)), 0, 0, 0, 0]
    dens = np.polymul([1, 4*np.pi*f4, (2*np.pi*f4)**2],
           np.polymul([1, 4*np.pi*f1, (2*np.pi*f1)**2],
           np.polymul([1, 2*np.pi*f3],
                      [1, 2*np.pi*f2])))

    b, a = bilinear(nums, dens, fs)
    return b, a

# =========================
# PINK NOISE GENERATOR
# =========================
def generate_pink_noise(duration, fs=48000):
    n_samples = int(duration * fs)
    white = np.random.randn(n_samples)
    fourier = np.fft.rfft(white)
    frequencies = np.fft.rfftfreq(n_samples, d=1/fs)
    
    scalers = np.zeros_like(frequencies)
    scalers[1:] = 1.0 / np.sqrt(frequencies[1:])
    
    pink_fourier = fourier * scalers
    pink = np.fft.irfft(pink_fourier)
    print("Genrated pink noise")
    return (pink / np.max(np.abs(pink))).astype(np.float32)

# =========================
# CONFIG
# =========================
m_time = os.path.getmtime(os.getcwd() + "/main.py")
dt = datetime.datetime.fromtimestamp(m_time)
versid = "0.3a - Grumpy Gorilla (" + dt.strftime("%Y-%m-%d %H:%M:%S") + ")"

LOG_FILE_PATH = "/var/log/hushmonkey.log"
log_watcher_active = False
log_viewer_count = 0  # num of active log viewers

fs = 48000
chunk = 2048 # was 1024

REF = 0.01  # Dummy calibration (changed via web)
LAF_limit = 1.01
LAeq1_limit = 2.02
LAeq10_limit = 3.03
b, a = a_weighting(fs)

measurement_mode = "spl"  # "spl" / "transfer"
pink_noise_buffer = generate_pink_noise(10, fs=48000)
play_ptr = 0

G_xx_smooth = None
G_yy_smooth = None
G_xy_smooth = None

locked_delay_samples = 0
current_delay_mode = "auto"     # "auto", "lock" or "manual"
manual_delay_offset = 0
locked_delay = 0
last_found_delay = 0

# =========================
# CONFIG — replace deques with running-sum accumulators
# =========================
chunks_per_sec = fs / chunk # Ca. 46.875 chunks per sec
buf_1m  = deque(maxlen=int(chunks_per_sec *  60)) # Ca.  2812 elements
buf_10m = deque(maxlen=int(chunks_per_sec * 600)) # Ca. 28125 elements

raw_audio_queue = queue.Queue(maxsize=100)

# update_predictions runs every 1 sec. 
# maxlen=30 give equals the last 30 sec. history
trend_buf = deque(maxlen=30)

sum_1m  = 0.0
sum_10m = 0.0

cfg_load_error = 99
limits_load_err = 99
device_load_err = 99

fft_buf = deque(maxlen=16384)   # ca. 85 ms @ 48 kHz

# Spectrum smoothing + peak hold
spectrum_smooth = None
spectrum_peak = None
peak_mode = "slow"   # slow / fast
yaxis_mode = "wide"   # wide / narrow

# IEC 1/3-octave centers
centers = [
    20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630,
    800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000
]

laf_time = 0
la1_time = 0
la10_time= 0
lafwarn_time=0
l1warn_time=0
l10warn_time=0

# =========================
# Setup dict
# =========================
state = {
    "LAF": 0.0,
    "LAeq1m": 0.0,
    "LAeq10m": 0.0,
    "MAX_LAF": -999.0,
    "MAX_1M": -999.0,
    "MAX_10M": -999.0,
    "LAeq10_trend": "stabil",  # + rising, - falling, 0 stable
    "LAeq10_rate": 0.0,        # dB pr. minut
    "LAeq10_eta": -1,          # Sec to breaking limit (-1 = infinity/safe)
    "L90": 0.0,                # L90% = background noise
    "L10": 0.0                 # L10% Peak noise
}

mic_data = {
    "NAME": "None selected",
    "REF": REF,
    "NOTES": "None"
}

limits = {
    "LAF_limit": LAF_limit,
    "LAeq1_limit": LAeq1_limit,
    "LAeq10_limit": LAeq10_limit,
    "LAFwarn": 3,
    "L1warn": 3,
    "L10warn": 3,
    "alert_delay": 5
}

warn = {
    "LAF_warn" : False,
    "LA1_warn" : False,
    "LA10_warn": False,
    "LAFwarn"  : False,
    "L1warn"   : False,
    "L10warn"  : False
}

cal_session = {
    "running": False,
    "target_db": None,
    "samples": [],
    "final_rms": None
}

transfer_state = {
    "delay_samples": 0,
    "delay_ms": 0.0,
    "freqs": [],
    "phase": [],
    "coherence": [],
    "magnitude": []
}

sound_dev = {
    "alsa_index": 0,
    "id": "none",
    "name": "none",
    "device_string": "none"

}

# =========================
# Save and LOAD config
# =========================
def save_config(filnavn):
    try:
        with open(filnavn, "w") as f:
            json.dump(mic_data, f, indent=4)
        return True, "Saved calibration to '"+filnavn+"'"
    except OSError as e:
        return False, str(e)   

def load_config(filnavn):
    try:
        with open(filnavn, "r") as f:
            return json.load(f), 0
        
    except (FileNotFoundError, json.JSONDecodeError):
            return {
                "NAME": "None selected",
                "REF": 0.09,
                "NOTES": "None"
            }, 1

def save_limits(filnavn):
    with open(filnavn, "w") as f:
        json.dump(limits, f, indent=4)
        print("Limits updated:", limits, flush=True)

def load_limits(filnavn):
    try:
        with open(filnavn, "r") as f:
            return json.load(f), 0
        
    except (FileNotFoundError, json.JSONDecodeError):
            return {
                "LAF_limit": 1.0,
                "LAeq1_limit": 2.0,
                "LAeq10_limit": 3.0,
                "LAFwarn": 4,
                "L1warn": 5,
                "L10warn": 6,
                "alert_delay": 7
            }, 1

def save_device(filnavn, dev):
    try:
        with open(filnavn, "w") as f:
            json.dump(dev, f, indent=4)
        return True, "Saved default sound device to '"+filnavn+"'"
    except OSError as e:
        return False, str(e)   

def load_device(filnavn):
    try:
        with open(filnavn, "r") as f:
            return json.load(f), 0
        
    except (FileNotFoundError, json.JSONDecodeError):
            return {
                "alsa_index": -1,
                "id": "err",
                "name": "err",
                "device_string": "err"
            }, 1

def loadCurve(filnavn):
    try:
        with open(filnavn, "r") as f:
            curve = json.load(f)
            print("Load curve:",filnavn, " / Data :",curve, flush=True)
            return curve,0
    except (FileNotFoundError, json.JSONDecodeError): 
            return {"msg":"err"},1

        
def saveCurve(filnavn):
    try:
        with open(filnavn, "w") as f:
            json.dump(dev, f, indent=4)
        return True, "Saved default sound device to '"+filnavn+"'"
    except OSError as e:
        return False, str(e)
        
# =========================
# TRANSFER & DELAY CALC
# =========================
def find_delay(mic_chunk, ref_chunk):
    # Determines the time shift via cross-correlation in the frequency domain
    N = len(mic_chunk)
    # Kør FFT på begge signaler
    X = np.fft.fft(ref_chunk)
    Y = np.fft.fft(mic_chunk)
    
    # Calc cross-power spectrum (G_xy)
    R = Y * np.conj(X)
    
    # invers FFT to time domain
    cc = np.fft.ifft(R)
    
    # Find index (sample), with biggest peak
    delay_samples = np.argmax(np.abs(cc))
    
    # Correct if the peak is in the negative time 
    if delay_samples > N // 2:
        delay_samples -= N
        
    delay_ms = (delay_samples / fs) * 1000.0
    return int(delay_samples), float(delay_ms)

def compute_transfer_function(mic_signal, ref_signal, delay_samples):
    # adj ref and calc magnitude, phase and coherence
    # DENNE SKAl MÅSKE IKKE BRUGE MERE
    global G_xx_smooth, G_yy_smooth, G_xy_smooth
    
    N = len(mic_signal)
    window = np.hanning(N)
    
    # 1. Adj time
    ref_synced = np.roll(ref_signal, delay_samples)
    
    # 2. FFT of both signals
    X = np.fft.rfft(ref_synced * window)
    Y = np.fft.rfft(mic_signal * window)
    
    # 3. Cross- og Auto-spectra
    G_xy_instant = Y * np.conj(X)
    G_xx_instant = X * np.conj(X)
    G_yy_instant = Y * np.conj(Y)
    
    # 4. Averaging over tme
    alpha = 0.15 
    
    if G_xx_smooth is None or len(G_xx_smooth) != len(G_xx_instant):
        G_xx_smooth = G_xx_instant.copy()
        G_yy_smooth = G_yy_instant.copy()
        G_xy_smooth = G_xy_instant.copy()
    else:
        G_xx_smooth = alpha * G_xx_instant + (1 - alpha) * G_xx_smooth
        G_yy_smooth = alpha * G_yy_instant + (1 - alpha) * G_yy_smooth
        G_xy_smooth = alpha * G_xy_instant + (1 - alpha) * G_xy_smooth
    
    # 5. Calc H (transfer function) from avg spectra
    H = G_xy_smooth / (G_xx_smooth + 1e-12)
    phase_deg = np.angle(H, deg=True)
    
    # 6. Magnitude in dB
    # absolutte value of H (amplitude relation) convert to  dB
    magnitude_db = 20 * np.log10(np.abs(H) + 1e-12)
    
    # 7. Calc from avg. spectra
    coherence_val = (np.abs(G_xy_smooth) ** 2) / (G_xx_smooth * G_yy_smooth + 1e-12)
    coherence_val = np.clip(coherence_val, 0.0, 1.0)
    
    # 8. Create freq-vector
    freqs = np.fft.rfftfreq(N, d=1/fs)
    
    # 9. Convert to JSON'ish lists
    freqs_list = [float(f.real) for f in freqs]
    phase_list = [float(p.real) for p in phase_deg]
    coherence_list = [float(c.real) for c in coherence_val]
    magnitude_list = [float(m.real) for m in magnitude_db] # NY
    
    return freqs_list, phase_list, coherence_list, magnitude_list

def compute_transfer_function_and_ir(mic_signal, ref_signal, current_delay_samples, delay_mode="auto", manual_offset_samples=0):
    # adj ref and calc magnitude, phase and coherence
    # delay_mode: "auto" | "lock" | "manual"
    #manual_offset_samples: offset in samples send from frontend  + / -

    global G_xx_smooth, G_yy_smooth, G_xy_smooth, locked_delay_samples

    N = len(mic_signal)
    window = np.hanning(N)
    
    # 1. delay type
    if delay_mode == "auto":
        used_delay = current_delay_samples
        locked_delay_samples = current_delay_samples  # Opdaterer gemt værdi
    elif delay_mode == "lock":
        used_delay = locked_delay_samples
    elif delay_mode == "manual":
        used_delay = locked_delay_samples + manual_offset_samples
        #locked_delay_samples = used_delay  # Gem den nye manuelle status
        
    # 2. time adj. reference with delay
    ref_synced = np.roll(ref_signal, used_delay)
    
    # 3. FFT 
    X = np.fft.rfft(ref_synced * window)
    Y = np.fft.rfft(mic_signal * window)
    
    # 4. Averaging
    alpha = 0.15 
    if G_xx_smooth is None or len(G_xx_smooth) != len(X):
        G_xx_smooth = X * np.conj(X)
        G_yy_smooth = Y * np.conj(Y)
        G_xy_smooth = Y * np.conj(X)
    else:
        G_xx_smooth = alpha * (X * np.conj(X)) + (1 - alpha) * G_xx_smooth
        G_yy_smooth = alpha * (Y * np.conj(Y)) + (1 - alpha) * G_yy_smooth
        G_xy_smooth = alpha * (Y * np.conj(X)) + (1 - alpha) * G_xy_smooth
    
    # 5. Calc H (transfer function) 
    H = G_xy_smooth / (G_xx_smooth + 1e-12)
    phase_deg = np.angle(H, deg=True)
    magnitude_db = 20 * np.log10(np.abs(H) + 1e-12)
    
    # 6. Coherence
    coherence_val = (np.abs(G_xy_smooth) ** 2) / (G_xx_smooth * G_yy_smooth + 1e-12)
    coherence_val = np.clip(coherence_val, 0.0, 1.0)
    
    # 7. IMPULSRESPONCE (IR) via iFFT
    # ir_time_domain is signal in timedomain (amplitude over time)
    ir_raw = np.fft.irfft(H)
    
    # Let move IR to make 0ms center on graph
    ir_shifted = np.fft.fftshift(ir_raw)
    
    # Normalize IR-amplitude to a nice interval (eg -1.0 to 1.0 or 0 to 100%)
    max_val = np.max(np.abs(ir_shifted)) + 1e-12
    ir_normalized = ir_shifted / max_val

    # time axis for IR in ms
    time_ms = (np.arange(len(ir_normalized)) - len(ir_normalized) // 2) * (1000.0 / fs)
    
    # 8. Create freq-vector
    freqs = np.fft.rfftfreq(N, d=1/fs)
    
    # 9. Return JSON'ish lists and reduce IR timespan eg. 512-1024 points in the middle
    center_idx = len(ir_normalized) // 2
    span = 512 # time windows around 0 ms
    
    ir_slice = ir_normalized[center_idx - span : center_idx + span]
    time_slice = time_ms[center_idx - span : center_idx + span]

    return {
        'freqs': [float(f) for f in freqs],
        'phase': [float(p) for p in phase_deg],
        'coherence': [float(c) for c in coherence_val],
        'magnitude': [float(m) for m in magnitude_db],
        'delay_samples': int(used_delay),
        'delay_ms': float((used_delay / fs) * 1000.0),
        'ir_time': [float(t) for t in time_slice],
        'ir_amplitude': [float(a) for a in ir_slice]
    }

def compute_transfer_function_and_ir_optimized(mic_signal, ref_signal, delay_mode="auto", manual_offset_samples=0):
    #Only perform FFT oncefor auto-delay, Transfer Function and IR.
    #Saves ~40% CPU on Raspberry Pi3+
 
    global G_xx_smooth, G_yy_smooth, G_xy_smooth, locked_delay_samples, last_found_delay

    N = len(mic_signal)
    window = np.hanning(N)
    
    # 1. SINGLE FFT PAS
    # We apply a window to the raw reference and microphone signalsl
    X_raw = np.fft.rfft(ref_signal * window)
    Y_raw = np.fft.rfft(mic_signal * window)
    
    # 2. DETERMINE AUTO-DELAY WITHOUT EXTRA FFT
    # Cross-spectrum of the unaligned signal
    R_raw = Y_raw * np.conj(X_raw)
    
    # Inverse FFT to find time shift (cross-correlation peak)
    cc = np.fft.irfft(R_raw)
    
    # Find the sample index with the largest deviation.
    auto_delay = np.argmax(np.abs(cc))
    if auto_delay > N // 2:
        auto_delay -= N
        
    last_found_delay = int(auto_delay)

    # 3. SELECT THE ACTUAL DELAY TO BE USED
    if delay_mode == "auto":
        used_delay = auto_delay
        locked_delay_samples = auto_delay
    elif delay_mode == "lock":
        used_delay = locked_delay_samples
    elif delay_mode == "manual":
        used_delay = locked_delay_samples + manual_offset_samples

    # 4. TIME ADJUST ON FREQUENCY (Phase rotation instead of np.roll)
    # np.roll in the time domain costs CPU. In the frequency domain, it is a simple phase shift
    freq_indices = np.arange(len(X_raw))
    phase_shift = np.exp(-1j * 2 * np.pi * freq_indices * used_delay / N)
    X = X_raw * phase_shift  # Time adj reference
    Y = Y_raw

    # 5. EXPONENTIAL AVERAGE OVER TIME
    alpha = 0.15 
    G_xx_instant = X * np.conj(X)
    G_yy_instant = Y * np.conj(Y)
    G_xy_instant = Y * np.conj(X)

    if G_xx_smooth is None or len(G_xx_smooth) != len(X):
        G_xx_smooth = G_xx_instant.copy()
        G_yy_smooth = G_yy_instant.copy()
        G_xy_smooth = G_xy_instant.copy()
    else:
        G_xx_smooth = alpha * G_xx_instant + (1 - alpha) * G_xx_smooth
        G_yy_smooth = alpha * G_yy_instant + (1 - alpha) * G_yy_smooth
        G_xy_smooth = alpha * G_xy_instant + (1 - alpha) * G_xy_smooth

    # 6. TRANSFER FUNCTION (H), PHASE AND MAGNITUDE
    H = G_xy_smooth / (G_xx_smooth + 1e-12)
    phase_deg = np.angle(H, deg=True)
    magnitude_db = 20 * np.log10(np.abs(H) + 1e-12)

    # 7. COHERENCE
    coherence_val = (np.abs(G_xy_smooth) ** 2) / (G_xx_smooth * G_yy_smooth + 1e-12)
    coherence_val = np.clip(coherence_val, 0.0, 1.0)

    # 8. IMPULSRESPONS (IR)
    ir_raw = np.fft.irfft(H)
    ir_shifted = np.fft.fftshift(ir_raw)
    
    max_val = np.max(np.abs(ir_shifted)) + 1e-12
    ir_normalized = ir_shifted / max_val
    time_ms = (np.arange(len(ir_normalized)) - len(ir_normalized) // 2) * (1000.0 / fs)

    # Cutdown slice for graph (512 points)
    center_idx = len(ir_normalized) // 2
    span = 256  # 256 per side = 512 points in total (saves on network & rendering)
    
    ir_slice = ir_normalized[center_idx - span : center_idx + span]
    time_slice = time_ms[center_idx - span : center_idx + span]
    freqs = np.fft.rfftfreq(N, d=1/fs)

    return {
        'freqs': [float(f) for f in freqs],
        'phase': [float(p) for p in phase_deg],
        'coherence': [float(c) for c in coherence_val],
        'magnitude': [float(m) for m in magnitude_db],
        'delay_samples': int(used_delay),
        'delay_ms': float((used_delay / fs) * 1000.0),
        'ir_time': [float(t) for t in time_slice],
        'ir_amplitude': [float(a) for a in ir_slice]
    }

# =========================
# DSP
# =========================
def process(x):
    y = lfilter(b, a, x)
    energy = y**2
    rms = np.sqrt(np.mean(energy) + 1e-12)
    laf = 20 * np.log10(rms / REF)
    return laf, energy, rms

# =========================
# DSP WORKER THREAD
# =========================
def processing_worker():
    global sum_1m, sum_10m, laf_time, la1_time, la10_time, lafwarn_time, l1warn_time, l10warn_time, last_prediction_time, REF
    
    local_push_counter = 0
    print("   DSP Processing Worker startet.", flush=True)
    
    while not threadstop:
        try:
            # Fetch the raw chunks (blocks until data is available, so no CPU waste)
            x_mic, x_ref = raw_audio_queue.get(timeout=1.0)
        except queue.Empty:
            continue

        # 1. Calculate SPL (A-weighting, RMS, etc.)
        laf, energy, rms = process(x_mic)
        fft_buf.extend(x_mic)

        if cal_session["running"]:
            cal_session["samples"].append(rms)

        chunk_sum = float(np.sum(energy))
        chunk_len = len(energy)

        # Buffer management
        if len(buf_1m) == buf_1m.maxlen: sum_1m -= buf_1m[0]
        buf_1m.append(chunk_sum)
        sum_1m += chunk_sum

        if len(buf_10m) == buf_10m.maxlen: sum_10m -= buf_10m[0]
        buf_10m.append(chunk_sum)
        sum_10m += chunk_sum

        n_1m  = len(buf_1m)  * chunk_len
        n_10m = len(buf_10m) * chunk_len

        leq1  = 10 * np.log10((sum_1m  / n_1m)  / (REF**2) + 1e-12) if n_1m > 0 else -120.0
        leq10 = 10 * np.log10((sum_10m / n_10m) / (REF**2) + 1e-12) if n_10m > 0 else -120.0

        state["LAF"] = float(laf)
        state["LAeq1m"] = float(leq1)
        state["LAeq10m"] = float(leq10)
        state["MAX_LAF"] = max(state["MAX_LAF"], laf)
        state["MAX_1M"]  = max(state["MAX_1M"],  leq1)
        state["MAX_10M"] = max(state["MAX_10M"], leq10)
        
        # Alarmer
        if state["LAF"] >= limits["LAF_limit"]:
            laf_time = time.time()
            warn["LAF_warn"] = True
        elif (time.time() - laf_time) >= limits["alert_delay"]:
            warn["LAF_warn"] = False
            
        if state["LAeq1m"] >= limits["LAeq1_limit"]:
            la1_time = time.time()
            warn["LA1_warn"] = True
        elif (time.time() - la1_time) >= limits["alert_delay"]:
            warn["LA1_warn"] = False
            
        if state["LAeq10m"] >= limits["LAeq10_limit"]:
            la10_time = time.time()
            warn["LA10_warn"] = True
        elif (time.time() - la10_time) >= limits["alert_delay"]:
            warn["LA10_warn"] = False
            
        if  limits["LAF_limit"] > state["LAF"] > limits["LAF_limit"]-limits["LAFwarn"]:
            lafwarn_time = time.time()
            warn["LAFwarn"] = True
        elif (time.time() - lafwarn_time )>= limits["alert_delay"]:
            warn["LAFwarn"] = False
            
        if  limits["LAeq1_limit"] > state["LAeq1m"] > limits["LAeq1_limit"]-limits["L1warn"]:
            l1warn_time = time.time()
            warn["L1warn"] = True
        elif (time.time() - l1warn_time) >= limits["alert_delay"]:
            warn["L1warn"] = False
            
        if  limits["LAeq10_limit"] > state["LAeq10m"] > limits["LAeq10_limit"]-limits["L10warn"]:
            l10warn_time = time.time()
            warn["L10warn"] = True
        elif (time.time() - l10warn_time) >= limits["alert_delay"]:
            warn["L10warn"] = False   
        
        # 2. Transfer function (if active)
        current_transfer_payload = None
        if measurement_mode == "transfer":
            # Optionally, increase the counter from 4 to 8 to reduce the update rate to ~5 Hz
            if local_push_counter == 4:  
                
                # A single combined run that detects delays AND calculates TF/IR
                tf_data = compute_transfer_function_and_ir_optimized(
                    mic_signal=x_mic, 
                    ref_signal=x_ref, 
                    delay_mode=current_delay_mode,
                    manual_offset_samples=manual_delay_offset
                )
                
                transfer_state.update(tf_data)
        
            current_transfer_payload = transfer_state.copy()

        # 3. Websocket Push-counter
        local_push_counter += 1
        if local_push_counter >= 5:
            local_push_counter = 0
            
            now = time.time()
            if now - last_prediction_time >= 1.0:
                last_prediction_time = now
                update_predictions(leq10, leq1)
            
            smooth_spec, peak_spec = compute_spectrum()

            payload = {
                "state": state,
                "limits": limits,
                "spectrum": {
                    "freqs": centers,
                    "levels": smooth_spec,
                    "peak": peak_spec
                },
                "warn": warn,
                "transfer": current_transfer_payload,
                "measurement_mode": measurement_mode
            }
            
            if audio_queue.full():
                try:
                    audio_queue.get_nowait()
                except:
                    pass
            try:
                audio_queue.put_nowait(payload)
            except:
                pass


# =========================
# FFT / SPECTRUM CALCULATOR (Now calculated directly per chunk)
# =========================
def compute_spectrum():
    global spectrum_smooth, spectrum_peak
    if len(fft_buf) < fft_buf.maxlen:
        return [0.0]*len(centers), [0.0]*len(centers)

    buf = np.array(fft_buf, dtype=float)
    N = len(buf)
    window = np.hanning(N)
    buf_win = buf * window

    spec = np.fft.rfft(buf_win)
    freqs = np.fft.rfftfreq(N, 1/fs)

    spec_peak_val = np.abs(spec) * 2.0 / N
    spec_rms = spec_peak_val / np.sqrt(2)
    spec_rms *= 2.0 # Hann correction

    mag_db = 20 * np.log10(spec_rms / (REF + 1e-20) + 1e-20)
    raw_levels = []

    for c in centers:
        bw = c * 0.231
        low, high = c - bw / 2, c + bw / 2
        idx = np.where((freqs >= low) & (freqs <= high))[0]
        if len(idx) > 0:
            band_energy = np.mean(10 ** (mag_db[idx] / 10))
            raw_levels.append(10 * np.log10(band_energy + 1e-20))
        else:
            raw_levels.append(-120.0)

    decay, alpha = (0.05, 0.2) if peak_mode == "slow" else (0.20, 0.35)

    if spectrum_smooth is None: spectrum_smooth = raw_levels.copy()
    else: spectrum_smooth = [alpha * r + (1 - alpha) * s for r, s in zip(raw_levels, spectrum_smooth)]

    if spectrum_peak is None: spectrum_peak = raw_levels.copy()
    else: spectrum_peak = [max(r, p - decay) for r, p in zip(raw_levels, spectrum_peak)]

    return spectrum_smooth, spectrum_peak

# =========================
# TREND, RATE & PREDICTION
# =========================
def update_predictions(current_laeq10, current_laeq1m):
    global sum_10m
    
    # ==========================================
    # 1. CALCULATE TREND & RATE (dB/min)
    # ==========================================
    trend_buf.append(current_laeq10)
    if len(trend_buf) >= 10:
        delta_db = trend_buf[-1] - trend_buf[0]
        duration_mins = len(trend_buf) / 60.0
        rate = delta_db / duration_mins # dB pr. minut
        
        state["LAeq10_rate"] = round(rate, 2)
        if rate > 0.5:
            state["LAeq10_trend"] = "+"
        elif rate < -0.5:
            state["LAeq10_trend"] = "-"
        else:
            state["LAeq10_trend"] = "0"

    # ==========================================
    # 2. CALCULATE ETA
    # ==========================================
    limit_db = limits["LAeq10_limit"]
    
    if current_laeq10 >= limit_db:
        state["LAeq10_eta"] = 0
    elif current_laeq1m <= limit_db:
        state["LAeq10_eta"] = -1
    else:
        p_sustained_norm = 10**(current_laeq1m / 10)
        current_sum_norm = sum_10m / (REF**2)
        #limit_sum_norm = (10**(limit_db / 10)) * buf_10m.maxlen * chunk
        limit_sum_norm = (10**(limit_db / 10)) * len(buf_10m) * chunk
        energy_needed = limit_sum_norm - current_sum_norm
        energy_gain_per_sample = (p_sustained_norm - (10**(current_laeq10 / 10)))
        
        if energy_gain_per_sample > 0:
            samples_to_limit = energy_needed / energy_gain_per_sample
            eta_seconds = samples_to_limit / fs
            state["LAeq10_eta"] = int(min(max(0, eta_seconds), 600))
        else:
            state["LAeq10_eta"] = -1

    # ==========================================
    # 3. STATISTICAL LEVELS (L10 and L90)
    # ==========================================
    if len(buf_10m) > 100:
        energies = np.array(buf_10m)
        db_samples = 10 * np.log10((energies / chunk) / (REF**2) + 1e-12)
        
        state["L90"] = float(round(np.percentile(db_samples, 10), 1))
        state["L10"] = float(round(np.percentile(db_samples, 90), 1))

push_counter = 0
last_prediction_time = 0.0


# =========================
# AUDIO THREAD VIA CALLBACK (Ultra-Lightweight)
# =========================
def audio_loop():
    global threadstop, play_ptr, measurement_mode, snd_index 

    target_device = snd_index
    print("index=",target_device)
    try:
        devices = sd.query_devices()
        print("dev",devices)
        for idx, dev in enumerate(devices):
            if (idx == target_device):
                print(f"   FFound sound carn on index: {idx} ({dev['name']})", flush=True)
                break
    except Exception as e:
        print(f"Fejl ved søgning efter enhed: {e}", flush=True)

    def callback(indata, outdata, frames, time_info, status):
        global play_ptr, measurement_mode

        # 1. Playback (Pink Noise or Silence)
        if (measurement_mode == "transfer" or measurement_mode == "spl_pink"):

            end_idx = play_ptr + frames
            chunk_to_play = pink_noise_buffer[play_ptr:end_idx]
            
            if len(chunk_to_play) < frames:
                remainder = frames - len(chunk_to_play)
                chunk_to_play = np.concatenate([chunk_to_play, pink_noise_buffer[0:remainder]])
                play_ptr = remainder
            else:
                play_ptr += frames
                
            outdata[:, 0] = chunk_to_play  # L (Speaker/mixer)
            outdata[:, 1] = chunk_to_play  # R (Physical Loopback)
        else:
            outdata.fill(0)
            play_ptr = 0
            

        # 2. Hand off raw chunks to our worker thread at speed
        # We make copies of the raw arrays to avoid memory overwrites
        try:
            raw_audio_queue.put_nowait((indata[:, 0].copy(), indata[:, 1].copy()))
        except queue.Full:
            pass  # If the queue is full, contrary to expectations, we drop a frame to protect ALSA.

    stream_device = target_device if target_device is not None else None
    
    with sd.Stream(device=stream_device, 
                   channels=(2, 2), 
                   samplerate=fs, 
                   blocksize=chunk, 
                   latency='high', 
                   callback=callback):
        while not threadstop:
            gevent.sleep(0.1)

# ==========================================
# Runs in Socket.IO's background thread
# ==========================================
def bg_emit_loop():
    print("Background thread for WebSockets started...")
    try:
        while True:
            # Get from queueueueue
            payload = audio_queue.get()
            
            # SAVE TO WATERFALL HISTORY
            # double-checking that 'spectrum' and 'levels' are included in the package
            if 'spectrum' in payload and 'levels' in payload['spectrum']:
                WATERFALL_HISTORY.append(payload['spectrum']['levels'])
            

            # TRANSFER DATA MONITORING (For debugging/logging in the terminal) - we should probably comente this if out
            # If we are in transfer mode, we can monitor the delay directly in the backend
            if payload.get("transfer"):
                t_data = payload["transfer"]
                # Just for verification
                # print(f"[Transfer] Delay: {t_data['delay_ms']} ms ({t_data['delay_samples']} samples)", flush=True)
                pass
            
            # Socket send over network
            socketio.emit('audio_update', payload)
            
    except Exception as e:
        # If a CRITICAL, unexpected error occurs in the network layer
        print(f"\\nCRITICAL: bg_emit_loop died unexpectedly! Error: {e}", flush=True)
        print("Force application to shut down for a restart....", flush=True)
        shutdown_clean(0) # 'Crash & Restart' exit-kode

def watch_log_file():
    # background task runs autonomously and streams ONLY live data
    global log_watcher_active
    print("[LOG WATCHER] Live-thread started...")
    
    try:
        with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="ignore") as f:
            # Go directly to the bottom of the file, as the history is handled individually
            f.seek(0, 2)
            
            while log_watcher_active:
                line = f.readline()
                if not line:
                    socketio.sleep(0.5)
                    continue
                
                socketio.emit('new_log_line', {'data': line.strip()}, room='log_viewers')
                
    except Exception as e:
        socketio.emit('new_log_line', {'data': f'[Error in live-watcher: {str(e)}]'}, room='log_viewers')
    
    print("[LOG WATCHER] Live-thread thread stopped...")
    
def list_devices():
    aktive_enheder = []
    cards_file = "/proc/asound/cards"

    if not os.path.exists(cards_file):
        return jsonify({"error": "ALSA cards file not found"}), 500

    # Read the actual, physical devices directly from the Linux kernel
    with open(cards_file, "r") as f:
        lines = f.readlines()
        
    # /proc/asound/cards typically has 2 lines per sound card. Eg.
    # Line 1: " 0 [PCH            ]: HDA Intel PCH - HDA Intel PCH"
    # Line 2: "                  Subdevices: 1/1"
    for i in range(len(lines)):
        line = lines[i].strip()
        parts = line.split()
        
        # if line starts with a number, it is a sound card - I hope...
        if parts and parts[0].isdigit():
            try:
                kort_nummer = parts[0]
                # Find ID in [ ]
                card_id = line.split('[')[1].split(']')[0].strip()
                # Find the full description after the :
                card_desc = line.split(':', 1)[1].strip()
                
                # Lets build a name that kind of looks like the one ALSA/PortAudio uses
                # to match it after restart. look for "hw:X" or the ID
                if "usb" in card_id.lower() or "usb" in card_desc.lower():
                    aktive_enheder.append({
                        "alsa_index": int(kort_nummer),
                        "id": card_id,
                        "name": card_desc,
                        "device_string": f"hw:{kort_nummer},0" # Standard ALSA device string
                    })
            except IndexError:
                continue

    return aktive_enheder

def find_sd_index(name, detected_dev):
    hw_string = None
    for dev in detected_dev:
        if dev['name'] == name:
            hw_string = dev['device_string'] # ie. "hw:3,0"
            break
        
    if not hw_string:
        print(f"   [ERROR] Saved sound card '{name}' was not found on system!")
        return None
    
    for sd_dev in sd.query_devices():
        if hw_string in sd_dev['name']:
            print(f"   [Succes] Matchede '{name}' ({hw_string}) to sounddevice index: {sd_dev['index']}")
            return sd_dev['index']

    return None
# =============================================
# SOCKETS & ROUTES
# =============================================
      
@socketio.on('connect') # Send history on refresh / new connection
def handle_connect():
    # Flask-SocketIO gives specifik client ID via 'request.sid'
    print(f"New device connected : {request.sid}")
    # If we have history, send it to only this one device that just conencted/refreshed
    if len(WATERFALL_HISTORY) > 0:
        socketio.emit('waterfall_history_dump', list(WATERFALL_HISTORY), to=request.sid)
    socketio.emit('gui_trigger', { 
            'event': 'peak_mode',
            'value': peak_mode
        } )
    socketio.emit('gui_trigger', { 
            'event': 'yaxis_mode',
            'value': yaxis_mode
        } )
        
@socketio.on('join_log_stream')
def handle_join():
    global log_watcher_active, log_viewer_count
    
    join_room('log_viewers')
    log_viewer_count += 1
    print(f"[LOG] Client connected. Active viewers: {log_viewer_count}")
    
    # 1. Retrieve history only for this specific client
    try:
        with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="ignore") as f:
            sidste_linjer = deque(f, maxlen=1000)
            
            # send history ONLY to this specific client's session (use request.sid)
            for line in sidste_linjer:
                tekst_linje = line.strip()
                if tekst_linje:
                    socketio.emit('new_log_line', {'data': tekst_linje}, to=request.sid)
    except Exception as e:
        socketio.emit('new_log_line', {'data': f'[Error retrieving history: {str(e)}]'}, to=request.sid)
    
    # 2. Start or keep the live stream running globally
    if not log_watcher_active:
        log_watcher_active = True
        socketio.start_background_task(watch_log_file)

@socketio.on('leave_log_stream')
def handle_leave():
    global log_watcher_active, log_viewer_count
    
    leave_room('log_viewers')
    if log_viewer_count > 0:
        log_viewer_count -= 1
    print(f"[LOG] A client left the room by choice. Active viewers: {log_viewer_count}")
    
    # No more viewers, no more looping
    if log_viewer_count == 0:
        log_watcher_active = False

@socketio.on('disconnect')
def handle_disconnect():
    global log_watcher_active, log_viewer_count
    
    # flask-socketio automatically removes the user from all rooms upon disconnection,
    # but we need to check whether the user was one of the log viewers.
    # We cannot easily determine exactly WHICH room they left during the disconnect event,
    # but we can perform a simple check (or simply have the frontend call 'leave_log_stream' before closing or changing pages).
    # Safeguard: If a client disconnects completely (e.g., closes the browser),
    # we decrement the counter if it was above 0.
    if log_viewer_count > 0:
        log_viewer_count -= 1
        print(f"[LOG] A client lost the connection. Active viewers: {log_viewer_count}")
        
        if log_viewer_count == 0:
            log_watcher_active     

@socketio.on('save_device') # Save device trigger return from GUI
def handle_gui_trigger(json_data):
    print("To be saved:",json_data, flush=True)
    print(save_device("../default_snd.conf", json_data), flush=True)
    

@socketio.on('gui_trigger') # GUI trigger return from GUI
def handle_gui_trigger(json_data):
    action = json_data.get('action')
    global measurement_mode, sound_dev, current_delay_mode, manual_delay_offset, locked_delay, last_found_delay
    
    if action == 'reset_max':
        state["MAX_LAF"] = -999
        print(f"[RESET] MAX LAF was reset by client: {request.sid}")
        
    if action == 'reset_1':
        state["MAX_1M"] = -999
        print(f"[RESET] LAeq1 was reset by client: {request.sid}")
    
    if action == 'reset_10':
        state["MAX_10M"] = -999
        print(f"[RESET] LAeq10 was reset by client: {request.sid}", flush=True)
        
    if action == 'toggle_peakmode':
        global peak_mode
        peak_mode = "fast" if peak_mode == "slow" else "slow"
        socketio.emit('gui_trigger', { 
            'event': 'peak_mode',
            'value': peak_mode
        } )
        print(f"[toggle_peakmode] by client: {request.sid} mode={peak_mode}", flush=True)
        
    if action == 'toggle_yaxis_mode':
        global yaxis_mode
        yaxis_mode = "narrow" if yaxis_mode == "wide" else "wide"
        socketio.emit('gui_trigger', { 
            'event': 'yaxis_mode',
            'value': yaxis_mode
        } )
        print(f"[toggle_yaxis_mode] by client: {request.sid} mode={yaxis_mode}")

    if action == 'reset_peaks':
        global spectrum_peak
        spectrum_peak = None
        print(f"[reset_peaks] by client: {request.sid}", flush=True)
        
    if action == 'save_limits':
        limits.update ({
            "LAF_limit": float(json_data.get('laf_lim')),
            "LAeq1_limit": float(json_data.get('la1_lim')),
            "LAeq10_limit": float(json_data.get('la10_lim')),
            "LAFwarn": float(json_data.get('LAFwarn')),
            "L1warn": float(json_data.get('L1warn')),
            "L10warn": float(json_data.get('L10warn')),
            "alert_delay": int(json_data.get('delay_in'))
        })
        save_limits("../limits.txt")
        
    if action == 'getREF':
        socketio.emit('gui_trigger', {'REF': REF} )
    
    if action == 'resound':
        result = resound()
        print(result, flush=True)
        socketio.emit('resound', { 
            'value': result
        } )
    
    if action == 'restart_app':
        print("GUI-trigger: Restart app", flush=True)
        threading.Timer(4, lambda: shutdown_clean()).start()
        
    if action == 'reboot_sys':
        print("GUI-trigger: Reboot system", flush=True)
        threading.Timer(4, lambda: kill_clean("reboot")).start()
        
    if action == 'shutdown_sys':
        print("GUI-trigger: Shutdown system", flush=True)
        threading.Timer(4, lambda: kill_clean("shutdown")).start()
 
    if action == 'waterfall_history_dump':
        if len(WATERFALL_HISTORY) > 0:
            socketio.emit('waterfall_history_dump', list(WATERFALL_HISTORY), to=request.sid)
    
    if action == 'mode_transfer': 
        measurement_mode = "transfer"
        socketio.emit('gui_trigger', {
            'event': 'pink',
            'value': True
        } )
        print("measurement_mode = transfer", flush=True)
        
    if action == 'mode_spl':
        measurement_mode = "spl"
        socketio.emit('gui_trigger', {
            'event': 'pink',
            'value': False
        } )
        print("measurement_mode = spl", flush=True)
        
    if action == 'mode_pink':
        measurement_mode = "spl_pink"
        socketio.emit('gui_trigger', {
            'event': 'pink',
            'value': True
        } )
        print("measurement_mode = spl_pink" , flush=True)
        
    if action == 'devices':
        print("Device list requested", flush=True)
        devs = list_devices()
        socketio.emit('devices',devs)
        
    if action == 'cfg_dev':
        print("Dev config requested :",sound_dev, flush=True)
        socketio.emit('devices',sound_dev)
            
    if action == 'set_delay_mode':
        mode = json_data.get('mode', 'auto')
        current_delay_mode = mode
        
        if mode == 'auto':
            manual_delay_offset = 0
            print(f"[DELAY] Switched to Auto Track mode by {request.sid}", flush=True)
            
        elif mode == 'lock':
            # Store the precise delay from the latest auto-measurement
            locked_delay_samples = last_found_delay
            manual_delay_offset = 0
            print(f"[DELAY] Locked to current delay ({locked_delay_samples} spls) by {request.sid}", flush=True)
            
        elif mode == 'manual':
            # If we came directly from auto, we only lock on the latest auto measurement
            if current_delay_mode == 'auto':
                locked_delay_samples = last_found_delay
                
            # Add only the new offset to the total offset sum
            offset = json_data.get('offset_samples', 0)
            manual_delay_offset += offset
            print(f"[DELAY] Manual offset adjusted by {offset} spls. Total offset: {manual_delay_offset}", flush=True)
    
    if action == 'get1':
        data = loadCurve("../curve.json")
        print("result:",data[0], flush=True)
        print("Error code:",data[1], flush=True)
        socketio.emit('curvedata',{'value': data})
    
    if action == 'save1':
        print(json_data.get('curvedata'), flush=True)
    
    if action == "getcurve":
        print("Loading preset :", json_data.get('filename'), flush=True)
        data = loadCurve("./preset_curves/"+json_data.get('filename'))
        print("result:",data[0], flush=True)
        print("Error code:",data[1], flush=True)
        socketio.emit('curvedata',{'value': data})
    
    if action == 'listcurves':
        preset_dir = './preset_curves'
        curvelist = sorted(os.listdir(preset_dir))
        pattern = '_curve.json'.lower()
        
        filtered = []
        for f in curvelist:
            if f.lower().endswith(pattern):
                file_path = os.path.join(preset_dir, f)
                try:
                    with open(file_path, 'r', encoding='utf-8') as file:
                        data = json.load(file)
                        # Get head & info from file
                        header_info = data[0] if data else {}
                        
                        filtered.append({
                            'filename': f,
                            'head': header_info.get('head', ''),
                            'info': header_info.get('info', '')
                        })
                except (json.JSONDecodeError, IOError):
                    continue

        socketio.emit('curvelist', {'value': filtered})
        
# =========================
# API: SET REF (calibration)
# =========================
@app.route("/set_ref", methods=["POST"])
def set_ref():
    global REF
    data = request.json
    if "value" in data:
        REF = float(data["value"])
        state["REF"] = REF
        return {"status": "ok", "REF": REF}
    return {"status": "error"}
 
# =========================
# Config load error
# =========================
@app.route("/cfgerr")
def cfgerr():
    global REF
    mic_data, cfg_load_error = load_config("../default_mic.txt")
    limits, limits_load_err = load_limits("../limits.txt")
    result = { "cfgstatus": cfg_load_error, "limitstatus": limits_load_err}
    REF = mic_data["REF"]
    socketio.emit('gui_trigger', {'REF': REF} )
    print("load  >Limits :", limits)
    print("load  >mic_data:", mic_data)
    return jsonify(result)

# =========================
# Config save
# =========================
@app.route("/savecfg")
def savecfg():
    success, msg = save_config("../default_mic.txt")
    return jsonify({ "success": success, "message":msg })

# =========================
# DASHBOARD
# =========================
@app.route("/")
def index():
    global REF
    print("Loader config ::")
    mic_data, cfg_load_error = load_config("../default_mic.txt")
    limits, limits_load_err = load_limits("../limits.txt")
    REF = mic_data["REF"]
    print("  >Load mic-file error :",cfg_load_error)
    print("  >Load limits-file error :",limits_load_err)
    print("  >REF:",REF)
    return send_from_directory('./html/',"index.html")
    

# =========================
# ABOUT 
# =========================
@app.route("/about")
def about():
    return send_from_directory('./html/',"about.html")
    
@app.route("/calibrate/start", methods=["POST"])
def calibrate_start():
    global cal_session

    data = request.json

    cal_session["running"] = True
    cal_session["target_db"] = float(data["db"])
    cal_session["samples"] = []
    cal_session["final_rms"] = None

    return {"status": "started"}
    
@app.route("/calibrate/stop", methods=["POST"])
def calibrate_stop():
    global cal_session

    cal_session["running"] = False

    if len(cal_session["samples"]) < 10:
        return {"status": "error", "msg": "not enough samples"}

    samples = np.array(cal_session["samples"])

    # robust filtering
    samples = samples[
        (samples > np.percentile(samples, 10)) &
        (samples < np.percentile(samples, 90))
    ]

    rms = np.median(samples)

    cal_session["final_rms"] = float(rms)

    return {
        "status": "ok",
        "rms": float(rms),
        "db": cal_session["target_db"]
    }


@app.route("/calibrate/apply", methods=["POST"])
def calibrate_apply():
    global REF, cal_session

    if cal_session["final_rms"] is None:
        return {"status": "error", "msg": "no calibration done"}

    if cal_session["target_db"] is None:
        return {"status": "error", "msg": "missing target db"}

    rms = cal_session["final_rms"]
    db = cal_session["target_db"]

    REF = rms / (10 ** (db / 20))
    mic_data["REF"] = REF
    print(mic_data)
    

    return {
        "status": "ok",
        "REF": REF
    }

# @app.route("/limits", methods=["POST"])
# def limits_apply():
    # data = request.json
    # limits.update(data)
    # save_limits("limits.txt")
    # return {
        # "status": "ok",
        # "data": data
    # }

@app.route("/health")
def health():
    print("health")
    return {"status": "ok"}    
   
@app.route("/exit")
def cleanexit():
    print("GUI-trigger: Secret exit")
    threading.Timer(4, lambda: kill_clean("exit")).start()
    return {"status": "exit wrapper"}
    
@app.route("/vers")
def vers():
    return {"vers": versid}

@app.route("/device")
def device():  
    # global snd_index
    # try:
        # devices = sd.query_devices()
        # for idx, dev in enumerate(devices):
            # if (idx == snd_index):
                # print(f"   Fandt lydkort på index: {idx} ({dev['name']})", flush=True)
                # break
    # except Exception as e:
        # print(f"Fejl ved søgning efter enhed: {e}", flush=True)
    return {"name":sound_dev['name']}


@app.route("/devices", methods=["GET"])
def get_devices():
    return jsonify(list_devices())

### NEW: Spectrum endpoint
# @app.route("/spectrum_data")
# def spectrum():
    # return jsonify(spectrum_state)
       
# @app.route("/reset_peaks")
# def reset_peaks():
    # global spectrum_peak
    # spectrum_peak = None
    # return "OK"

# @app.route("/toggle_peak_mode")
# def toggle_peak_mode():
    # global peak_mode
    # peak_mode = "fast" if peak_mode == "slow" else "slow"
    # return peak_mode

# @app.route("/toggle_yaxis_mode")
# def toggle_yaxis_mode():
    # global yaxis_mode
    # yaxis_mode = "narrow" if yaxis_mode == "wide" else "wide"
    # return yaxis_mode

# @app.route("/get_modes")
# def get_modes():
    # global yaxis_mode
    # global peak_mode
    # return jsonify({ "ymode": yaxis_mode, "peakmode":peak_mode })
    
# Multiple URL Converter
@app.route('/log/<msg>')
def log_value(msg):
    print ("Log mesage from browser :", msg)
    return "OK"
    
@app.route('/<path:path>') #Everything else just goes by filename
def sendstuff(path):
	print(path)
	return send_from_directory('./html/', path)

# =========================
# START (Runs globally once when Gunicorn imports the module)
# =========================
spc = "                                                                         "
print(".-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-.", flush=True)
print("|    _    _           _     __  __             _                      |", flush=True)
print("!   | |  | |         | |   |  \\/  |           | |                     |", flush=True)
print(":   | |__| |_   _ ___| |__ | \\  / | ___  _ __ | | _____ _   _         |", flush=True)
print(":   |  __  | | | / __| '_ \\| |\\/| |/ _ \\| '_ \\| |/ / _ \\ | | |        |", flush=True)
print(".   | |  | | |_| \\__ \\ | | | |  | | (_) | | | |   <  __/ |_| |        |", flush=True)
print(".   |_|  |_|\\__,_|___/_| |_|_|  |_|\\___/|_| |_|_|\\_\\___|\\__, |        |", flush=True)
print(":   LAF monitor and acoustic test & measurement          __/ |        |", flush=True)
print("¡                                                       |___/         |", flush=True)
print("|  ___  ____ _ ____ _  _     ____ _  _ ___  ____ ____ ____ ____ _  _  |", flush=True)
print("|  |__] |__/ | |__| |\\ |     |__| |\\ | |  \\ |___ |__/ [__  |___ |\\ |  |", flush=True)
print("|  |__] |  \\ | |  | | \\|     |  | | \\| |__/ |___ |  \\ ___] |___ | \\|  |", flush=True)
print("|  Copyright 2026 - GNU General Public License v3.0 (GPLv3)           |", flush=True)
print("|                                                                     |", flush=True)
#print("|  Version:", versid, spc[:22-len(versid)],"|", flush=True)
print("|  Version:", versid, spc[:57-len(versid)-1],"|", flush=True)
print("`-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-'", flush=True)
print("", flush=True)
print("Loading config-files...", flush=True)

mic_data, cfg_load_error = load_config("../default_mic.txt")
limits, limits_load_err = load_limits("../limits.txt")
sound_dev, device_load_err = load_device("../default_snd.conf")
snd_index = find_sd_index(sound_dev["name"], list_devices())
# Ensure that the global REF variable is actually updated with the loaded value!
REF = mic_data["REF"]

print("   Load config-file error :", cfg_load_error, flush=True)
print("   Load limits-file error :", limits_load_err, flush=True)
print("   State :", state, flush=True)
print("   Limits :", limits, flush=True)
print("   mic_data:", mic_data, flush=True)
print("", flush=True)
print("--------------------------------------------------------------", flush=True)
print("Detected sound devices : ", list_devices(), flush=True)
print("", flush=True)
print("Loading default sound device from config-file:", flush=True)
print("   Device :", sound_dev, flush=True)
print("   ",sound_dev["name"], flush=True)
print("--------------------------------------------------------------", flush=True)
print("", flush=True)
print("Matching soundcards config to hardware:")
print("   index:", snd_index, flush=True)
print("--------------------------------------------------------------", flush=True)
# Start background threads globally
print("", flush=True)
print("Starting background threads via Gunicorn worker...", flush=True)

print("  Audio-loop", flush=True)
# 1. Start the real OS audio thread
t = threading.Thread(target=audio_loop, daemon=True)
t.start()

print("  DSP worker starting", flush=True)
# 1b. Start DSP worker-thread that chews through raw data
t_dsp = threading.Thread(target=processing_worker, daemon=True)
t_dsp.start()

print("  bg_emit_loop starting", flush=True)
# 2. Start the Socket.IO background thread via gevent
socketio.start_background_task(bg_emit_loop)

print("  Term binds set", flush=True)
# 3. Bind terminate signals to the Gunicorn worker 
signal.signal(signal.SIGINT,  lambda s, f: shutdown_clean(0))
signal.signal(signal.SIGTERM, lambda s, f: shutdown_clean(0))

print("", flush=True)
print("System initialized and running.", flush=True)
print("", flush=True)                    
print(" |   _ _|_ / _    _   _  | ", flush=True)
print(" |_ (/_ |_  _>   (_| (_) o ", flush=True)
print("                  _|       ", flush=True)
print("", flush=True)



