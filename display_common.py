# display_common.py -- shared RGB matrix setup used by every program
# (flight_wall.py, bus_tracker.py, ...). Import from here instead of
# duplicating the panel init in each program.
#
# ============================================================
# WHERE TO CONFIGURE THINGS
# ============================================================
#   Display size / color depth ......... DISPLAY_WIDTH, DISPLAY_HEIGHT, BIT_DEPTH
#   Screen brightness (0.0-1.0) ........ BRIGHTNESS / BRIGHTNESS_DAY, BRIGHTNESS_NIGHT
#   Night dimming schedule hours ....... NIGHT_START_HOUR, NIGHT_END_HOUR
#   Display off schedule hours ......... OFF_START_HOUR, OFF_END_HOUR
# ============================================================

import board
import displayio
import framebufferio
import rgbmatrix

# --- Panel setup: 64x32, 2.5mm pitch, 1:16 scan (4 address lines) ---
# DISPLAY_WIDTH / DISPLAY_HEIGHT: change only if you swap to a different-size panel.
# BIT_DEPTH: color levels per channel = 2^BIT_DEPTH (e.g. 4 -> 16 levels/channel).
#   Higher = smoother/truer colors but more refresh work per frame.
DISPLAY_WIDTH = 64
DISPLAY_HEIGHT = 32
BIT_DEPTH = 4

# Screen brightness, 0.0 (off) to 1.0 (max).
# BRIGHTNESS is preserved as the daytime default.
BRIGHTNESS = 0.12
BRIGHTNESS_DAY = BRIGHTNESS
BRIGHTNESS_NIGHT = 0.04
NIGHT_START_HOUR = 22
NIGHT_END_HOUR = 7
OFF_START_HOUR = 0
OFF_END_HOUR = 6

WHITE = 0xFFFFFF
CHAR_W = 6  # pixel width of one terminalio.FONT character; used for centering text
ROW_Y = (6, 16, 26)  # pixel y-positions of the 3 text rows

_cached_display = None
_last_tick_mono = None


def init_matrix_display():
    """Create and return the FramebufferDisplay for the 64x32 matrix panel.
    Returns the cached display object on subsequent calls."""
    global _cached_display
    if _cached_display is not None:
        return _cached_display

    displayio.release_displays()

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
    _cached_display = display
    return display


def center_x(text, char_w=CHAR_W, display_width=DISPLAY_WIDTH):
    """Return the x pixel coordinate to center text horizontally on the display."""
    return max(0, (display_width - len(text) * char_w) // 2)


def brightness_for_hour(h):
    """Compute display brightness for a given local hour (0-23) based on configured schedule."""
    import time_common
    return time_common.brightness_for_hour(
        h,
        day=BRIGHTNESS_DAY,
        night=BRIGHTNESS_NIGHT,
        night_start=NIGHT_START_HOUR,
        night_end=NIGHT_END_HOUR,
        off_start=OFF_START_HOUR,
        off_end=OFF_END_HOUR,
    )


def tick():
    """Periodic hook called from app_switch.check().
    Runs at most once every 30 seconds:
    - computes local hour and adjusts display.brightness
    - checks hourly time resynchronization"""
    global _last_tick_mono
    import time
    now_mono = time.monotonic()
    if _last_tick_mono is not None and (now_mono - _last_tick_mono) < 30:
        return
    _last_tick_mono = now_mono

    # 1. Update brightness based on local hour
    try:
        import time_common
        local_unix = time_common.local_now()
        if local_unix is not None:
            local_hour = (local_unix % 86400) // 3600
            target_brightness = brightness_for_hour(local_hour)
        else:
            target_brightness = BRIGHTNESS_DAY

        disp = init_matrix_display()
        if disp.brightness != target_brightness:
            disp.brightness = target_brightness
    except Exception as e:
        print("Brightness tick error:", e)

    # 2. Lazy hourly time resync
    try:
        import time_common
        if time_common.needs_resync():
            import wifi
            import socketpool
            if wifi.radio.connected:
                pool = socketpool.SocketPool(wifi.radio)
                time_common.sync_ntp(pool)
    except Exception as e:
        print("Time resync tick error:", e)


def show_error(text):
    """Display a 3-line centered white error message on the cached display."""
    import terminalio
    from adafruit_display_text.label import Label

    disp = init_matrix_display()
    group = displayio.Group()

    if isinstance(text, str):
        lines = text.split("\n")
    else:
        lines = list(text)

    if len(lines) == 1:
        lines = ["ERROR", lines[0], ""]
    elif len(lines) == 2:
        lines = [lines[0], lines[1], ""]
    lines = lines[:3]

    for i, line in enumerate(lines):
        line_str = str(line)[:10]
        lbl = Label(terminalio.FONT, text=line_str, color=WHITE)
        lbl.x = center_x(line_str)
        lbl.y = ROW_Y[i]
        group.append(lbl)

    disp.root_group = group
