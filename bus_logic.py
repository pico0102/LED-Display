# bus_logic.py -- Pure logic for NJ Transit bus status parsing,
# walk-time catchability filtering, color coding, and leave-now cues.
# Hardware-free pure Python: safe to import and unit test on desktop.

COLOR_WHITE = 0xFFFFFF
COLOR_RED = 0xFF0000
COLOR_YELLOW = 0xFFFF00
COLOR_GREEN = 0x00FF00
COLOR_GRAY = 0x888888

RED_UNDER_MIN = 3
YELLOW_UNDER_MIN = 5


def classify_status(text):
    """NJT's departurestatus field comes in three different shapes:
      - a relative countdown, e.g. "in 18 mins"
      - an imminent-arrival status with no number at all, e.g. "All Aboard"
        or "Due" -- this means SOONER than any numbered countdown, not later
      - (for trips far enough out) an absolute clock time, e.g. "09:43 PM"
    (departuretime, a separate field, is ALWAYS a clock time -- not this.)
    Returns (sort_key, display_label): sort_key is minutes-until for the
    relative case, -1 (soonest) for an imminent status, or 9999 (effectively
    "unknown, put it last") for a bare clock time."""
    if not text:
        return 9999, "?"
    text = str(text)
    lower = text.lower()
    if "min" in lower:
        digits = ""
        for ch in text:
            if ch.isdigit():
                digits += ch
            elif digits:
                break
        if digits:
            minutes = int(digits)
            return minutes, f"{minutes}m"
    if ":" in text:
        compact = text.replace(" AM", "A").replace(" PM", "P").strip()
        return 9999, compact
    return -1, "DUE"


def time_color_for(sort_key):
    """Return color for departure time: red if < 3m, yellow if < 5m, green otherwise."""
    if sort_key < RED_UNDER_MIN:
        return COLOR_RED
    if sort_key < YELLOW_UNDER_MIN:
        return COLOR_YELLOW
    return COLOR_GREEN


def is_catchable(sort_key, walk_min):
    """Determine if a bus can be caught given walk time in minutes.
    - walk_min <= 0: all buses catchable.
    - walk_min > 0: clock-time (9999) or minutes >= walk_min catchable;
      due (-1) or minutes < walk_min not catchable."""
    if walk_min <= 0:
        return True
    if sort_key < 0:
        return False
    return sort_key >= walk_min


def should_leave_now(sort_key, walk_min):
    """Trigger leave-now cue when next catchable bus is within walk_min .. walk_min + 1.
    Clock-time (9999) and negative/imminent (-1) statuses do not trigger leave-now cue."""
    if sort_key == 9999 or sort_key < 0:
        return False
    return walk_min <= sort_key <= (walk_min + 1)


def minutes_sort_key(trip):
    status = trip.get("departurestatus", "") if trip else ""
    return classify_status(status)[0]


def select_display_trips(trips, walk_min=4):
    """Filter and select next trip and ticker trips based on catchability.
    Returns (next_trip, ticker_trips, leave_now_flag).
    - Next catchable bus goes to next_trip (row 2).
    - Other trips go to ticker_trips (row 3).
    - If no trips are catchable, falls back to first trip (shown in gray on row 2)."""
    if not trips:
        return None, [], False

    catchable_idx = None
    for idx, t in enumerate(trips):
        s_key, _ = classify_status(t.get("departurestatus", ""))
        if is_catchable(s_key, walk_min):
            catchable_idx = idx
            break

    if catchable_idx is not None:
        next_trip = trips[catchable_idx]
        ticker_trips = [t for i, t in enumerate(trips) if i != catchable_idx]
    else:
        next_trip = trips[0]
        ticker_trips = trips[1:]

    next_key, _ = classify_status(next_trip.get("departurestatus", ""))
    leave_now = should_leave_now(next_key, walk_min)

    return next_trip, ticker_trips, leave_now
