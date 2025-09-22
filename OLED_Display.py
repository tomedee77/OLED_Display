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
DEBOUNCE = 0.2        # seconds
LONG_PRESS = 2        # seconds to return to GPS
LOG_DIR = "/home/tomedee77/TunerStudioProjects/VWRX/DataLogs"
GPS_PORT = "/dev/gps0"
GPS_BAUD = 9600

# Labels for live ECU logs
LIVE_LABELS = ["MAP", "AFR", "MAT", "CLT"]

# Fonts
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

current_index = 0
showing_gps = True
button_down_time = None
last_press_time = 0
blink = True
blink_timer = time.time()
latest_log_file = None
log_file_handle = None
log_col_map = {}

# Setup GPS
try:
    gps_serial = serial.Serial(GPS_PORT, GPS_BAUD, timeout=1)
except Exception:
    gps_serial = None

gps_fix = False

# ----------------------------
# FUNCTIONS
# ----------------------------
def draw_oled(label, value):
    global device, blink, gps_fix
    with canvas(device) as draw:
        if label == "GPS":
            bbox = font_large.getbbox(value)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
            draw.text(((OLED_WIDTH - w)/2, (OLED_HEIGHT - h)/2), value, font=font_large, fill=255)
            if gps_fix and blink:
                draw.text((0,0),"•",font=font_small,fill=255)
        else:
            bbox = font_small.getbbox(label)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
            draw.text(((OLED_WIDTH - w)/2, 0), label, font=font_small, fill=255)
            bbox = font_large.getbbox(value)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
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
                mph = float(msg.spd_over_grnd)*1.15078
                gps_fix = True
                return f"{mph:.1f}"
    except Exception:
        pass
    gps_fix = False
    return "0.0"

def cleanup_old_logs():
    today = datetime.now().date()
    for f in glob.glob(os.path.join(LOG_DIR,"*.mlg")) + glob.glob(os.path.join(LOG_DIR,"*.msl")):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(f)).date()
            if mtime < today:
                os.remove(f)
        except:
            pass

def find_latest_log():
    files = glob.glob(os.path.join(LOG_DIR,"*.mlg")) + glob.glob(os.path.join(LOG_DIR,"*.msl"))
    if not files:
        return None
    return max(files,key=os.path.getmtime)

def parse_log_header(file_path):
    """Return col_map and line index to start reading numeric data"""
    col_map = {}
    start_line = 0
    try:
        with open(file_path,"r") as f:
            lines = [l.strip() for l in f if l.strip()]
            for i,line in enumerate(lines):
                parts = line.split("\t")
                try:
                    float(parts[0])
                    start_line = i
                    break
                except ValueError:
                    continue
            header_line_idx = max(0,start_line-1)
            headers = lines[header_line_idx].split("\t")
            for idx,label in enumerate(headers):
                col_map[label.strip()] = idx
    except:
        pass
    return col_map,start_line

def read_latest_log_value(label):
    """Return last numeric value for label from log tail"""
    global log_file_handle, log_col_map
    if not log_file_handle or label not in log_col_map:
        return "N/A"
    # read last line
    try:
        pos = log_file_handle.tell()
        log_file_handle.seek(0,os.SEEK_END)
        while True:
            log_file_handle.seek(pos)
            line = log_file_handle.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if label in log_col_map and log_col_map[label]<len(parts):
                value = parts[log_col_map[label]]
        return value
    except:
        return "N/A"

# ----------------------------
# MAIN
# ----------------------------
cleanup_old_logs()
latest_log_file = find_latest_log()
if latest_log_file:
    log_col_map, start_line = parse_log_header(latest_log_file)
    log_file_handle = open(latest_log_file,"r")
    # move to end for tailing
    for _ in range(start_line):
        log_file_handle.readline()

try:
    while True:
        # blink toggle
        if time.time()-blink_timer>0.5:
            blink = not blink
            blink_timer=time.time()

        # button polling
        button_state = GPIO.input(BUTTON_PIN)
        now = time.time()
        if button_state == 0:
            if button_down_time is None:
                button_down_time = now
            elif not showing_gps and now - button_down_time >= LONG_PRESS:
                showing_gps = True
        else:
            if button_down_time:
                if now - last_press_time > DEBOUNCE and now - button_down_time < LONG_PRESS:
                    if showing_gps:
                        # do nothing, already on GPS
                        pass
                    else:
                        current_index = (current_index+1)%len(LIVE_LABELS)
                last_press_time = now
                button_down_time=None

        # update latest log file if needed
        candidate = find_latest_log()
        if candidate != latest_log_file:
            latest_log_file = candidate
            log_col_map,start_line = parse_log_header(latest_log_file)
            if log_file_handle:
                log_file_handle.close()
            log_file_handle = open(latest_log_file,"r")
            for _ in range(start_line):
                log_file_handle.readline()

        # pick value to display
        if showing_gps:
            label="GPS"
            value=read_gps_speed()
        else:
            label = LIVE_LABELS[current_index]
            value = read_latest_log_value(label)

        draw_oled(label,value)
        time.sleep(0.1)

except KeyboardInterrupt:
    GPIO.cleanup()
    if log_file_handle:
        log_file_handle.close()