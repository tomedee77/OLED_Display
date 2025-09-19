import time
import csv
import glob
import threading
from luma.core.interface.serial import i2c
from luma.oled.device import sh1106
from luma.core.render import canvas
from PIL import ImageFont
import RPi.GPIO as GPIO
import os

# --- OLED setup ---
serial = i2c(port=1, address=0x3C)
device = sh1106(serial)

small_font = ImageFont.load_default()
large_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)

# --- Button setup ---
BUTTON_PIN = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# --- Log directory ---
LOG_DIR = "/home/pi/TunerStudioProjects/MyProject/Logs/"
FIELDS = []        # Fields from CSV header
current_index = 0  # Which value to display
log_file = None    # Will be set to newest .msl file

# --- Test mode ---
TEST_MODE = False
test_values = {}

# --- Live log data storage ---
log_data = {}

# --- Button press to cycle fields ---
def button_callback(channel):
    global current_index
    current_index = (current_index + 1) % len(FIELDS)

GPIO.add_event_detect(BUTTON_PIN, GPIO.FALLING, callback=button_callback, bouncetime=200)

# --- Find latest .msl log file ---
def find_latest_log():
    files = glob.glob(os.path.join(LOG_DIR, "*.msl"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)

# --- Tail CSV log ---
def tail_log():
    global log_data, FIELDS, test_values
    while True:
        lf = find_latest_log()
        if lf != log_file:
            # New file found
            nonlocal log_file
            log_file = lf
            try:
                f = open(log_file)
                reader = csv.DictReader(f)
                FIELDS = reader.fieldnames
                test_values = {field: 0 for field in FIELDS}  # default test
                print(f"Tracking log: {log_file}")
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        continue
                    row = dict(zip(FIELDS, line.strip().split(',')))
                    log_data = row
            except Exception as e:
                print(f"Error opening log: {e}")
                time.sleep(1)
        else:
            time.sleep(1)

# --- Start tailing in background ---
threading.Thread(target=tail_log, daemon=True).start()

# --- Display loop ---
try:
    while True:
        if not FIELDS:
            time.sleep(0.2)
            continue

        field = FIELDS[current_index]
        value = test_values[field] if TEST_MODE else log_data.get(field, "N/A")

        with canvas(device) as draw:
            # Top line: label
            w, h = draw.textsize(field, font=small_font)
            draw.text(((device.width - w)//2, 0), field, font=small_font, fill=255)
            # Bottom line: value
            val_str = str(value)
            w, h = draw.textsize(val_str, font=large_font)
            draw.text(((device.width - w)//2, device.height//2), val_str, font=large_font, fill=255)

        time.sleep(0.2)

except KeyboardInterrupt:
    GPIO.cleanup()
