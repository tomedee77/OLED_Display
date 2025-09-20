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
font = ImageFont.load_default()

# --- GPIO setup ---
BUTTON_PIN = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# --- Page handling ---
pages = ["RPM", "MAP", "CLT", "TPS"]
page_index = 0
last_button_state = GPIO.input(BUTTON_PIN)
last_debounce_time = 0
debounce_delay = 0.2  # seconds

# --- Find latest log file ---
def get_latest_log():
    files = glob.glob("/root/TunerStudioProjects/**/*.msl", recursive=True)
    if not files:
        files = glob.glob("/root/TunerStudioProjects/**/*.mlg", recursive=True)
    if not files:
        return None
    return max(files, key=os.path.getctime)

# --- Read last line from log ---
def read_latest_value(log_file, field="RPM"):
    try:
        with open(log_file, "r") as f:
            lines = f.readlines()
            if len(lines) < 2:
                return "No data"
            header = lines[0].strip().split("\t")
            values = lines[-1].strip().split("\t")
            if field in header:
                idx = header.index(field)
                return values[idx]
            else:
                return "Field?"
    except Exception as e:
        return f"Err: {e}"

# --- Main loop ---
try:
    while True:
        # Poll button
        button_state = GPIO.input(BUTTON_PIN)
        if button_state == GPIO.LOW and last_button_state == GPIO.HIGH:
            if (time.time() - last_debounce_time) > debounce_delay:
                page_index = (page_index + 1) % len(pages)
                last_debounce_time = time.time()
        last_button_state = button_state

        # Find latest log
        log_file = get_latest_log()

        # Read value
        if log_file:
            field = pages[page_index]
            value = read_latest_value(log_file, field)
            text = f"{field}: {value}"
        else:
            text = "No log file"

        # Update OLED
        with canvas(device) as draw:
            draw.text((0, 0), "ECU Monitor", font=font, fill=255)
            draw.text((0, 16), text, font=font, fill=255)

        time.sleep(0.2)

except KeyboardInterrupt:
    GPIO.cleanup()