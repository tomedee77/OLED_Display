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
LONG_PRESS = 2.0      # long press to enter/exit test mode
LOG_DIR = "/home/tomedee77/TunerStudioProjects/VWRX/DataLogs"
GPS_PORT = "/dev/ttyACM0"
GPS_BAUD = 9600

# Labels we want to display (must match log columns!)
LIVE_LABELS = ["MAP", "AFR", "CLT", "MAT"]

# Test labels/values for bench test
TEST_LABELS = ["RPM", "TPS", "AFR", "Coolant", "IAT"]
TEST_VALUES = ["1000", "12.5%", "14.7", "90°C", "25°C"]

# Fonts
font_small = ImageFont.load_default()
try:
    font_large = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16
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
test_mode = False        # Boot to live mode
last_press_time = 0
button_press_start = None
blink = True
blink_timer = time.time()
latest_log_file = None

# GPS serial
try:
    gps_serial = serial.Serial(GPS_PORT, GPS_BAUD, timeout=1)
except Exception:
    gps_serial = None

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

def draw_oled(label, value, blink_indicator=False):
    global device, blink
    with canvas(device) as draw:
        # Label (top)
        bbox = font_small.getbbox(label)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((OLED_WIDTH - w) / 2, 0), label, font=font_small, fill=255)

        # Value (bottom, with spacing)
        bbox = font_large.getbbox(value)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((OLED_WIDTH - w) / 2, 16), value, font=font_large, fill=255)

        # Blinking "T" if test mode
        if blink_indicator and blink:
            draw.text((0, 0), "T", font=font_small, fill=255)

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

def read_gps_speed():
    """Return GPS speed in MPH"""
    if not gps_serial:
        return "N/A"
    try:
        line = gps_serial.readline().decode("ascii", errors="ignore")
        msg = pynmea2.parse(line)
        if hasattr(msg, "spd_over_grnd"):
            mph = msg.spd_over_grnd * 1.15078
            return f"{int(mph)} mph"
        return "N/A"
    except:
        return "N/A"

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

        # Button pressed handling
        if GPIO.input(BUTTON_PIN) == 0:  # pressed
            if button_press_start is None:
                button_press_start = time.time()
            elif time.time() - button_press_start >= LONG_PRESS:
                test_mode = not test_mode  # toggle test/live mode
                button_press_start = None
        else:
            button_press_start = None
            now = time.time()
            if now - last_press_time > DEBOUNCE:
                get_next_index(TEST_LABELS if test_mode else LIVE_LABELS)
                last_press_time = now

        # Update latest log file
        if not test_mode:
            candidate = find_latest_log()
            if candidate and candidate != latest_log_file:
                latest_log_file = candidate
                current_index = 0

        # Display values
        if test_mode:
            label = TEST_LABELS[current_index]
            value = TEST_VALUES[current_index]
            draw_oled(label, value, blink_indicator=True)
        else:
            # Cycle through live labels
            label = LIVE_LABELS[current_index]
            value = read_latest_value(label, latest_log_file) if latest_log_file else "N/A"
            draw_oled(label, value, blink_indicator=False)
            # Show GPS speed as a separate line if needed
            gps_value = read_gps_speed()
            draw_oled("GPS", gps_value, blink_indicator=False)

        time.sleep(0.1)

except KeyboardInterrupt:
    GPIO.cleanup()