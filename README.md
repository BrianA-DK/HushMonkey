

![Logo](https://github.com/BrianA-DK/HushMonkey/blob/main/0.3a/html/icon-192.png)

**There are 2 flavours of HushMonkey - Both designed to run on a Raspberry Pi 3+**
- 0.2: A lightweight version that solved my most basic needs to monitor LAF during shows. Minimalistic and straight to the point.
- 0.3: "Open Sound Meter and SMAART" in a browser, almost... 😉 Just the features you actually need for 99% of the jobs where you setup a sound system and run a consistent level thru the show. .

**Quick start:**\
Download `install.sh` and the folder with the version you want to use.

**Usage:**\
  ```./install.sh [version]```       --> install/activate a version\
	```./install.sh --rollback```      --> reactivate the previously active version
 After install/upgrade/rollback please reboot and refresh browser to make sure backend and frontend are running the same version
 Read the [How to install](/How_to_install.md) for a more indepth guide.

## How to use ##
Check out the [Cheat Sheets](https://github.com/BrianA-DK/HushMonkey/tree/main/Cheat%20Sheets) to get started on using Hush Monkey when setting up your PA.

**Hidden trick: On the LAF-view. Double-click inside each of the 3 LAF-fields to reset Max-value.**

![LAF view](https://github.com/BrianA-DK/HushMonkey/blob/main/images/lafview2.png)


## Functions ##

### Grumpy Gorilla-series (0.3): ###

#### Genral ####
- Fullscreen toggle by clicking on the icon in the upper right corner.

#### LAF meter ####
- Calculates A-weighted Fast Sound Level ($L_{\text{AF}}$) alongside integrated short-term ($L_{\text{Aeq,1m}}$) and long-term ($L_{\text{Aeq,10m}}$) equivalent continuous noise levels.
- Noise Statistics & Trends: Computes statistical noise indicators ($L_{10}$ peak levels and $L_{90}$ ambient background noise) and measures 30-second trends (dB/min rate of change).
- Limit Exceedance & ETA Prediction: Calculates estimated time remaining before reaching configured exposure limits ($L_{\text{Aeq,10m}}$ ETA) and triggers visual warnings when thresholds are approached or breached.
- Waterfall Spectrogram: Displays a continuous, real-time 2D color-coded waterfall history of frequency levels over time.
- Dark/Light mode toggle by clicking on the Moon/Sun icon in the upper left corner

#### Frequency & Spectrum Analysis (Spectrum Analyzer ) ####
- 1/3-Octave Band RTA: Analyzes 30 standard IEC center frequencies (from 20 Hz to 16,000 Hz).
- Peak Hold & Display Controls: Supports configurable peak decay speeds (Slow/Fast)
- multiple Y-axis scaling ranges (0–60 dB, 60–100 dB, 40–120 dB), and exponential moving average (EMA) smoothing options
- House / Target Curve Overlays: Allows loading, saving, exporting, and interactive drag-and-drop editing of target frequency curves. Includes adjustable tolerance zones ($\pm 1.5\text{ dB}$ to $\pm 5\text{ dB}$) and global dB offsets.
- Pink Noise Compensation: Built-in pink noise generator and $+3\text{ dB/octave}$ compensation mode for RTA tuning.

#### Acoustic Test & Measurement (Transfer & IR) ####
- Transfer Function Measurement.
- Real-time dual-channel acoustic transfer measurement calculating Magnitude (dB), Phase (degrees), and Coherence relative to a reference signal.
- Delay Detection & Alignment: Calculates physical propagation delay in milliseconds and sample counts using FFT-based cross-correlation.
- Features Auto-tracking, Lock Delay, and manual sample offset adjustment.
- Impulse Response (IR): Computes and displays the time-domain impulse response curve.
- Coherence Blanking & Auto-Cal: Dynamic coherence thresholding to filter out room noise or uncorrelated reflections, alongside one-click Auto-Calibration to normalize magnitude to $0\text{ dB}$.
- Trace Storage & Export: Allows capturing up to 3 overlay memory slots, with import/export capabilities in JSON and CSV formats.

#### Calibration & Sound Hardware Setup #### 
- Acoustic Microphone Calibration: Step-by-step calibration sequence using external sound calibrators ($94\text{ dB}$, $104\text{ dB}$, or $114\text{ dB}$) to calculate and store reference sensitivity factors.
- Threshold & Limit Management: User-definable alarm limits and warning margins for $L_{\text{AF}}$, $L_{\text{Aeq,1m}}$, and $L_{\text{Aeq,10m}}$, plus configurable alert delays.
- Sound Card Selector: Auto-detects connected ALSA USB audio interfaces and configures volume levels directly via system shell tools.
- Restart, Reboot and Shutdown controls
- A quite bananas About-screen (do NOT spank the monkey - I double dare you...)

### Chill Chimpanzee-series (0.2): ###

#### LAF meter ####
- Calculates A-weighted Fast Sound Level ($L_{\text{AF}}$) alongside integrated short-term ($L_{\text{Aeq,1m}}$) and long-term ($L_{\text{Aeq,10m}}$) equivalent continuous noise levels.
- Limit Exceedance triggers visual warnings when thresholds breached.

#### Frequency & Spectrum Analysis (Spectrum Analyzer ) ####
- 1/3-Octave Band RTA: Analyzes 30 standard IEC center frequencies (from 20 Hz to 16,000 Hz).
- Peak Hold & Display Controls: Supports configurable peak decay speeds (Slow/Fast)
- Multiple Y-axis scaling ranges.

#### Calibration & Sound Hardware Setup #### 
- Acoustic Microphone Calibration: Step-by-step calibration sequence using external sound calibrators ($94\text{ dB}$, $104\text{ dB}$, or $114\text{ dB}$) to calculate and store reference sensitivity factors.
- Threshold & Limit Management: User-definable alarm limits for $L_{\text{AF}}$, $L_{\text{Aeq,1m}}$, and $L_{\text{Aeq,10m}}$, plus configurable alert delays.
- Sound Card Selector: Auto-detects connected ALSA USB audio interfaces and configures volume levels directly via system shell tools.
- Restart, Reboot and Shutdown controls
- A quite bananas About-screen (do NOT spank the monkey - I dare you...)
