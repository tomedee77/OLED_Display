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
BUTTON_PIN = 17
DEBOUNCE = 0.2
LONG_PRESS = 2
LOG_DIR = "/home/tomedee77/TunerStudioProjects/VWRX/DataLogs"
GPS_PORT = "/dev/gps0"
GPS_BAUD = 9600

LIVE_LABELS = ["GPS", "MAP", "AFR", "MAT", "CLT"]

font_small = ImageFont.load_default()
try:
    font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
except:
    font_large = ImageFont.load_default()

# ----------------------------
# SETUP
# ----------------------------
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

serial_oled = i2c(port=1, address=0x3C)
device = sh1106(serial_oled)

current_index = 0  # GPS
button_down_time = None
last_press_time = 0
blink = True
blink_timer = time.time()

gps_fix = False
latest_log_file = None
log_col_map = {}
log_file_handle = None

# Setup GPS
try:
    gps_serial = serial.Serial(GPS_PORT, GPS_BAUD, timeout=1)
except Exception:
    gps_serial = None

# ----------------------------
# HELPERS
# ----------------------------
def cleanup_old_logs():
    today = datetime.now().date()
    for f in glob.glob(os.path.join(LOG_DIR, "*.msl")) + glob.glob(os.path.join(LOG_DIR, "*.mlg")):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(f)).date()
            if mtime < today:
                os.remove(f)
        except Exception:
            pass

def find_latest_log():
    files = glob.glob(os.path.join(LOG_DIR, "*.msl")) + glob.glob(os.path.join(LOG_DIR, "*.mlg"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def parse_log_header(file_path):
    col_map = {}
    data_start_idx = 0
    try:
        with open(file_path, "r") as f:
            lines = [line.strip() for line in f if line.strip()]
            # first line that looks numeric
            for i, line in enumerate(lines):
                parts = line.split("\t")
                if all(p.replace(".", "").isdigit() or p=="0" for p in parts if p):
                    data_start_idx = i
                    break
            headers = []
            for line in lines[:data_start_idx]:
                headers.extend(line.split("\t"))
            for idx, label in enumerate(headers):
                col_map[label] = idx
    except Exception:
        pass
    return col_map, data_start_idx

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

def draw_oled(label, value, gps_dot=False):
    global device, blink
    with canvas(device) as draw:
        if label == "GPS":
            bbox = font_large.getbbox(value)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
            draw.text(((OLED_WIDTH-w)/2, (OLED_HEIGHT-h)/2), value, font=font_large, fill=255)
        else:
            bbox = font_small.getbbox(label)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
            draw.text(((OLED_WIDTH-w)/2, 0), label, font=font_small, fill=255)
            bbox = font_large.getbbox(value)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
            draw.text(((OLED_WIDTH-w)/2, 16), value, font=font_large, fill=255)
        if gps_dot and blink:
            draw.text((0,0),"•", font=font_small, fill=255)

def get_next_index():
    global current_index
    if current_index == 0:
        current_index = 1
    else:
        current_index += 1
        if current_index >= len(LIVE_LABELS):
            current_index = 0
    return current_index

def read_latest_value(label):
    """Read last line from log file tail"""
    global log_file_handle, log_col_map
    if not log_file_handle or not log_col_map or label not in log_col_map:
        return "N/A"
    try:
        # read new lines
        while True:
            pos = log_file_handle.tell()
            line = log_file_handle.readline()
            if not line:
                log_file_handle.seek(pos)
                break
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            idx = log_col_map.get(label)
            if idx is None or idx >= len(parts):
                continue
            value = parts[idx]
        # return last parsed value
        return value
    except Exception:
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
        if button_state == 0:
            if button_down_time is None:
                button_down_time = now
            elif now - button_down_time >= LONG_PRESS:
                current_index = 0  # long press returns to GPS
        else:
            if button_down_time:
                if now - last_press_time > DEBOUNCE and now - button_down_time < LONG_PRESS:
                    get_next_index()
                    last_press_time = now
                button_down_time = None

        # Open log if needed (skip GPS index 0)
        if current_index != 0:
            candidate = find_latest_log()
            if candidate != latest_log_file:
                latest_log_file = candidate
                log_col_map, data_start_idx = parse_log_header(latest_log_file)
                try:
                    if log_file_handle:
                        log_file_handle.close()
                    log_file_handle = open(latest_log_file, "r")
                    # skip header lines
                    for _ in range(data_start_idx):
                        log_file_handle.readline()
                except Exception:
                    log_file_handle = None

        # Determine value
        label = LIVE_LABELS[current_index]
        if label == "GPS":
            value = read_gps_speed()
        else:
            value = read_latest_value(label)

        draw_oled(label, value, gps_dot=gps_fix)
        time.sleep(0.1)

except KeyboardInterrupt:
    GPIO.cleanup()