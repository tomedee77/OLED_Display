import os
import time
import glob
import RPi.GPIO as GPIO
from luma.core.interface.serial import i2c
from luma.oled.device import sh1106
from luma.core.render import canvas
from PIL import ImageFont

# --- OLED setup ---
serial = i2c(port=1, address=0x3C)
device = sh1106(serial)

# --- Fonts ---
font_small = ImageFont.load_default()
font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)

# --- Button setup ---
BUTTON_PIN = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# --- Labels to show ---
FIELDS = ["RPM", "TPS", "AFR", "CLT", "IAT"]
test_values = {
    "RPM": [900, 1500, 2500, 3000],
    "TPS": [0, 25, 50, 75, 100],
    "AFR": [14.7, 12.5, 13.2],
    "CLT": [20, 80, 90],
    "IAT": [18, 30, 40]
}

# --- Helper to find latest log file ---
def get_latest_log():
    files = glob.glob("/home/pi/TunerStudioProjects/*/datalogs/*.ml*")
    if not files:
        return None
    return max(files, key=os.path.getctime)

# --- Display helper ---
def show(label, value, test_mode=False):
    with canvas(device) as draw:
        top = f"{label} {'[T]' if test_mode else ''}"
        draw.text((64, 0), top, font=font_small, anchor="mm", align="center")
        draw.text((64, 20), str(value), font=font_large, anchor="mm", align="center")

# --- Main loop ---
page = 0
test_mode = False
test_index = {f: 0 for f in FIELDS}

while True:
    # Button polling
    if GPIO.input(BUTTON_PIN) == GPIO.LOW:
        page = (page + 1) % len(FIELDS)
        time.sleep(0.3)  # debounce

    # Try to get ECU/log file
    logfile = get_latest_log()
    if logfile and os.path.getsize(logfile) > 0:
        test_mode = False
        # For now just show "Live" placeholder until parsing added
        label = FIELDS[page]
        value = "Live..."
    else:
        test_mode = True
        label = FIELDS[page]
        vals = test_values[label]
        value = vals[test_index[label]]
        test_index[label] = (test_index[label] + 1) % len(vals)

    # Update OLED
    show(label, value, test_mode)

    time.sleep(1)