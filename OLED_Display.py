from luma.core.interface.serial import i2c
from luma.oled.device import sh1106
from luma.core.render import canvas

serial = i2c(port=1, address=0x3C)
device = sh1106(serial)

from PIL import ImageFont
font = ImageFont.load_default()

with canvas(device) as draw:
    draw.text((0,0),"OLED OK", font=font, fill=255)