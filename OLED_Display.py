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

LIVE_LABELS = ["GPS", "MAP", "AFR", "CLT", "MAT"]

font_small = ImageFont.load_default(20)
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
button_down_time = None
last_press_time = 0
blink = True
blink_timer = time.time()
latest_log_file = None
log_file_handle = None
log_positions = {}
gps_fix = False

# GPS setup
try:
    gps_serial = serial.Serial(GPS_PORT, GPS_BAUD, timeout=1)
except Exception:
    gps_serial = None

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

def draw_oled(label, value):
    global device, blink
    with canvas(device) as draw:
        if label == "GPS":
            bbox = font_large.getbbox(value)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((OLED_WIDTH - w)/2, (OLED_HEIGHT - h)/2), value, font=font_large, fill=255)
            if gps_fix:
                draw.text((0, 0), "•", font=font_small, fill=255)
        else:
            bbox = font_small.getbbox(label)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((OLED_WIDTH - w)/2, 0), label, font=font_small, fill=255)

            bbox = font_large.getbbox(value)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((OLED_WIDTH - w)/2, 16), value, font=font_large, fill=255)

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

def tail_log(label):
    """Return latest value for a label using file tailing"""
    global log_file_handle, log_positions

    if not latest_log_file:
        return "N/A"

    try:
        # open log if not already
        if not log_file_handle or log_file_handle.name != latest_log_file:
            if log_file_handle:
                log_file_handle.close()
            log_file_handle = open(latest_log_file, "r")
            log_positions.clear()
            # read header to locate columns
            lines = [line.strip() for line in log_file_handle if line.strip()]
            header_idx = None
            for i, line in enumerate(lines):
                parts = line.split("\t")
                if label in parts:
                    header_idx = i
                    log_positions['col'] = parts.index(label)
                    log_positions['pos'] = i + 1  # start after header
                    break
            if header_idx is None:
                return "N/A"
        # seek to last read line
        log_file_handle.seek(0)
        lines = [line.strip() for line in log_file_handle if line.strip()]
        if len(lines) <= log_positions['pos']:
            return "N/A"
        last_data_line = lines[-1]
        parts = last_data_line.split("\t")
        col = log_positions.get('col', 0)
        if len(parts) > col:
            return parts[col]
        return "N/A"
    except Exception:
        return "N/A"

# ----------------------------
# MAIN LOOP
# ----------------------------
cleanup_old_logs()

try:
    while True:
        # Blink
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
                current_index = 0  # return to GPS
        else:
            if button_down_time:
                if now - last_press_time > DEBOUNCE and now - button_down_time < LONG_PRESS:
                    get_next_index()
                    last_press_time = now
                button_down_time = None

        # Update latest log
        candidate = find_latest_log()
        if candidate and candidate != latest_log_file:
            latest_log_file = candidate
            if log_file_handle:
                log_file_handle.close()
                log_file_handle = None

        # Determine display value
        label = LIVE_LABELS[current_index]
        if label == "GPS":
            value = read_gps_speed()
        else:
            value = tail_log(label)

        draw_oled(label, value)
        time.sleep(0.1)

except KeyboardInterrupt:
    if log_file_handle:
        log_file_handle.close()
    GPIO.cleanup()