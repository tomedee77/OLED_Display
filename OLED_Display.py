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
LONG_PRESS = 2        # seconds to return to GPS
LOG_DIR = "/home/tomedee77/TunerStudioProjects/VWRX/DataLogs"
GPS_PORT = "/dev/gps0"
GPS_BAUD = 9600

# Labels for live mode (ECU + GPS)
LIVE_LABELS = ["GPS", "MAP", "AFR", "CLT", "MAT"]

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

button_down_time = None
last_press_time = 0
blink = True
blink_timer = time.time()
latest_log_file = None

# Start on GPS
current_index = 0

# Setup GPS
try:
    gps_serial = serial.Serial(GPS_PORT, GPS_BAUD, timeout=1)
except Exception:
    gps_serial = None

gps_fix = False

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

def get_next_index():
    global current_index
    current_index = (current_index + 1) % len(LIVE_LABELS)
    return current_index

def draw_oled(label, value, gps_fix=False):
    global device, blink
    with canvas(device) as draw:
        if label == "GPS":
            # GPS value only, centered
            bbox = font_large.getbbox(value)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((OLED_WIDTH - w)/2, (OLED_HEIGHT - h)/2), value, font=font_large, fill=255)

            # GPS fix dot top-left
            if gps_fix and blink:
                draw.text((0, 0), "•", font=font_small, fill=255)
        else:
            # Label top
            bbox = font_small.getbbox(label)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((OLED_WIDTH - w)/2, 0), label, font=font_small, fill=255)

            # Value bottom
            bbox = font_large.getbbox(value)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((OLED_WIDTH - w)/2, 16), value, font=font_large, fill=255)

def read_latest_value(label, file_path):
    """Tail the log file, skip metadata lines, return latest numeric value"""
    try:
        if not file_path or not os.path.exists(file_path):
            return "N/A"

        with open(file_path, "r") as f:
            lines = f.readlines()

        if len(lines) < 3:
            return "N/A"

        # First line = headers
        header = lines[0].strip().split("\t")
        if label not in header:
            return "N/A"
        idx = header.index(label)

        # Walk backwards to find the latest valid numeric row
        for line in reversed(lines):
            parts = line.strip().split("\t")
            if len(parts) <= idx:
                continue
            try:
                float(parts[0])  # first column numeric check
            except ValueError:
                continue
            return parts[idx]

        return "N/A"

    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return "N/A"

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

# ----------------------------
# MAIN LOOP
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
        if button_state == 0:
            if button_down_time is None:
                button_down_time = now
            elif now - button_down_time >= LONG_PRESS:
                # Return to GPS
                current_index = 0
        else:
            if button_down_time:
                if now - last_press_time > DEBOUNCE and now - button_down_time < LONG_PRESS:
                    # Short press -> next log value (skip GPS)
                    if current_index == 0:
                        current_index = 1
                    else:
                        get_next_index()
                    last_press_time = now
                button_down_time = None

        # Update latest log file
        if current_index != 0:  # only read log if not GPS
            candidate = find_latest_log()
            if candidate and candidate != latest_log_file:
                latest_log_file = candidate

        # Pick value
        label = LIVE_LABELS[current_index]
        if label == "GPS":
            value = read_gps_speed()
        else:
            value = read_latest_value(label, latest_log_file)

        draw_oled(label, value, gps_fix=gps_fix)

        time.sleep(0.1)

except KeyboardInterrupt:
    GPIO.cleanup()