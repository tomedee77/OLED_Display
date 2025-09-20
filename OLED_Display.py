#!/usr/bin/env python3
import os
import glob
import time
import RPi.GPIO as GPIO
from luma.core.interface.serial import i2c
from luma.oled.device import sh1106
from luma.core.render import canvas
from PIL import ImageFont

# --- Paths ---
LOG_DIR = "/home/pi/TunerStudioProjects/YourProject/datalogs"

# --- OLED setup ---
serial = i2c(port=1, address=0x3C)
device = sh1106(serial)

# --- Fonts ---
font_small = ImageFont.load_default()
font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)

# --- Button setup ---
BUTTON_PIN = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# --- Values to show ---
labels = ["RPM", "TPS", "AFR", "CLT", "IAT"]
index = 0
test_mode = False
last_press_time = 0

# --- Globals for log parsing ---
log_header = []
log_columns = {}

def get_latest_log():
    """Return path to most recent .msl file."""
    files = glob.glob(os.path.join(LOG_DIR, "*.msl"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def parse_header(filepath):
    """Read the header line to map column names to indices."""
    global log_header, log_columns
    try:
        with open(filepath, "r", errors="ignore") as f:
            for line in f:
                if line.startswith("Time") or line.startswith("ts"):
                    log_header = line.strip().split("\t")
                    log_columns = {name: i for i, name in enumerate(log_header)}
                    break
    except Exception as e:
        print("Header parse error:", e)

def get_live_values():
    """Get latest values from the most recent log."""
    try:
        latest = get_latest_log()
        if not latest:
            return {lbl: "N/A" for lbl in labels}

        if not log_header:  # first time only
            parse_header(latest)

        with open(latest, "rb") as f:
            f.seek(-800, os.SEEK_END)
            lines = f.readlines()
            last_line = lines[-1].decode(errors="ignore").strip()

        parts = last_line.split("\t")

        values = {}
        for lbl in labels:
            if lbl in log_columns:
                values[lbl] = parts[log_columns[lbl]]
            else:
                values[lbl] = "N/A"

        return values
    except Exception:
        return {lbl: "N/A" for lbl in labels}

def draw_display(label, value, blink=False):
    """Draw text on OLED."""
    with canvas(device) as draw:
        # Top line label
        w, h = draw.textsize(label, font=font_small)
        draw.text(((device.width - w) // 2, 0), label, font=font_small, fill=255)

        # Bottom value
        w, h = draw.textsize(value, font=font_large)
        draw.text(((device.width - w) // 2, (device.height - h) // 2 + 6), value, font=font_large, fill=255)

        # Blinking T in test mode
        if blink:
            draw.text((device.width - 10, 0), "T", font=font_small, fill=255)

def get_button():
    """Poll button with debounce."""
    global last_press_time
    if GPIO.input(BUTTON_PIN) == GPIO.LOW:
        now = time.time()
        if now - last_press_time > 0.3:  # debounce 300ms
            last_press_time = now
            return True
    return False

# --- Main loop ---
blink_state = False
values = {}

try:
    while True:
        if get_button():
            # Short press cycles values
            index = (index + 1) % len(labels)

        if test_mode:
            # Fake values for debugging
            values = {
                "RPM": str(int(time.time()) % 7000),
                "TPS": str((int(time.time()) * 3) % 100),
                "AFR": "14.7",
                "CLT": "90",
                "IAT": "25"
            }
        else:
            values = get_live_values()

        blink_state = not blink_state if test_mode else False

        label = labels[index]
        value = values.get(label, "N/A")

        draw_display(label, value, blink=blink_state)

        time.sleep(0.5)

except KeyboardInterrupt:
    GPIO.cleanup()