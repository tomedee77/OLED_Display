#!/usr/bin/env python3
import time
import os
import glob
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
BUTTON_PIN = 17
DEBOUNCE = 0.2
LINE_SPACING = 2
LOG_DIR = "/home/tomedee77/TunerStudioProjects/VWRX/DataLogs"
LOG_COLUMNS = ["MAP", "AFR", "CLT", "MAT"]  # columns to read from log

# Test mode data
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

# ----------------------------
# LOG FILE HANDLING
# ----------------------------
def clear_old_logs():
    files = glob.glob(os.path.join(LOG_DIR, "*.msl")) + glob.glob(os.path.join(LOG_DIR, "*.mlg"))
    for f in files:
        try:
            os.remove(f)
        except:
            pass

def get_latest_log_file():
    files = sorted(glob.glob(os.path.join(LOG_DIR, "*.msl")) + glob.glob(os.path.join(LOG_DIR, "*.mlg")),
                   key=os.path.getmtime, reverse=True)
    return files[0] if files else None

clear_old_logs()

# ----------------------------
# HELPER FUNCTIONS
# ----------------------------
def get_next_index():
    global current_index
    current_index += 1
    if current_index >= len(TEST_LABELS):
        current_index = 0
    return current_index

def draw_oled(label, value, indicator=""):
    global blink
    with canvas(device) as draw:
        # Compute label and value size
        label_bbox = font_small.getbbox(label)
        value_bbox = font_large.getbbox(value)

        label_width = label_bbox[2] - label_bbox[0]
        label_height = label_bbox[3] - label_bbox[1]

        value_width = value_bbox[2] - value_bbox[0]
        value_height = value_bbox[3] - value_bbox[1]

        total_height = label_height + LINE_SPACING + value_height
        y_offset = (OLED_HEIGHT - total_height) / 2

        # Draw label
        draw.text(
            ((OLED_WIDTH - label_width) / 2, y_offset),
            label,
            font=font_small,
            fill=255
        )

        # Draw value
        draw.text(
            ((OLED_WIDTH - value_width) / 2, y_offset + label_height + LINE_SPACING),
            value,
            font=font_large,
            fill=255
        )

        # Blink indicator
        if indicator and blink:
            draw.text((0, 0), indicator, font=font_small, fill=255)

def is_tunerstudio_running():
    latest = get_latest_log_file()
    if latest:
        try:
            mtime = os.path.getmtime(latest)
            return time.time() - mtime < 5
        except:
            return False
    return False

def read_live_data():
    latest = get_latest_log_file()
    if not latest:
        return None
    try:
        with open(latest, "r") as f:
            lines = f.readlines()
            if not lines:
                return None
            last_line = lines[-1].strip().split(",")
            # Map the required columns
            data = {}
            headers = [h.strip() for h in lines[0].strip().split(",")]
            for col in LOG_COLUMNS:
                if col in headers:
                    idx = headers.index(col)
                    data[col] = last_line[idx]
                else:
                    data[col] = "N/A"
            return data
    except:
        return None

# ----------------------------
# MAIN LOOP
# ----------------------------
try:
    while True:
        # Button polling
        if GPIO.input(BUTTON_PIN) == 0:  # pressed
            now = time.time()
            if now - last_press_time > DEBOUNCE:
                get_next_index()
                last_press_time = now

        # Blink toggle
        if time.time() - blink_timer > 0.5:
            blink = not blink
            blink_timer = time.time()

        # Live mode check
        live_data = read_live_data()
        if live_data:
            test_mode = False
            keys = list(live_data.keys())
            key = keys[current_index % len(keys)]
            label = key
            value = str(live_data[key])
            draw_oled(label, value, indicator="")  # no blink in live
        else:
            test_mode = True
            label = TEST_LABELS[current_index]
            value = TEST_VALUES[current_index]
            draw_oled(label, value, indicator="T")

        time.sleep(0.05)

except KeyboardInterrupt:
    GPIO.cleanup()
