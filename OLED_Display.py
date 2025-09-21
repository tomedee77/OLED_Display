#!/usr/bin/env python3
import os
import time
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
LONG_PRESS = 1.5
DATA_LOG_DIR = "/home/tomedee77/TunerStudioProjects/VWRX/DataLogs"

LIVE_LABELS = ["MAP", "AFR", "CLT", "MAT"]
TEST_LABELS = ["RPM", "TPS", "AFR", "Coolant", "IAT"]
TEST_VALUES = ["1000", "12.5%", "14.7", "90°C", "25°C"]

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

serial = i2c(port=1, address=0x3C)
device = sh1106(serial)

current_index = 0
last_press_time = 0
button_held_time = None
mode_live = True  # Boot straight into live mode
blink = True
blink_timer = time.time()


# ----------------------------
# HELPERS
# ----------------------------
def get_newest_log():
    """Return newest datalog file path or None."""
    files = glob.glob(os.path.join(DATA_LOG_DIR, "*.ml*"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def read_latest_values():
    """Read last line of newest datalog and return dict of values."""
    logfile = get_newest_log()
    if not logfile:
        return None

    try:
        with open(logfile, "r") as f:
            lines = f.readlines()
            if len(lines) < 2:
                return None
            header = lines[0].strip().split("\t")
            last = lines[-1].strip().split("\t")
            data = dict(zip(header, last))
            return {
                "MAP": data.get("MAP", "N/A"),
                "AFR": data.get("AFR", "N/A"),
                "CLT": data.get("CLT", "N/A"),
                "MAT": data.get("MAT", "N/A"),
            }
    except Exception:
        return None


def draw_oled(label, value, indicator=""):
    with canvas(device) as draw:
        # Label top line
        bbox = font_small.getbbox(label)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((OLED_WIDTH - w) / 2, 0), label, font=font_small, fill=255)

        # Value bottom line
        bbox = font_large.getbbox(value)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((OLED_WIDTH - w) / 2, 16), value, font=font_large, fill=255)

        # Mode indicator (T or L) with blink
        if indicator:
            if blink:
                draw.text((0, 0), indicator, font=font_small, fill=255)


def get_next_index(limit):
    global current_index
    current_index = (current_index + 1) % limit
    return current_index


# ----------------------------
# MAIN LOOP
# ----------------------------
try:
    while True:
        now = time.time()
        pressed = GPIO.input(BUTTON_PIN) == 0

        # Handle button press
        if pressed:
            if button_held_time is None:
                button_held_time = now
            elif now - button_held_time > LONG_PRESS:
                mode_live = not mode_live
                button_held_time = None
                time.sleep(0.3)
        else:
            if button_held_time:
                if now - button_held_time > DEBOUNCE:
                    get_next_index(len(LIVE_LABELS if mode_live else TEST_LABELS))
                button_held_time = None

        # Toggle blink
        if time.time() - blink_timer > 0.5:
            blink = not blink
            blink_timer = time.time()

        # Get data depending on mode
        if mode_live:
            values = read_latest_values()
            if not values:  # fallback
                label = "NO LOG"
                value = "--"
            else:
                label = LIVE_LABELS[current_index]
                value = values.get(label, "N/A")
            indicator = "L"
        else:
            label = TEST_LABELS[current_index]
            value = TEST_VALUES[current_index]
            indicator = "T"

        draw_oled(label, str(value), indicator)
        time.sleep(0.05)

except KeyboardInterrupt:
    GPIO.cleanup()