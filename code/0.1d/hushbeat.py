#!/usr/bin/env python3
import subprocess
import time
import signal
import sys
from gpiozero import LED

PIN = 17
led = LED(PIN)

def cleanup(signum, frame):
    led.off()
    led.close()
    sys.exit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

def is_service_active(name):
    result = subprocess.run(
        ["systemctl", "is-active", name],
        capture_output=True, text=True
    )
    return result.stdout.strip() == "active"

def usb_soundcard_present():
    result = subprocess.run(
        ["aplay", "-l"],
        capture_output=True, text=True
    )
    return "USB" in result.stdout or "usb" in result.stdout

def single_blink(delay):
    led.on()
    time.sleep(delay)
    led.off()
    time.sleep(delay)

def double_blink(delay):
    # First blink
    led.on()
    time.sleep(delay)
    led.off()
    time.sleep(delay * 0.8)
    # Second blink
    led.on()
    time.sleep(delay)
    led.off()
    # Longer pause between double-blink groups so it reads as "pairs"
    time.sleep(delay * 2.1)

while True:
    hushmonkey_ok = is_service_active("hushmonkey.service")
    audio_ok = usb_soundcard_present()

    if hushmonkey_ok and audio_ok:
        single_blink(0.8)          # All good slow single

    elif not hushmonkey_ok and audio_ok:
        single_blink(0.15)          # hushmonkey down fast single

    elif hushmonkey_ok and not audio_ok:
        double_blink(0.4)          # No audio slow double

    else:
        double_blink(0.15)          # Everything down fast double
