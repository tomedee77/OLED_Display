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
BUTTON_PIN = 17  # GPIO pin for momentary button
DEBOUNCE = 0.2   # button debounce time in seconds
LINE_SPACING = 5  # vertical pixels between label and value
LOG_DIR = "/home/tomedee77/TunerStudioProjects/VWRX/DataLogs"

# Labels and test values
TEST_LABELS = ["RPM", "TPS", "AFR", "Coolant", "IAT"]
TEST_VALUES = ["1000", "12.5%", "14.7", "90°C", "25°C"]

# Fonts
font_small = ImageFont.load_default(25)
try:
    font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 35)
except:
    font_large = ImageFont.load_default(35)

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

clear_old_logs()  # clear old logs at startup

# Get the latest log file for live monitoring
def get_latest_log_file():
    files = sorted(glob.glob(os.path.join(LOG_DIR, "*.msl")) + glob.glob(os.path.join(LOG_DIR, "*.mlg")), key=os.path.getmtime, reverse=True)
    return files[0] if files else None

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
        # Measure label and value sizes
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

        # Optional blink indicator (e.g., "T" for test mode)
        if indicator and blink:
            draw.text((0, 0), indicator, font=font_small, fill=255)

def is_tunerstudio_running():
    # simple check: if latest log file exists and is being updated
    latest = get_latest_log_file()
    if latest:
        try:
            mtime = os.path.getmtime(latest)
            if time.time() - mtime < 5:  # updated within last 5 seconds
                return True
        except:
            return False
    return False

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

        # Toggle blink every 0.5 sec
        if time.time() - blink_timer > 0.5:
            blink = not blink
            blink_timer = time.time()

        # Determine what to display
        label = TEST_LABELS[current_index]
        value = TEST_VALUES[current_index]

        # If not in test mode, show TS status instead
        if not test_mode:
            ts_status = "TS OK" if is_tunerstudio_running() else "TS --"
            draw_oled(ts_status, "", indicator="")
        else:
            draw_oled(label, value, indicator="T")

        time.sleep(0.05)

except KeyboardInterrupt:
    GPIO.cleanup()
