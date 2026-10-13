# app_switch.py -- lets any program hand off to the next/previous one in PROGRAMS
# when the board's UP or DOWN button is pressed. UP moves forward in rotation (+1),
# DOWN moves backward (-1). Switching happens in-memory without rebooting the board.
#
# Buttons are managed once via keypad.Keys at module load time so taps during
# network calls or sleeps are queued and never missed, and pins are never locked.
# Raising SwitchRequested(BaseException) propagates directly through app loops
# back to code.py runner.
#
# ============================================================
# WHERE TO CONFIGURE THINGS
# ============================================================
#   Active programs in rotation ........ PROGRAMS list below
#   Auto-rotate timeout (0 to disable) . AUTO_ROTATE_SECONDS (default 0)
# ============================================================

import board
import keypad
import time
import display_common

# Programs active in rotation. Add each file only when its implementation exists.
PROGRAMS = ("flight_wall.py", "bus_tracker.py")
STATE_FILE = "/program_state.txt"

# Auto-rotate timer: seconds before auto-cycling to next app. 0 = disabled.
# When enabled, button press resets the timer. Apps can set hold_rotation = True.
AUTO_ROTATE_SECONDS = 0
hold_rotation = False

# Background keypad scanner initialized once at module level.
# Key 0 = BUTTON_UP (+1 / next app)
# Key 1 = BUTTON_DOWN (-1 / previous app)
# value_when_pressed=False, pull=True matches active-low buttons with internal pull-up.
_keys = keypad.Keys((board.BUTTON_UP, board.BUTTON_DOWN), value_when_pressed=False, pull=True)
_event = keypad.Event()


class SwitchRequested(BaseException):
    """Raised when user requests switching apps. Subclasses BaseException so
    stray 'except Exception:' blocks within apps do not catch or swallow it."""
    def __init__(self, direction):
        super().__init__(direction)
        self.direction = direction


def _read_index():
    try:
        with open(STATE_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return 0


def _write_index(idx):
    try:
        with open(STATE_FILE, "w") as f:
            f.write(str(idx))
    except Exception as e:
        # CIRCUITPY may be mounted read-only to CircuitPython (e.g. host PC
        # has write lock). Switching still works for this session.
        print("Could not persist program selection:", e)


def current_index():
    """Read the persisted index (used by code.py runner at startup)."""
    idx = _read_index()
    if idx < 0 or idx >= len(PROGRAMS):
        idx = 0
    return idx


def next_index(idx, direction):
    """Calculate the next index given direction (+1 for UP, -1 for DOWN)."""
    return (idx + direction) % len(PROGRAMS)


def make_switch_button(current_program=None, pin=None):
    """Set up the button switch handler for an app.
    current_program is the filename of the program calling this.
    Clears any pending button events queued before the app started.
    Returns check() to call regularly inside the app's main loop."""
    # Drain any events that occurred during startup/transition
    while _keys.events.get_into(_event):
        pass

    start_time = time.monotonic()

    def check():
        # 1. Background hooks (brightness schedule, time sync)
        display_common.tick()

        # 2. Drain keys queue; act on first pressed event
        while _keys.events.get_into(_event):
            if _event.pressed:
                direction = 1 if _event.key_number == 0 else -1
                raise SwitchRequested(direction)

        # 3. Optional auto-rotation (Phase 8)
        if AUTO_ROTATE_SECONDS > 0 and not hold_rotation:
            if time.monotonic() - start_time >= AUTO_ROTATE_SECONDS:
                raise SwitchRequested(1)

    return check
