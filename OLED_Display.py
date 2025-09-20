#!/usr/bin/env python3
import time
import os
import glob
from luma.core.interface.serial import i2c
from luma.oled.device import sh1106
from luma.core.render import canvas
from PIL import ImageFont

# ----------------------------
# CONFIG
# ----------------------------
OLED_WIDTH = 128
OLED_HEIGHT = 32
BUTTON_PIN = 17  # GPIO pin for button
DEBOUNCE = 0.2   # button debounce time (seconds)

# Labels and test values
TEST_LABELS = ["RPM", "TPS", "AFR", "Coolant", "IAT"]
TEST_VALUES = ["1000", "12.5%", "14.7", "90°C", "25°C"]

# ----------------------------
# SETUP
# ----------------------------
import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

serial = i2c(port=1, address=0x3C)
device = sh1106(serial)

font_small = ImageFont.load_default()
font_large = ImageFont.load_default()  # can replace with truetype if desired

current_index = 0
test_mode = True
last_press_time = 0
blink = True
blink_timer = time.time()

# ----------------------------
# HELPER FUNCTIONS
# ----------------------------
def get_next_index():
    global current_index
    current_index += 1
    if current_index >= len(TEST_LABELS):
        current_index = 0
    return current_index

def draw_oled(label, value, blink_indicator=False):
    global device
    with canvas(device) as draw:
        # Top line: label
        w, h = draw.textsize(label, font=font_small)
        draw.text(((OLED_WIDTH - w) / 2, 0), label, font=font_small, fill=255)
        # Bottom line: value
        w, h = draw.textsize(value, font=font_large)
        draw.text(((OLED_WIDTH - w) / 2, 16), value, font=font_large, fill=255)
        # Optional blink T in top-left
        if blink_indicator and blink:
            draw.text((0, 0), "T", font=font_small, fill=255)

# ----------------------------
# MAIN LOOP
# ----------------------------
try:
    while True:
        # Button polling
        if GPIO.input(BUTTON_PIN) == 0:  # pressed
            now = time.time()
            if now - last_press_time > DEBOUNCE:
                get_next_index()
                last_press_time = now

        # Toggle blink every 0.5 sec
        if time.time() - blink_timer > 0.5:
            blink = not blink
            blink_timer = time.time()

        # Display
        label = TEST_LABELS[current_index]
        value = TEST_VALUES[current_index]
        draw_oled(label, value, blink_indicator=test_mode)

        time.sleep(0.05)

except KeyboardInterrupt:
    GPIO.cleanup()