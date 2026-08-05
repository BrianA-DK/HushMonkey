from flask import Flask, jsonify, request
from flask import send_from_directory
#from flask import render_template
import numpy as np
import sounddevice as sd
from scipy.signal import bilinear, lfilter
import threading
import time
from collections import deque
import json
import os
import datetime
#import sys
import signal

app = Flask(__name__)

threadstop = False;


# =========================
# CLEAN SHUTDOWN
# =========================
def shutdown_clean(exit_code=0):
    global threadstop
    print("Shutting down audio thread...")
    threadstop = True
    t.join(timeout=3)  # wait up to 3 seconds for thread to finish
    print("Audio thread stopped. Exiting.")
    os._exit(exit_code)  # force-exit Flask + all threads

# Register Ctrl+C / kill signal
signal.signal(signal.SIGINT,  lambda s, f: shutdown_clean(0))
signal.signal(signal.SIGTERM, lambda s, f: shutdown_clean(0))


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
# CONFIG
# =========================
m_time = os.path.getmtime(os.getcwd() + "/current/main.py")
dt = datetime.datetime.fromtimestamp(m_time)
print('Modified on:', dt)
versid = "0.2b - Chill Chimpanzee (" + dt.strftime("%Y-%m-%d %H:%M:%S") + ")"

fs = 48000
chunk = 1024

REF = 0.01  # Dummy calibration (changed via web)
LAF_limit = 1.01
LAeq1_limit = 2.02
LAeq10_limit = 3.03
b, a = a_weighting(fs)

# =========================
# CONFIG — replace deques with running-sum accumulators
# =========================
buf_1m  = deque(maxlen=fs * 60)    # keep for now, repurposed below
buf_10m = deque(maxlen=fs * 600)

sum_1m  = 0.0 # Running sums — O(1) update instead of O(N) mean each callback
sum_10m = 0.0 # -"-

cfg_load_error = 99
limits_load_err = 99

fft_buf = deque(maxlen=16384)   # ca. 85 ms ved 48 kHz
spectrum_state = {
    "freqs": [],
    "levels": [],
    "peak": []
}
# Spectrum smoothing + peak hold
spectrum_smooth = None
spectrum_peak = None
peak_mode = "slow"   # slow / fast
yaxis_mode = "wide"   # wide / narrow



# =========================
# Setup dict
# =========================
state = {
    "LAF": 0.0,
    "LAeq1m": 0.0,
    "LAeq10m": 0.0,
    "MAX_LAF": -999.0,
    "MAX_1M": -999.0,
    "MAX_10M": -999.0
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
    "alert_delay": 5
}

cal_session = {
    "running": False,
    "target_db": None,
    "samples": [],
    "final_rms": None
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
        print(limits)

def load_limits(filnavn):
    try:
        with open(filnavn, "r") as f:
            return json.load(f), 0
        
    except (FileNotFoundError, json.JSONDecodeError):
            return {
                "LAF_limit": 1.0,
                "LAeq1_limit": 2.0,
                "LAeq10_limit": 3.0,
                "alert_delay": 5
            }, 1
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
# AUDIO THREAD — optimized callback
# =========================
def audio_loop():
    global REF, threadstop, sum_1m, sum_10m

    def callback(indata, frames, time_info, status):
        global sum_1m, sum_10m

        x = indata[:, 0]
        laf, energy, rms = process(x)
        ### NEW: Fill FFT buffer
        fft_buf.extend(x)

        if cal_session["running"]:
            cal_session["samples"].append(rms)

        # --- Running sum trick: subtract evicted values, add new ones ---
        chunk_sum = float(np.sum(energy))   # sum of this chunk (small array)
        chunk_len = len(energy)

        # 1-minute buffer
        if len(buf_1m) == buf_1m.maxlen:
            sum_1m -= buf_1m[0]  # We stored per-chunk sums, so eviction is O(1)
        buf_1m.append(chunk_sum) # store SUM per chunk, not raw samples
        sum_1m += chunk_sum

        # 10-minute buffer
        if len(buf_10m) == buf_10m.maxlen:
            sum_10m -= buf_10m[0]
        buf_10m.append(chunk_sum)
        sum_10m += chunk_sum

        # Total sample counts for correct mean
        n_1m  = min(len(buf_1m),  buf_1m.maxlen)  * chunk_len
        n_10m = min(len(buf_10m), buf_10m.maxlen) * chunk_len

        mean_1m  = sum_1m  / n_1m
        mean_10m = sum_10m / n_10m

        leq1  = 10 * np.log10(mean_1m  / (REF**2))
        leq10 = 10 * np.log10(mean_10m / (REF**2))

        state["LAF"]     = float(laf)
        state["LAeq1m"]  = float(leq1)
        state["LAeq10m"] = float(leq10)

        state["MAX_LAF"] = max(state["MAX_LAF"], laf)
        state["MAX_1M"]  = max(state["MAX_1M"],  leq1)
        state["MAX_10M"] = max(state["MAX_10M"], leq10)
    
    ### NEW: FFT processing function (corrected + calibrated)
    def compute_spectrum():
        global spectrum_state, fft_buf, REF
        global spectrum_smooth, spectrum_peak

        if len(fft_buf) < fft_buf.maxlen:
            return

        buf = np.array(fft_buf, dtype=float)
        N = len(buf)

        # Hann window
        window = np.hanning(N)
        buf_win = buf * window

        # FFT
        spec = np.fft.rfft(buf_win)
        freqs = np.fft.rfftfreq(N, 1/fs)

        # FFT → RMS → dB SPL
        spec_peak = np.abs(spec) * 2.0 / N
        spec_rms = spec_peak / np.sqrt(2)

        # Hann window amplitude correction
        spec_rms *= 2.0

        # Convert to dB SPL
        mag_db = 20 * np.log10(spec_rms / (REF + 1e-20) + 1e-20)

        # IEC 1/3-octave centers
        centers = [
            20, 25, 31.5, 40, 50, 63, 80, 100,
            125, 160, 200, 250, 315, 400, 500, 630,
            800, 1000, 1250, 1600, 2000, 2500, 3150,
            4000, 5000, 6300, 8000, 10000, 12500, 16000
        ]

        raw_levels = []

        for c in centers:
            bw = c * 0.231
            low = c - bw / 2
            high = c + bw / 2

            idx = np.where((freqs >= low) & (freqs <= high))[0]

            if len(idx) > 0:
                band_energy = np.mean(10 ** (mag_db[idx] / 10))
                band_db = 10 * np.log10(band_energy + 1e-20)
                raw_levels.append(band_db)
            else:
                raw_levels.append(-120.0)

        # Peak hold settings
        if peak_mode == "slow":
            decay = 0.05      # langsom decay
            alpha = 0.2       # smoothing
        else:
            decay = 0.20      # hurtig decay
            alpha = 0.35      # hurtigere smoothing

        # --- SMOOTHING (EMA) ---
        #alpha = 0.2  # smoothing factor (0.1 = meget smooth, 0.3 = hurtigere)
        if spectrum_smooth is None:
            spectrum_smooth = raw_levels.copy()
        else:
            spectrum_smooth = [
                alpha * r + (1 - alpha) * s
                for r, s in zip(raw_levels, spectrum_smooth)
            ]

        # --- PEAK HOLD ---
        #decay = 0.05  # dB pr. opdatering (300 ms → ~0.17 dB/sek)
        if spectrum_peak is None:
            spectrum_peak = raw_levels.copy()
        else:
            new_peak = []
            for r, p in zip(raw_levels, spectrum_peak):
                if r > p:
                    new_peak.append(r)
                else:
                    new_peak.append(p - decay)
            spectrum_peak = new_peak

        # Send begge til frontend
        spectrum_state["freqs"] = centers
        spectrum_state["levels"] = spectrum_smooth
        spectrum_state["peak"] = spectrum_peak

    
    with sd.InputStream(channels=1,
                        samplerate=fs,
                        blocksize=chunk,
                        callback=callback):
        while not threadstop:
            compute_spectrum()   ### NEW
            time.sleep(0.5)   # slightly tighter exit response

# =========================
# API: RESET 
# =========================
@app.route("/resetmax", methods=["POST"])
def reset():
    state["MAX_LAF"] = -999
    return {"status": "reset ok"}

# =========================
# Also fix reset routes to clear sums
# =========================
@app.route("/reset1")
def reset1():
    global sum_1m
    buf_1m.clear()
    sum_1m = 0.0
    state["MAX_1M"] = -999
    return {"status": "reset1 ok"}

@app.route("/reset10")
def reset10():
    global sum_10m
    buf_10m.clear()
    sum_10m = 0.0
    state["MAX_10M"] = -999
    return {"status": "reset10 ok"}

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
# DATA
# =========================
@app.route("/data")
def data():
    response = jsonify(state | limits)
    response.headers["Cache-Control"] = "no-store"   # already default, but consider:
    # response.cache_control.max_age = 0             # explicit no-cache
    return response
    
# =========================
# Config load error
# =========================
@app.route("/cfgerr")
def cfgerr():
    global REF
    mic_data, cfg_load_error = load_config("default_mic.txt")
    limits, limits_load_err = load_limits("limits.txt")
    result = { "cfgstatus": cfg_load_error, "limitstatus": limits_load_err}
    print("load  >Limits :", limits)
    print("load  >mic_data:", mic_data)
    return jsonify(result)
    
    
# =========================
# Config save
# =========================
@app.route("/savecfg")
def savecfg():
    success, msg = save_config("default_mic.txt")
    return jsonify({ "success": success, "message":msg })

# =========================
# DASHBOARD
# =========================
@app.route("/")
def index():
    global REF
    print("Loader config ::")
    mic_data, cfg_load_error = load_config("default_mic.txt")
    limits, limits_load_err = load_limits("limits.txt")
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

@app.route("/limits", methods=["POST"])
def limits_apply():
    data = request.json
    limits.update(data)
    save_limits("limits.txt")
    return {
        "status": "ok",
        "data": data
    }

@app.route("/health")
def health():
    print("health")
    return {"status": "ok"}    

@app.route("/restart")
def restart():
    print("restart")
    threading.Timer(8, lambda: shutdown_clean(0)).start()
    return {"status": "restarting"}

@app.route("/reboot")
def reboot():
    threading.Timer(8, lambda: shutdown_clean(170)).start()
    return {"status": "rebooting"}

@app.route("/shutdown")
def shutdown():
    threading.Timer(8, lambda: shutdown_clean(171)).start()
    return {"status": "shuttingdown"}
    
@app.route("/exit")
def cleanexit():
    threading.Timer(8, lambda: shutdown_clean(172)).start()
    return {"status": "exit wrapper"}
    
@app.route("/vers")
def vers():
    return {"vers": versid}

@app.route("/device")
def device():
    devices = sd.query_devices()
    host_apis = sd.query_hostapis()

    result = []

    for idx, dev in enumerate(devices):
        if dev["max_input_channels"] < 1:
            continue  # output-only device

        host_api_name = host_apis[dev["hostapi"]]["name"] if dev["hostapi"] < len(host_apis) else "Unknown"

        result.append({
            "index": idx,
            "name": dev["name"],
            "channels": dev["max_input_channels"],
            "sample_rate": int(dev["default_samplerate"]),
            "host_api": host_api_name,
            "is_default": idx == sd.default.device[0],
        })

    for i in result:
        if (i["is_default"]):
            return jsonify(i)

### NEW: Spectrum endpoint
@app.route("/spectrum_data")
def spectrum():
    return jsonify(spectrum_state)
    
@app.route("/spectrum")
def spectrum_page():
    return send_from_directory('./html/', "spectrum.html")
    
@app.route("/reset_peaks")
def reset_peaks():
    global spectrum_peak
    spectrum_peak = None
    return "OK"

@app.route("/toggle_peak_mode")
def toggle_peak_mode():
    global peak_mode
    peak_mode = "fast" if peak_mode == "slow" else "slow"
    return peak_mode

@app.route("/toggle_yaxis_mode")
def toggle_yaxis_mode():
    global yaxis_mode
    yaxis_mode = "narrow" if yaxis_mode == "wide" else "wide"
    return yaxis_mode

@app.route("/get_modes")
def get_modes():
    global yaxis_mode
    global peak_mode
    return jsonify({ "ymode": yaxis_mode, "peakmode":peak_mode })

@app.route('/<path:path>') #Everything else just goes by filename
def sendstuff(path):
	print(path)
	return send_from_directory('./html/', path)

# =========================
# START
# =========================
if __name__ == "__main__":
    print("LAF monitor")
    print("(c) 2026 Brian Andersen")
    print("-----------------------------------------------")
    print("Loader config ::")
    mic_data, cfg_load_error = load_config("default_mic.txt")
    limits, limits_load_err = load_limits("limits.txt")
    print("  >Load config-file error :",cfg_load_error)
    print("  >Load limits-file error :",limits_load_err)
    print("  >State :",state)
    print("  >Limits :", limits)
    print("  >mic_data:", mic_data)
    print("-----------------------------------------------")
    t = threading.Thread(target=audio_loop, daemon=True)
    t.start()
    
    app.run(host="0.0.0.0", port=80, threaded=True)
    
    
