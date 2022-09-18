print("Starting")

import board

from kmk.kmk_keyboard import KMKKeyboard
from kmk.keys import KC
from kmk.scanners import DiodeOrientation
from kmk.scanners.encoder import RotaryioEncoder
from kmk.extensions.media_keys import MediaKeys
from kmk.extensions.statusled import statusLED
from kmk.modules.layers import Layers
from kmk.modules.encoder import EncoderHandler
#from kmk.extensions.rgb import RGB

keyboard = KMKKeyboard()
encoder_handler = EncoderHandler()
statusLED = statusLED(led_pins=[board.SCK, board.MISO, board.D10])

#rgb_ext = RGB(pixel_pin=board.D2, num_pixels=16)
#keyboard.extensions.append(rgb_ext)

keyboard.modules = [encoder_handler]
keyboard.modules.append(Layers())
keyboard.extensions.append(statusLED)
keyboard.extensions.append(MediaKeys())
keyboard.col_pins = (board.D5,board.D6,board.D7,board.D8,board.D9)
keyboard.row_pins = (board.A3,board.A2,board.A1,board.A0)    
keyboard.diode_orientation = DiodeOrientation.COL2ROW


class MyKeyboard(KMKKeyboard):
    def __init__(self):
        # create and register the scanner
        self.matrix = RotaryioEncoder(
            pin_a=board.MOSI,
            pin_b=board.D4,
            # optional
            divisor=2,
        )


# Layer Keys
MOMENTARY = KC.MO(1)
LAYER_TAP = KC.LT(1, KC.END, prefer_hold=True, tap_interrupted=False, tap_time=250) # any tap longer than 250ms will be interpreted as a hold
# 
_______ = KC.TRNS
   
keyboard.keymap = [
# Base Layer    
    [
        KC.NO,      KC.P7,   KC.P8,   KC.P9,   KC.A,
        KC.NO,      KC.P4,   KC.P5,   KC.P6,   KC.B,
        KC.NO,      KC.P1,   KC.P2,   KC.P3,   KC.C,
        KC.MUTE,    KC.E,    KC.F,    KC.G,    LAYER_TAP,
        ],
# Layer 1
    [
        KC.NO,      KC.PGUP,   KC.UP,   KC.PGDN,    KC.A,
        KC.NO,      KC.LEFT,   KC.DOWN, KC.RIGHT,   KC.B,
        KC.NO,      KC.P1,     KC.P2,   KC.P3,      KC.C,
        KC.MUTE,    KC.E,      KC.F,    KC.G,       _______,
    ]
]

# Rotary Encoder (1 encoder / 1 definition per layer)
encoder_handler.map = ( ((KC.VOLU, KC.VOLD,),), ) # Standard                        


if __name__ == '__main__':
    keyboard.go()