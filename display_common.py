# display_common.py -- shared RGB matrix setup used by every program
# (flight_wall.py, bus_tracker.py, ...). Import from here instead of
# duplicating the panel init in each program.

import board
import displayio
import framebufferio
import rgbmatrix

displayio.release_displays()

# --- Panel setup: 64x32, 2.5mm pitch, 1:16 scan (4 address lines) ---
# DISPLAY_WIDTH / DISPLAY_HEIGHT: change only if you swap to a different-size panel.
# BIT_DEPTH: color levels per channel = 2^BIT_DEPTH (e.g. 4 -> 16 levels/channel).
#   Higher = smoother/truer colors but more refresh work per frame.
DISPLAY_WIDTH = 64
DISPLAY_HEIGHT = 32
BIT_DEPTH = 4

# Screen brightness, 0.0 (off) to 1.0 (max). This is the ONLY place brightness
# is set -- every program calls init_matrix_display() with no arguments, so
# there's no per-file override to accidentally shadow this value.
BRIGHTNESS = 0.12

WHITE = 0xFFFFFF
CHAR_W = 6  # pixel width of one terminalio.FONT character; used for centering text


def init_matrix_display():
    """Create and return the FramebufferDisplay for the 64x32 matrix panel."""
    matrix = rgbmatrix.RGBMatrix(
        width=DISPLAY_WIDTH,
        height=DISPLAY_HEIGHT,
        bit_depth=BIT_DEPTH,
        # G and B swapped on purpose: every reported color mismatch (UAL
        # blue rendering cyan then pastel green, AAL orange rendering
        # magenta, UPS brown rendering pink) matches exactly what you'd see
        # if this specific panel's green/blue data lines are physically
        # swapped relative to the "standard" HUB75 assumption. Swapping the
        # pin assignment here corrects it once, instead of hand-compensating
        # every color value.
        rgb_pins=[
            board.MTX_R1, board.MTX_B1, board.MTX_G1,
            board.MTX_R2, board.MTX_B2, board.MTX_G2,
        ],
        addr_pins=[
            board.MTX_ADDRA, board.MTX_ADDRB,
            board.MTX_ADDRC, board.MTX_ADDRD,
        ],
        clock_pin=board.MTX_CLK,
        latch_pin=board.MTX_LAT,
        output_enable_pin=board.MTX_OE,
        doublebuffer=True,
    )
    display = framebufferio.FramebufferDisplay(matrix, auto_refresh=True)
    display.brightness = BRIGHTNESS
    return display


def center_x(text, char_w=CHAR_W, display_width=DISPLAY_WIDTH):
    return max(0, (display_width - len(text) * char_w) // 2)
