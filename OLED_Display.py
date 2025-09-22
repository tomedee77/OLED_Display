#!/usr/bin/env python3
import time
import os
import glob
from datetime import datetime
import RPi.GPIO as GPIO
from luma.core.interface.serial import i2c
from luma.oled.device import sh1106
from luma.core.render import canvas
from PIL import ImageFont
import serial
import pynmea2

# ----------------------------
# CONFIG
# ----------------------------
OLED_WIDTH = 128
OLED_HEIGHT = 32
BUTTON_PIN = 17       # GPIO pin for momentary button
DEBOUNCE = 0.2        # debounce time
LONG_PRESS = 2        # seconds to return to GPS display
LOG_DIR = "/home/tomedee77/TunerStudioProjects/VWRX/DataLogs"
GPS_PORT = "/dev/gps0"
GPS_BAUD = 9600

LIVE_LABELS = ["MAP", "AFR", "CLT", "MAT", "GPS"]

# Fonts
font_small = ImageFont.load_default()
try:
    font_large = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40
    )
except:
    font_large = ImageFont.load_default()

# ----------------------------
# SETUP
# ----------------------------
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

serial_oled = i2c(port=1, address=0x3C)
device = sh1106(serial_oled)

current_index = 0
showing_gps = True
button_down_time = None
last_press_time = 0
blink = True
blink_timer = time.time()
latest_log_file = None
gps_fix = False

# Setup GPS
try:
    gps_serial = serial.Serial(GPS_PORT, GPS_BAUD, timeout=1)
except Exception:
    gps_serial = None

# Track file pointer for tailing
log_fp = None

# ----------------------------
# HELPER FUNCTIONS
# ----------------------------
def cleanup_old_logs():
    today = datetime.now().date()
    for f in glob.glob(os.path.join(LOG_DIR, "*.msl")) + glob.glob(os.path.join(LOG_DIR, "*.mlg")):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(f)).date()
            if mtime < today:
                os.remove(f)
        except Exception as e:
            print(f"Failed to remove {f}: {e}")

def find_latest_log():
    files = glob.glob(os.path.join(LOG_DIR, "*.msl")) + glob.glob(os.path.join(LOG_DIR, "*.mlg"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def draw_oled(label, value, gps_fix=False):
    global device, blink
    with canvas(device) as draw:
        if label == "GPS":
            bbox = font_large.getbbox(value)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((OLED_WIDTH - w)/2, (OLED_HEIGHT - h)/2), value, font=font_large, fill=255)
        else:
            # Label top
            bbox = font_small.getbbox(label)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((OLED_WIDTH - w)/2, 0), label, font=font_small, fill=255)
            # Value bottom
            bbox = font_large.getbbox(value)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((OLED_WIDTH - w)/2, 16), value, font=font_large, fill=255)
        # GPS fix dot
        if gps_fix and label == "GPS":
            draw.text((0,0), "•", font=font_small, fill=255)

def read_gps_speed():
    global gps_fix
    if not gps_serial:
        gps_fix = False
        return "0.0"
    try:
        line = gps_serial.readline().decode('ascii', errors='replace')
        if line.startswith('$GPRMC'):
            msg = pynmea2.parse(line)
            if msg.spd_over_grnd:
                mph = float(msg.spd_over_grnd) * 1.15078
                gps_fix = True
                return f"{mph:.1f}"
            else:
                gps_fix = False
    except Exception:
        gps_fix = False
    return "0.0"

def read_latest_value(label):
    """Return the last value for label by tailing the log"""
    global log_fp
    if not log_fp:
        return "N/A"
    while True:
        pos = log_fp.tell()
        line = log_fp.readline()
        if not line:
            log_fp.seek(pos)
            break
        # Skip empty or metadata lines
        if line.strip() and not line.startswith("MS2Extra") and not line.startswith("Capture Date") and not line.startswith("Time"):
            parts = line.strip().split()
            if label in LIVE_LABELS:
                try:
                    idx = LIVE_LABELS.index(label)
                    if idx < len(parts):
                        return parts[idx]
                except:
                    return "N/A"
    return "N/A"

# ----------------------------
# MAIN
# ----------------------------
cleanup_old_logs()

try:
    while True:
        # Blink toggle
        if time.time() - blink_timer > 0.5:
            blink = not blink
            blink_timer = time.time()

        # Button polling
        button_state = GPIO.input(BUTTON_PIN)
        now = time.time()
        if button_state == 0:  # pressed
            if button_down_time is None:
                button_down_time = now
            elif now - button_down_time >= LONG_PRESS:
                showing_gps = True  # long press returns to GPS
        else:  # released
            if button_down_time is not None:
                press_duration = now - button_down_time
                if press_duration < LONG_PRESS and now - last_press_time > DEBOUNCE:
                    if showing_gps:
                        showing_gps = False
                        current_index = 0
                    else:
                        current_index = (current_index + 1) % (len(LIVE_LABELS)-1)  # exclude GPS from cycling
                last_press_time = now
                button_down_time = None

        # Open latest log for tailing if needed
        if not showing_gps:
            candidate = find_latest_log()
            if candidate != latest_log_file:
                latest_log_file = candidate
                try:
                    if log_fp:
                        log_fp.close()
                    log_fp = open(latest_log_file, "r")
                    # Skip to last line
                    log_fp.seek(0, os.SEEK_END)
                except Exception:
                    log_fp = None

        # Determine what to display
        if showing_gps:
            label = "GPS"
            value = read_gps_speed()
        else:
            label = LIVE_LABELS[current_index]
            if label == "GPS":
                value = read_gps_speed()
            else:
                value = read_latest_value(label)

        draw_oled(label, value, gps_fix=gps_fix)
        time.sleep(0.1)

except KeyboardInterrupt:
    GPIO.cleanup()
    if log_fp:
        log_fp.close()