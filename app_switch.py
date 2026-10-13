# app_switch.py -- lets any program hand off to the next one in PROGRAMS
# when the board's UP button is pressed. Each program identifies ITSELF by
# filename when calling in (rather than re-reading "what's current" back
# from disk) -- that's the only value we can always trust, since a state
# file write can silently fail or lag on CircuitPython. The state file is
# still written best-effort, purely so a cold power-on (via code.py) can
# resume the program you last had selected.
#
# Add a new program to the rotation by dropping its .py file next to this
# one and adding its filename to PROGRAMS below.

import board
import digitalio
import supervisor
import time

PROGRAMS = ("flight_wall.py", "bus_tracker.py")
STATE_FILE = "/program_state.txt"


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
        # has the write lock). Switching still works for this session, it
        # just won't be remembered after a full power cycle.
        print("Could not persist program selection:", e)


def current_index():
    """Only meaningful right after a cold boot (used by code.py). Do NOT use
    this from within a running program to figure out 'what am I' -- use the
    program's own filename instead, see switch_to_next()."""
    idx = _read_index()
    if idx < 0 or idx >= len(PROGRAMS):
        idx = 0
    return idx


def switch_to_next(current_program):
    """Persist and boot into the program after current_program in PROGRAMS.
    current_program is the filename of the program calling this (it knows
    its own identity directly -- much more reliable than reading it back
    from a state file that might not have finished writing yet). Does not
    return."""
    try:
        idx = PROGRAMS.index(current_program)
    except ValueError:
        idx = 0
    idx = (idx + 1) % len(PROGRAMS)
    _write_index(idx)
    print("Switching from", current_program, "to", PROGRAMS[idx])
    supervisor.set_next_code_file(PROGRAMS[idx])
    supervisor.reload()


def make_switch_button(current_program, pin=board.BUTTON_UP):
    """Set up the onboard button used to cycle programs. current_program is
    the filename of the program calling this (e.g. "flight_wall.py").
    Returns a check() function to call once per loop iteration; it calls
    switch_to_next() (which reboots the board) on a press."""
    button = digitalio.DigitalInOut(pin)
    button.switch_to_input(pull=digitalio.Pull.UP)

    # Switching reboots the board into the next program. If the button is
    # still being held down when that next program starts up, its first
    # check() would see "pressed" immediately and switch again -- and again,
    # every reboot, for as long as you hold it -- rapidly cycling through
    # programs with no way to land on the one you want. So: block here until
    # the button is released before we start listening for a new press.
    while not button.value:
        time.sleep(0.05)

    def check():
        if not button.value:  # active-low: pressed pulls the pin to GND
            switch_to_next(current_program)

    return check
