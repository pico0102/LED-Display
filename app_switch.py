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
#   Auto-rotate timeout (0 to disable) . AUTO_ROTATE_SECONDS (default 0, set in settings.toml)
# ============================================================

import os
import board
import keypad
import time
import display_common
import voice_control

# Programs active in rotation. Add each file only when its implementation exists.
PROGRAMS = (
    "flight_wall.py",      # Index 0
    "bus_tracker.py",      # Index 1
    "sports_tracker.py",   # Index 2
    "sleeper_matchup.py",  # Index 3
    "idle_clock.py",       # Index 4
)

# Program labels for the 3-row voice confirmation splash screen (strictly <= 10 chars)
PROGRAM_LABELS = (
    "-> FLIGHTS",  # Index 0 (10 chars)
    "-> BUS",      # Index 1 (6 chars)
    "-> SPORTS",   # Index 2 (9 chars)
    "-> FANTASY",  # Index 3 (10 chars)
    "-> CLOCK",    # Index 4 (8 chars)
)

STATE_FILE = "/program_state.txt"

# Auto-rotate timer: seconds before auto-cycling to next app. 0 = disabled.
# When enabled, button press resets the timer. Apps can set hold_rotation = True
# (e.g., sports_tracker holds rotation while any game is live).
# Note: Flight tracker (flight_wall.py) is unaware of auto-rotation and runs untouched.
AUTO_ROTATE_SECONDS = int(os.getenv("AUTO_ROTATE_SECONDS", "0"))
hold_rotation = False

# Background keypad scanner initialized once at module level.
# Key 0 = BUTTON_UP (+1 / next app)
# Key 1 = BUTTON_DOWN (-1 / previous app)
# value_when_pressed=False, pull=True matches active-low buttons with internal pull-up.
_keys = keypad.Keys((board.BUTTON_UP, board.BUTTON_DOWN), value_when_pressed=False, pull=True)
_event = keypad.Event()


class SwitchRequested(BaseException):
    """Raised when user requests switching apps via button or voice.
    Subclasses BaseException so stray 'except Exception:' blocks within apps
    do not catch or swallow it."""
    def __init__(self, direction=0, target_index=None, source="button"):
        super().__init__(direction)
        self.direction = direction
        self.target_index = target_index
        self.source = source


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

    current_idx = PROGRAMS.index(current_program) if current_program in PROGRAMS else _read_index()
    start_time = time.monotonic()

    def check():
        nonlocal start_time
        # 1. Background hooks (brightness schedule, time sync)
        display_common.tick()

        # 2. Drain keys queue; act on first pressed event
        while _keys.events.get_into(_event):
            if _event.pressed:
                start_time = time.monotonic()
                direction = 1 if _event.key_number == 0 else -1
                raise SwitchRequested(direction)

        # 3. Voice control check (non-blocking LAN + MQTT)
        cmd = voice_control.poll(current_idx)
        if cmd is not None:
            start_time = time.monotonic()
            act = cmd.get("action")
            if act == "hold":
                global hold_rotation
                hold_rotation = bool(cmd.get("hold"))
            elif act == "step":
                raise SwitchRequested(direction=cmd.get("direction", 1), source="voice")
            elif act == "target":
                t_idx = cmd.get("target_index")
                if t_idx is not None and t_idx != current_idx:
                    raise SwitchRequested(direction=0, target_index=t_idx, source="voice")

        # 4. Optional auto-rotation (Phase 8)
        if AUTO_ROTATE_SECONDS > 0 and not hold_rotation:
            if time.monotonic() - start_time >= AUTO_ROTATE_SECONDS:
                start_time = time.monotonic()
                raise SwitchRequested(1)

    return check

