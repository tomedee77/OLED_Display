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
BUTTON_PIN = 17          # GPIO pin for momentary button
DEBOUNCE = 0.2           # button debounce time
LOG_DIR = "/home/tomedee77/TunerStudioProjects/VWRX/DataLogs"

GPS_PORT = "/dev/ttyACM0"
GPS_BAUD = 9600

# Labels we want to display (must match log columns!)
LIVE_LABELS = ["MAP", "AFR", "CLT", "MAT", "GPS_Speed"]

# Test labels/values for bench test
TEST_LABELS = ["RPM", "TPS", "AFR", "Coolant", "IAT", "GPS_Speed"]
TEST_VALUES = ["1000", "12.5%", "14.7", "90°C", "25°C", "0.0 mph"]

# ----------------------------
# FONTS
# ----------------------------
font_small = ImageFont.load_default()
try:
    font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
except:
    font_large = ImageFont.load_default()

# ----------------------------
# SETUP
# ----------------------------
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

serial_oled = i2c(port=1, address=0x3C)
device = sh1106(serial_oled)

# GPS setup
gps_speed = "0.0 mph"
try:
    gps_ser = serial.Serial(GPS_PORT, GPS_BAUD, timeout=1)
except Exception as e:
    print(f"GPS init failed: {e}")
    gps_ser = None

current_index = 0
test_mode = True
last_press_time = 0
blink = True
blink_timer = time.time()
latest_log_file = None

# ----------------------------
# HELPER FUNCTIONS
# ----------------------------
def cleanup_old_logs():
    """Delete logs older than today"""
    today = datetime.now().date()
    for f in glob.glob(os.path.join(LOG_DIR, "*.msl")) + glob.glob(os.path.join(LOG_DIR, "*.mlg")):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(f)).date()
            if mtime < today:
                os.remove(f)
        except Exception as e:
            print(f"Failed to remove {f}: {e}")

def find_latest_log():
    """Find the most recent log file"""
    files = glob.glob(os.path.join(LOG_DIR, "*.msl")) + glob.glob(os.path.join(LOG_DIR, "*.mlg"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def get_next_index(labels):
    global current_index
    current_index = (current_index + 1) % len(labels)
    return current_index

def update_gps_speed():
    global gps_speed
    if not gps_ser:
        gps_speed = "N/A"
        return
    try:
        line = gps_ser.readline().decode(errors='ignore').strip()
        if line.startswith("$GPRMC") or line.startswith("$GNRMC"):
            msg = pynmea2.parse(line)
            if msg.spd_over_grnd:
                gps_speed = f"{float(msg.spd_over_grnd)*1.15078:.1f} mph"
    except Exception:
        gps_speed = "N/A"

def read_latest_value(label, file_path):
    """Read last logged value for given label from the log file"""
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
            if len(lines) < 2:
                return "N/A"
            header = lines[0].strip().split("\t")
            if label not in header:
                return "N/A"
            idx = header.index(label)
            last = lines[-1].strip().split("\t")
            return last[idx]
    except Exception:
        return "N/A"

def draw_oled(label, value, blink_indicator=False):
    global device, blink, gps_speed
    with canvas(device) as draw:
        # Top line: label
        bbox = font_small.getbbox(label)
        w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text(((OLED_WIDTH - w) / 2, 0), label, font=font_small, fill=255)

        # Bottom line: value
        bbox = font_large.getbbox(value)
        w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text(((OLED_WIDTH - w) / 2, 16), value, font=font_large, fill=255)

        # Blink "T" for test mode
        if blink_indicator and blink:
            draw.text((0, 0), "T", font=font_small, fill=255)

        # GPS speed always top-right
        gps_text = gps_speed
        bbox = font_small.getbbox(gps_text)
        w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text((OLED_WIDTH - w, 0), gps_text, font=font_small, fill=255)

# ----------------------------
# MAIN
# ----------------------------
cleanup_old_logs()

try:
    while True:
        # Update GPS
        update_gps_speed()

        # Blink toggle
        if time.time() - blink_timer > 0.5:
            blink = not blink
            blink_timer = time.time()

        # Button pressed?
        if GPIO.input(BUTTON_PIN) == 0:
            now = time.time()
            if now - last_press_time > DEBOUNCE:
                get_next_index(TEST_LABELS if test_mode else LIVE_LABELS)
                last_press_time = now

        # Switch to live mode if a log appears
        if test_mode:
            candidate = find_latest_log()
            if candidate and candidate != latest_log_file:
                latest_log_file = candidate
                test_mode = False
                current_index = 0

        # Display values
        if test_mode:
            label = TEST_LABELS[current_index]
            value = TEST_VALUES[current_index] if label != "GPS_Speed" else gps_speed
            draw_oled(label, value, blink_indicator=True)
        else:
            label = LIVE_LABELS[current_index]
            value = gps_speed if label == "GPS_Speed" else read_latest_value(label, latest_log_file)
            draw_oled(label, value, blink_indicator=False)

        time.sleep(0.1)

except KeyboardInterrupt:
    GPIO.cleanup()