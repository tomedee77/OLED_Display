#!/usr/bin/env python3
import os
import time
import glob
import subprocess
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

font_small = ImageFont.load_default(15)
try:
    font_large = ImageFont.truetype(
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 35
    )
except:
    font_large = ImageFont.load_default(35)

# ----------------------------
# CLEAR OLD LOGS ON STARTUP
# ----------------------------
for f in glob.glob(os.path.join(DATA_LOG_DIR, "*.ml*")):
    try:
        os.remove(f)
        print(f"Deleted old log: {f}")
    except Exception as e:
        print(f"Failed to delete {f}: {e}")

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


def ts_running():
    """Return True if TunerStudio Java process is running."""
    try:
        output = subprocess.check_output(["pgrep", "-f", "TunerStudio"], text=True)
        return bool(output.strip())
    except subprocess.CalledProcessError:
        return False


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

        # Total height of both lines
        total_height = label_height + value_height

        # Vertical centering
        y_offset = (OLED_HEIGHT - total_height) / 2

        # Draw label horizontally centered
        draw.text(
            ((OLED_WIDTH - label_width) / 2, y_offset),
            label,
            font=font_small,
            fill=255
        )

        # Draw value below label, horizontally centered
        draw.text(
            ((OLED_WIDTH - value_width) / 2, y_offset + label_height),
            value,
            font=font_large,
            fill=255
        )

        # Draw mode indicator (T/L/?) in top-left, blinking
        if indicator and blink:
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
                time.sleep(0.3)  # prevent bounce
        else:
            if button_held_time:
                if now - button_held_time > DEBOUNCE:
                    get_next_index(len(LIVE_LABELS if mode_live else TEST_LABELS))
                button_held_time = None

        # Toggle blink every 0.5 sec
        if time.time() - blink_timer > 0.5:
            blink = not blink
            blink_timer = time.time()

        # Get data depending on mode
        if mode_live:
            values = read_latest_values()
            if not values:
                label = "NO LOG"
                value = "--"
            else:
                label = LIVE_LABELS[current_index]
                value = values.get(label, "N/A")
            indicator = "L" if ts_running() else "?"
        else:
            label = TEST_LABELS[current_index]
            value = TEST_VALUES[current_index]
            indicator = "T"

        draw_oled(label, str(value), indicator)
        time.sleep(0.05)

except KeyboardInterrupt:
    GPIO.cleanup()
