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
LONG_PRESS = 2.0      # seconds for long press to enter test mode
LOG_DIR = "/home/tomedee77/TunerStudioProjects/VWRX/DataLogs"
GPS_PORT = "/dev/gps0"  # change to your GPS device
GPS_BAUD = 9600

# Labels we want to display (must match log columns!)
LIVE_LABELS = ["MAP", "AFR", "CLT", "MAT", "GPS_Speed"]

# Test labels/values for bench test
TEST_LABELS = ["RPM", "TPS", "AFR", "Coolant", "IAT", "GPS_Speed"]
TEST_VALUES = ["1000", "12.5%", "14.7", "90°C", "25°C", "0 km/h"]

# Fonts
font_small = ImageFont.load_default(15)
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

serial_i2c = i2c(port=1, address=0x3C)
device = sh1106(serial_i2c)

current_index = 0
test_mode = False          # Boot into live mode
last_press_time = 0
press_start_time = None
blink = True
blink_timer = time.time()
latest_log_file = None
gps_speed = "0 km/h"

# GPS setup
try:
    gps_serial = serial.Serial(GPS_PORT, GPS_BAUD, timeout=1)
except Exception as e:
    gps_serial = None
    print(f"GPS not available: {e}")

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

def get_next_index(labels):
    global current_index
    current_index = (current_index + 1) % len(labels)
    return current_index

def draw_oled(label, value, blink_indicator=False):
    global device, blink
    with canvas(device) as draw:
        if label == "GPS_Speed":
            bbox = font_large.getbbox(value)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
            draw.text(((OLED_WIDTH - w)/2, (OLED_HEIGHT - h)/2), value, font=font_large, fill=255)
        else:
            bbox = font_small.getbbox(label)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
            draw.text(((OLED_WIDTH - w)/2, 0), label, font=font_small, fill=255)

            bbox = font_large.getbbox(value)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
            draw.text(((OLED_WIDTH - w)/2, 16), value, font=font_large, fill=255)

            if blink_indicator and blink:
                draw.text((0, 0), "T", font=font_small, fill=255)

def read_latest_value(label, file_path):
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

def read_gps():
    global gps_speed
    if gps_serial and gps_serial.in_waiting:
        try:
            line = gps_serial.readline().decode("ascii", errors="replace")
            if line.startswith("$GPRMC") or line.startswith("$GNRMC"):
                msg = pynmea2.parse(line)
                if msg.spd_over_grnd is not None:
                    gps_speed = f"{round(msg.spd_over_grnd * 1.852)} km/h"
        except Exception:
            pass

# ----------------------------
# MAIN
# ----------------------------
cleanup_old_logs()

try:
    while True:
        # Update blink
        if time.time() - blink_timer > 0.5:
            blink = not blink
            blink_timer = time.time()

        # Read GPS
        read_gps()

        # Button handling
        if GPIO.input(BUTTON_PIN) == 0:  # pressed
            if press_start_time is None:
                press_start_time = time.time()
            elif (time.time() - press_start_time) >= LONG_PRESS:
                test_mode = True  # long press enters test mode
        else:  # released
            if press_start_time:
                duration = time.time() - press_start_time
                press_start_time = None
                if duration < LONG_PRESS:
                    # Short press: cycle index
                    get_next_index(TEST_LABELS if test_mode else LIVE_LABELS)

        # If in live mode, check for new log
        if not test_mode:
            candidate = find_latest_log()
            if candidate and candidate != latest_log_file:
                latest_log_file = candidate

        # Display current value
        label = (TEST_LABELS if test_mode else LIVE_LABELS)[current_index]
        if label == "GPS_Speed":
            value = gps_speed
        elif test_mode:
            value = TEST_VALUES[current_index]
        else:
            value = read_latest_value(label, latest_log_file)

        draw_oled(label, value, blink_indicator=test_mode)

        time.sleep(0.1)

except KeyboardInterrupt:
    GPIO.cleanup()