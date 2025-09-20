import time
import RPi.GPIO as GPIO
from luma.core.interface.serial import i2c
from luma.oled.device import sh1106
from luma.core.render import canvas
from PIL import ImageFont

# OLED setup
serial = i2c(port=1, address=0x3C)
device = sh1106(serial)
font_small = ImageFont.load_default()
font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)

# Button setup
BUTTON_PIN = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

FIELDS = ["RPM", "TPS", "AFR", "CLT", "IAT"]
test_values = {
    "RPM": [900, 1500, 2500, 3000],
    "TPS": [0, 25, 50, 75, 100],
    "AFR": [14.7, 12.5, 13.2],
    "CLT": [20, 80, 90],
    "IAT": [18, 30, 40]
}

page = 0
test_index = {f:0 for f in FIELDS}
last_button_state = GPIO.input(BUTTON_PIN)

while True:
    # Non-blocking button check
    current_state = GPIO.input(BUTTON_PIN)
    if last_button_state == GPIO.HIGH and current_state == GPIO.LOW:
        page = (page + 1) % len(FIELDS)
    last_button_state = current_state

    # Pick test value
    label = FIELDS[page]
    vals = test_values[label]
    value = vals[test_index[label]]
    test_index[label] = (test_index[label] + 1) % len(vals)

    # Draw OLED each loop
    with canvas(device) as draw:
        # Top line
        w, h = draw.textsize(label, font=font_small)
        draw.text(((device.width - w)//2, 0), label + " [T]", font=font_small, fill=255)
        # Bottom line
        val_str = str(value)
        w, h = draw.textsize(val_str, font=font_large)
        draw.text(((device.width - w)//2, (device.height - h)//2), val_str, font=font_large, fill=255)

    # Short delay so loop runs smoothly
    time.sleep(0.2)