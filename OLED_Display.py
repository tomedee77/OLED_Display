#!/usr/bin/env python3
import time
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
BUTTON_PIN = 17  # GPIO pin for momentary button
DEBOUNCE = 0.2   # debounce time in seconds
LONG_PRESS = 1.5 # seconds to trigger mode switch

# Labels and test values
TEST_LABELS = ["RPM", "TPS", "AFR", "Coolant", "IAT"]
TEST_VALUES = ["1000", "12.5%", "14.7", "90°C", "25°C"]

# Fonts
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
test_mode = True
last_press_time = 0
press_start = None
blink = True
blink_timer = time.time()
mode_message = None
mode_message_timer = 0

# ----------------------------
# HELPER FUNCTIONS
# ----------------------------
def get_next_index():
    global current_index
    current_index = (current_index + 1) % len(TEST_LABELS)
    return current_index

def draw_centered(draw, text, font, y):
    bbox = font.getbbox(text)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (OLED_WIDTH - w) // 2
    draw.text((x, y), text, font=font, fill=255)
    return h

def check_tunerstudio():
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "tunerstudio.service"],
            capture_output=True, text=True
        )
        return result.stdout.strip() == "active"
    except Exception:
        return False

def draw_oled(label, value, blink_indicator=False, ts_running=False, mode_msg=None):
    global device, blink
    with canvas(device) as draw:
        if mode_msg:  # temporary mode message
            draw_centered(draw, mode_msg, font_large, (OLED_HEIGHT - 16) // 2)
            return

        # Label (top, centered)
        label_height = draw_centered(draw, label, font_small, 0)

        # Value (centered below label)
        bbox = font_large.getbbox(value)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (OLED_WIDTH - w) // 2
        y = (OLED_HEIGHT - h) // 2 + (label_height // 2)
        draw.text((x, y), value, font=font_large, fill=255)

        # Optional blink indicator
        if blink_indicator and blink:
            draw.text((0, 0), "T", font=font_small, fill=255)

        # TunerStudio running indicator
        if ts_running:
            ts_text = "TS"
            bbox = font_small.getbbox(ts_text)
            w = bbox[2] - bbox[0]
            draw.text((OLED_WIDTH - w, 0), ts_text, font=font_small, fill=255)

# ----------------------------
# MAIN LOOP
# ----------------------------
try:
    while True:
        now = time.time()

        # Button logic
        if GPIO.input(BUTTON_PIN) == 0:  # button pressed
            if press_start is None:
                press_start = now
            elif now - press_start >= LONG_PRESS:
                test_mode = not test_mode
                mode_message = "MODE: TEST" if test_mode else "MODE: LIVE"
                mode_message_timer = now
                press_start = None
        else:  # button released
            if press_start is not None:
                if now - press_start < LONG_PRESS and now - last_press_time > DEBOUNCE:
                    get_next_index()  # short press
                    last_press_time = now
                press_start = None

        # Blink toggle
        if now - blink_timer > 0.5:
            blink = not blink
            blink_timer = now

        # Check TunerStudio status every loop
        ts_running = check_tunerstudio()

        # If showing mode message, clear after 1s
        if mode_message and now - mode_message_timer > 1.0:
            mode_message = None

        # Display
        label = TEST_LABELS[current_index]
        value = TEST_VALUES[current_index]
        draw_oled(label, value, blink_indicator=test_mode,
                  ts_running=ts_running, mode_msg=mode_message)

        time.sleep(0.05)

except KeyboardInterrupt:
    GPIO.cleanup()