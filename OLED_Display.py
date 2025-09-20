import os
import time
import glob
import RPi.GPIO as GPIO
from luma.core.interface.serial import i2c
from luma.oled.device import sh1106
from luma.core.render import canvas
from PIL import ImageFont

# --- Setup OLED ---
serial = i2c(port=1, address=0x3C)
device = sh1106(serial)

font_small = ImageFont.load_default()
font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)

# --- Button setup ---
BUTTON_PIN = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# --- Dummy test values ---
test_data = [
    ("AFR", "14.7"),
    ("TPS", "0%"),
    ("CLT", "20°C"),
    ("IAT", "22°C"),
    ("RPM", "850"),
]
page_index = 0

# --- Helper: draw text centered ---
def draw_screen(label, value):
    with canvas(device) as draw:
        # Label (top, small, centered)
        w, h = draw.textsize(label, font=font_small)
        draw.text(((device.width - w) // 2, 0), label, font=font_small, fill=255)

        # Value (bottom, large, centered)
        w, h = draw.textsize(value, font=font_large)
        draw.text(((device.width - w) // 2, (device.height - h) // 2), value, font=font_large, fill=255)

# --- Detect latest log file ---
def get_latest_log():
    logs = glob.glob("/home/pi/TunerStudioProjects/**/datalogs/*.ml*", recursive=True)
    if logs:
        return max(logs, key=os.path.getctime)
    return None

# --- Read ECU log line ---
def read_log_line(log_file):
    try:
        with open(log_file, "rb") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline().decode(errors="ignore").strip()
                if not line:
                    time.sleep(0.2)
                    continue
                yield line.split(",")
    except FileNotFoundError:
        return

# --- Main loop ---
def main():
    global page_index
    log_file = get_latest_log()

    if not log_file:
        print("No log file found, starting in TEST MODE")
    else:
        print(f"Reading from log file: {log_file}")

    data_gen = read_log_line(log_file) if log_file else None

    while True:
        button_state = GPIO.input(BUTTON_PIN)
        if button_state == GPIO.LOW:
            page_index = (page_index + 1) % len(test_data)
            time.sleep(0.3)  # debounce

        if log_file and data_gen:
            # Here you’d parse actual ECU values if log format known
            label, value = test_data[page_index]  # placeholder until format sorted
        else:
            label, value = test_data[page_index]

        draw_screen(label, value)
        time.sleep(0.2)

try:
    main()
except KeyboardInterrupt:
    GPIO.cleanup()