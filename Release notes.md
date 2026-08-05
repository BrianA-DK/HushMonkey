# Release Notes & Changelog

Welcome to the changelog. Below is an overview of all releases and updates organized by version family.

---

## 🦍 0.3 Series (Grumpy Gorilla)

### Version 0.3a
*Say hello to the Grumpy Gorilla! A brand new release series packed with new features and improvements.*

#### Frontend & Design
* **Single Page Application (SPA):** Completely restructured frontend and GUI redesign.
* **Dark / Light Theme:** Main page supports Dark/Light theme for displaying alerts in two distinct ways. Stores user preference on the device and automatically follows the operating system's dark mode settings.

#### Performance & Communication
* **WebSockets:** Moved GUI<->backend communication to sockets for streaming large data volumes efficiently.
* **Error Logging:** Web-call added to pass information from the frontend directly to the backend log file when needed.
* **Gunicorn Exit Handler:** New exit method to quit Gunicorn and pass a `returncode` to `wrapper.sh`.
* *CPU Usage:* Remains around 60% on a Raspberry Pi 3 with delay analysis running.

#### Advanced Audio & Measurement Analyses
* **Waterfall Analysis:** Added directly to the main page.
* **Statistical Sound Levels:** Added `L10` and `L90` calculations.
* **LAF Trend:** Indicates whether the sound level is increasing or decreasing over the last 10 minutes and at what rate.
* **Time to Limit Prediction:** Calculates how long the current sound level can be maintained before breaching the `LAeq10` limit.
* **Delay & Phase Analysis:** Added delay and phase measurement capabilities, along with a built-in **Pink Noise Generator**.

---

## 🙉 0.2 Series (Chill Chimpanzee – Lightweight)

> **Note:** The 0.2 family is no longer under active feature development. Consider this the lightweight alternative to the 0.3 series. Functions absolutely brilliantly.

### Version 0.2b
*The final release in the Chill Chimpanzee series.*

* **Graph Fix:** Fixed rare occasions where the spectrum graph would resize down to about 25%.
* **Synchronization:** Analyzer settings are now synced from the server and across multiple devices if more are connected (CSS and JS).
* **Naming Consistency:** Updated naming of sub-pages for consistency.
* **Cleanup:** Removed startup script for Windows (was only used during initial development on Windows; moved development entirely to RaspPi3).

### Version 0.2a
* **Memory Optimization:** Reduced buffer sizes (`buf_1m` & `buf_10m`) to reduce the memory footprint.
* **Spectrum Analyzer:** Draft implementation of a 1/3 octave spectrum analyzer featuring peaks, Y-axis zoom, and slow/fast decay.

---

## Legacy Versions (0.1 Series)

<details>
<summary><b>Click here to expand the 0.1.x archive</b></summary>

### Version 0.1d
* **Boot-loop Prevention:** Changed exit RC in `main.py` to avoid a boot-loop if the wrapper cannot launch `main.py` (ask me how I know...).
* **Wrapper & Installer:** Updated `wrapper.sh` to reflect new RC values. Updated `install.sh` to handle `apt` dependencies, sudo permissions, and log rotation on `/var/log/hushmonkey.log`.

### Version 0.1c
* **System & Web:** Comment cleanup in `main.py`. Version info is now passed to `about.html` via HTTP request. Removed version number from the title in `index.html`.
* **Optimization:** Changed logo to `.webp` format for a smaller file size while maintaining quality. Adjusted timeouts for retries in `restart.html`, `reboot.html`, and `shutdown.html`.
* **Network & Audio:** Updated `install.sh` and `main.py` to allow and run HTTP directly on port 80. Added audio input-device info on the calibration page and a restart option to update the device.

### Version 0.1b

#### Hushbeat (Status LED on GPIO17)
Added `hushbeat.sh` (Heartbeat LED showing status on GPIO17):
`GPIO17 o---[Resistor]----->LED|---o GND`

| State | Pattern |
| :--- | :--- |
| **All good** | Slow single blink |
| **HushMonkey down, USB audio OK** | Fast single blink |
| **HushMonkey OK, no USB audio** | Slow double-blink |
| **HushMonkey down + no USB audio** | Fast double-blink |

#### CPU Optimization in `main.py`
Fixed high CPU usage and sluggish UI response (went from **~98% CPU to ~8%** on a Raspberry Pi 3+):

| Problem / Area | Before | After |
| :--- | :--- | :--- |
| **`buf_1m` mean** | Iterate 2.88M floats every 21ms | $O(1)$ running sum |
| **`buf_10m` mean** | Iterate 28.8M floats every 21ms | $O(1)$ running sum |
| **Memory** | ~46 MB just for buffers | ~37 KB for chunk sums |

*Other 0.1b improvements:*
* Added HTTP endpoint `/exit` to exit the wrapper for debugging purposes.
* Added systemd service scripts to start/stop `wrapper.sh` and `hushbeat.sh`.
* Ensured Flask is running threaded + set `Cache-Control: no-cache` on `/data`.
* Updated `index.html` to update every 300ms (was 500ms before).
* Slightly tighter sleep in `AudioLoop` for faster exit response.

### Version 0.1
* Let's welcome the Chill Chimpanzee / The Hush Monkey.
* Initial version that works.

</details>
