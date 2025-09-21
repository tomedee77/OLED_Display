#!/usr/bin/env python3
import os
import glob
import time
import RPi.GPIO as GPIO
from luma.core.interface.serial import i2c
from luma.oled.device import sh1106
from luma.core.render import canvas
from PIL import ImageFont

# ----------------------------
# CONFIG
# ----------------------------
OLED_WIDTH = 128
OLED_HEIGHT = 32
BUTTON_PIN = 17  # GPIO pin for momentary button
DEBOUNCE = 0.2   # button debounce time in seconds
LOG_DIR = "/home/tomedee77/TunerStudioProjects/VWRX/DataLogs"
LOG_COLUMNS = ["MAP", "AFR", "CLT", "MAT"]  # columns to read from log
NO_DATA_TIMEOUT = 5  # seconds

# Labels and test values
TEST_LABELS = ["RPM", "TPS", "AFR", "Coolant", "IAT"]
TEST_VALUES = ["1000", "12.5%", "14.7", "90°C", "25°C"]

# Fonts
font_small = ImageFont.load_default(20)
try:
    font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
except:
    font_large = ImageFont.load_default(40)

# ----------------------------
# SETUP
# ----------------------------
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

serial = i2c(port=1, address=0x3C)
device = sh1106(serial)

current_index = 0
test_mode = True
last_press_time = 0
blink = True
blink_timer = time.time()
last_data_time = 0

# ----------------------------
# LOG FILE HANDLING
# ----------------------------
log_fh = None
log_headers = []

def clear_old_logs():
    files = glob.glob(os.path.join(LOG_DIR, "*"))
    for f in files:
        try:
            os.remove(f)
        except:
            pass

def get_latest_log_file():
    files = sorted(
        glob.glob(os.path.join(LOG_DIR, "*.msl")) + glob.glob(os.path.join(LOG_DIR, "*.mlg")),
        key=os.path.getmtime, reverse=True
    )
    return files[0] if files else None

def open_log_tail():
    global log_fh, log_headers
    latest = get_latest_log_file()
    if not latest:
        return False
    try:
        log_fh = open(latest, "r")
        lines = log_fh.readlines()
        if lines:
            log_headers = [h.strip() for h in lines[0].strip().split(",")]
        log_fh.seek(0, os.SEEK_END)
        return True
    except:
        log_fh = None
        return False

def read_next_log_line():
    global log_fh, log_headers
    if not log_fh:
        if not open_log_tail():
            return None
    line = log_fh.readline()
    if not line:
        return None
    parts = line.strip().split(",")
    data = {}
    for col in LOG_COLUMNS:
        if col in log_headers:
            idx = log_headers.index(col)
            data[col] = parts[idx] if idx < len(parts) else "N/A"
        else:
            data[col] = "N/A"
    return data

# ----------------------------
# OLED DISPLAY
# ----------------------------
LINE_SPACING = 2

def draw_oled(label, value, indicator=False, ts_running=False, no_data=False):
    global device, blink
    with canvas(device) as draw:
        if no_data:
            # Centered NO DATA message
            bbox = font_large.getbbox("NO DATA")
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((OLED_WIDTH - w) / 2, (OLED_HEIGHT - h) / 2),
                      "NO DATA", font=font_large, fill=255)
            return

        # Top line: label
        bbox = font_small.getbbox(label)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((OLED_WIDTH - w) / 2, 0), label, font=font_small, fill=255)

        # Bottom line: value
        bbox_val = font_large.getbbox(value)
        w_val, h_val = bbox_val[2] - bbox_val[0], bbox_val[3] - bbox_val[1]
        y_pos = h + LINE_SPACING
        draw.text(((OLED_WIDTH - w_val) / 2, y_pos), value, font=font_large, fill=255)

        # Test mode blink indicator (T)
        if indicator and blink:
            draw.text((0, 0), "T", font=font_small, fill=255)

        # Live mode TS indicator (top right)
        if ts_running:
            draw.text((OLED_WIDTH - 16, 0), "TS", font=font_small, fill=255)

# ----------------------------
# BUTTON HANDLING
# ----------------------------
def get_next_index():
    global current_index
    current_index += 1
    if current_index >= len(TEST_LABELS):
        current_index = 0
    return current_index

# ----------------------------
# MAIN
# ----------------------------
clear_old_logs()

try:
    while True:
        # Button polling
        if GPIO.input(BUTTON_PIN) == 0:  # pressed
            now = time.time()
            if now - last_press_time > DEBOUNCE:
                get_next_index()
                last_press_time = now

        # Toggle blink every 0.5 sec
        if time.time() - blink_timer > 0.5:
            blink = not blink
            blink_timer = time.time()

        # Read live data
        live_data = read_next_log_line()
        if live_data:
            test_mode = False
            last_data_time = time.time()
            keys = list(live_data.keys())
            key = keys[current_index % len(keys)]
            label = key
            value = str(live_data[key])
            draw_oled(label, value, indicator=False, ts_running=True, no_data=False)
        else:
            # If TS is running but no data for too long -> NO DATA warning
            if not test_mode and (time.time() - last_data_time > NO_DATA_TIMEOUT):
                draw_oled("", "", no_data=True)
            else:
                test_mode = True
                label = TEST_LABELS[current_index]
                value = TEST_VALUES[current_index]
                draw_oled(label, value, indicator=True, ts_running=False, no_data=False)

        time.sleep(0.05)

except KeyboardInterrupt:
    GPIO.cleanup()
