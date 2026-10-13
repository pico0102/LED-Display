# bus_tracker.py -- NJ Transit bus countdown for stop #21061 ("PLSD+BWRS" /
# Palisade Ave + Bowers St). 3 lines:
#   1) stop label, white (fixed -- "PALISADE + BOWERS" doesn't fit the panel width)
#   2) the very next bus, centered, e.g. "87-DUE" (route white, time color-coded)
#   3) a left-scrolling ticker of the buses after that, e.g. "86-13m   84-18m"
#      (route white, time color-coded, same as row 2)
# Time color coding: red if under 3 min (or an imminent status like "All
# Aboard"), yellow if under 5 min, green otherwise (including trips far
# enough out that NJT gives a clock time instead of a countdown).
# Data: NJ Transit's official BUSDV2 API (pcsdata.njtransit.com), which needs
# a username + password from registering at developer.njtransit.com/registration
# (approval can take a few days) -- see NJT_USERNAME / NJT_PASSWORD below.
#
# Press the board's UP button to switch to the next program (see app_switch.py).
#
# ============================================================
# WHERE TO CONFIGURE THINGS
# ============================================================
#   Screen brightness (0.0-1.0) ........ display_common.py (BRIGHTNESS) -- the ONLY place to set it
#   Bus stop to track .................. this file (NJT_STOP_ID)
#   Stop label shown on row 1 .......... this file (STOP_LABEL)
#   How often to poll for predictions .. this file (POLL_SECONDS)
#   How many buses in the ticker ....... this file (MAX_SCROLL_BUSES)
#   Ticker scroll speed ................ this file (SCROLL_SPEED_PX, SCROLL_TICK_SECONDS)
#   NJ Transit credentials .............. settings.toml (NJT_USERNAME / NJT_PASSWORD)
#   Wi-Fi credentials .................... settings.toml (CIRCUITPY_WIFI_SSID / _PASSWORD)
#   Which programs exist / switch button  app_switch.py
# ============================================================

import os
import time
import terminalio
import displayio
from adafruit_display_text.label import Label

from display_common import DISPLAY_WIDTH, WHITE, CHAR_W, init_matrix_display, center_x
from network_common import connect_wifi_and_get_session
import app_switch

display = init_matrix_display()

# --- NJ Transit stop to track. Find other stop IDs via the getStops endpoint. ---
NJT_STOP_ID = "21061"
STOP_LABEL = "PLSD+BWRS"  # "PALISADE + BOWERS" doesn't fit in ~10-11 chars/row

# How often (seconds) to poll NJ Transit for updated predictions.
POLL_SECONDS = 30

# How many buses (after the very next one) to include in the scrolling
# ticker on row 3.
MAX_SCROLL_BUSES = 3

# Ticker scroll speed: pixels per main-loop tick. The loop itself runs every
# SCROLL_TICK_SECONDS regardless of POLL_SECONDS, so the ticker keeps moving
# smoothly between polls.
SCROLL_SPEED_PX = 1
SCROLL_TICK_SECONDS = 0.1

BUSDV2_BASE = "https://pcsdata.njtransit.com/api/BUSDV2"

# NJ Transit developer credentials -- register at
# https://developer.njtransit.com/registration (approval can take a few
# days) and put them in settings.toml as:
#   NJT_USERNAME = "your-userid-here"
#   NJT_PASSWORD = "your-password-here"
NJT_USERNAME = os.getenv("NJT_USERNAME")
NJT_PASSWORD = os.getenv("NJT_PASSWORD")
njt_token = None
njt_token_expiry = 0

requests = connect_wifi_and_get_session()

# Without a timeout, a single stalled connection can hang forever with no
# exception raised, freezing the whole loop (same issue found in flight_wall.py).
HTTP_TIMEOUT = 10

# Time color coding.
COLOR_RED = 0xFF0000
COLOR_YELLOW = 0xFFFF00
COLOR_GREEN = 0x00FF00
RED_UNDER_MIN = 3
YELLOW_UNDER_MIN = 5


def time_color_for(sort_key):
    """sort_key comes straight from classify_status(): a real minutes count,
    -1 for an imminent status (e.g. "All Aboard"), or 9999 for a bare clock
    time (trip far enough out that NJT didn't give a countdown at all --
    treated as green/not-urgent)."""
    if sort_key < RED_UNDER_MIN:
        return COLOR_RED
    if sort_key < YELLOW_UNDER_MIN:
        return COLOR_YELLOW
    return COLOR_GREEN


main_group = displayio.Group()
display.root_group = main_group

ROW_Y = (6, 16, 26)
label_title = Label(terminalio.FONT, color=WHITE, x=0, y=ROW_Y[0])
main_group.append(label_title)
label_title.text = STOP_LABEL
label_title.x = center_x(STOP_LABEL)

# Row 2 (next bus): two labels so the route can stay white while the time
# is color-coded independently -- a single Label can only have one color.
label_next_route = Label(terminalio.FONT, color=WHITE, x=0, y=ROW_Y[1])
label_next_time = Label(terminalio.FONT, color=WHITE, x=0, y=ROW_Y[1])
main_group.append(label_next_route)
main_group.append(label_next_time)

# Row 3 (ticker): a Group we scroll as a whole by moving its .x, containing
# a white route Label + a color-coded time Label per bus, rebuilt on every
# poll. Moving the parent Group scrolls all children together in one step,
# instead of having to reposition each child label individually every tick.
TICKER_GAP_PX = 3 * CHAR_W
ticker_group = displayio.Group(x=DISPLAY_WIDTH, y=0)
main_group.append(ticker_group)
ticker_total_width = 0
scrolling_active = False


def clear_ticker():
    while len(ticker_group) > 0:
        ticker_group.pop()


def set_message(text1, text2):
    """Static two-line message (idle/error states) -- no scrolling."""
    global scrolling_active
    scrolling_active = False

    label_next_route.text = ""
    label_next_time.color = WHITE
    label_next_time.text = text1
    label_next_time.x = center_x(text1)

    clear_ticker()
    status_label = Label(terminalio.FONT, color=WHITE, x=center_x(text2), y=ROW_Y[2])
    status_label.text = text2
    ticker_group.append(status_label)
    ticker_group.x = 0


def set_next_bus(route, label, color):
    """Row 2: the very next bus, centered, static. route stays white; label
    (e.g. "13m", "DUE", "09:43P") gets color."""
    dash_label = f"-{label}"
    total_w = (len(route) + len(dash_label)) * CHAR_W
    start_x = max(0, (DISPLAY_WIDTH - total_w) // 2)

    label_next_route.text = route
    label_next_route.x = start_x

    label_next_time.text = dash_label
    label_next_time.color = color
    label_next_time.x = start_x + len(route) * CHAR_W


def rebuild_ticker(trips):
    """Row 3: rebuild the scrolling ticker's contents from scratch and reset
    it to start scrolling in from the right edge again."""
    global ticker_total_width, scrolling_active
    clear_ticker()

    x_cursor = 0
    for trip in trips[1:1 + MAX_SCROLL_BUSES]:
        route = trip.get("public_route", "?")
        sort_key, label = classify_status(trip.get("departurestatus", "?"))
        color = time_color_for(sort_key)
        dash_label = f"-{label}"

        route_label = Label(terminalio.FONT, color=WHITE, x=x_cursor, y=ROW_Y[2])
        route_label.text = route
        ticker_group.append(route_label)
        x_cursor += len(route) * CHAR_W

        time_label = Label(terminalio.FONT, color=color, x=x_cursor, y=ROW_Y[2])
        time_label.text = dash_label
        ticker_group.append(time_label)
        x_cursor += len(dash_label) * CHAR_W + TICKER_GAP_PX

    ticker_total_width = x_cursor
    ticker_group.x = DISPLAY_WIDTH
    scrolling_active = ticker_total_width > 0


def advance_scroll():
    """Call once per main-loop tick; no-op unless the ticker is active."""
    if not scrolling_active:
        return
    ticker_group.x -= SCROLL_SPEED_PX
    if ticker_group.x < -ticker_total_width:
        ticker_group.x = DISPLAY_WIDTH


def get_njt_token():
    """Fetch (and cache) a BUSDV2 auth token. Valid ~24h per NJT's docs; we
    refresh a bit early to be safe."""
    global njt_token, njt_token_expiry
    if not NJT_USERNAME or not NJT_PASSWORD:
        return None
    if njt_token and time.monotonic() < njt_token_expiry:
        return njt_token
    try:
        r = requests.post(
            f"{BUSDV2_BASE}/authenticateUser",
            data={"username": NJT_USERNAME, "password": NJT_PASSWORD},
            timeout=HTTP_TIMEOUT,
        )
        data = r.json()
        r.close()
        if data.get("Authenticated") == "True" and data.get("UserToken"):
            njt_token = data["UserToken"]
            njt_token_expiry = time.monotonic() + 23 * 3600
            return njt_token
        print("NJT auth rejected:", data)
    except Exception as e:
        print("NJT auth failed:", e)
    njt_token = None
    return None


def classify_status(text):
    """NJT's departurestatus field comes in three different shapes:
      - a relative countdown, e.g. "in 18 mins"
      - an imminent-arrival status with no number at all, e.g. "All Aboard"
        or "Due" -- this means SOONER than any numbered countdown, not later
      - (for trips far enough out) an absolute clock time, e.g. "09:43 PM"
    (departuretime, a separate field, is ALWAYS a clock time -- not this.)
    Returns (sort_key, display_label): sort_key is minutes-until for the
    relative case, -1 (soonest) for an imminent status, or 9999 (effectively
    "unknown, put it last") for a bare clock time we can't turn into a
    countdown without a real-time clock on the board."""
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
        # Absolute clock time, e.g. "09:43 PM" -- compact it ("09:43P") so
        # "<route> - <label>" still fits the ~10-11 char row.
        compact = text.replace(" AM", "A").replace(" PM", "P").strip()
        return 9999, compact
    # No digits, no clock time -- something like "All Aboard" or "Due".
    return -1, "DUE"


def minutes_sort_key(trip):
    return classify_status(trip.get("departurestatus", ""))[0]


def fetch_departures():
    token = get_njt_token()
    if not token:
        print("No NJT token available -- check NJT_USERNAME/NJT_PASSWORD in settings.toml")
        return None

    try:
        response = requests.post(
            f"{BUSDV2_BASE}/getBusDV",
            data={"token": token, "stop": NJT_STOP_ID, "direction": "", "route": ""},
            timeout=HTTP_TIMEOUT,
        )
    except Exception as e:
        print("Bus fetch failed:", e)
        return None

    try:
        data = response.json()
    except Exception as e:
        print("Bus fetch failed:", e, "- status:", response.status_code, "body:", response.text[:200])
        response.close()
        return None
    response.close()

    print("NJT raw response:", data)

    if isinstance(data, dict) and "errorMessage" in data:
        print("NJT API error:", data["errorMessage"])
        # Likely an expired/invalid token -- drop it so the next poll re-authenticates.
        global njt_token
        njt_token = None
        return None

    trips = data.get("DVTrip") or []
    return sorted(trips, key=minutes_sort_key)


def render(trips):
    if not trips:
        return False

    first = trips[0]
    route = first.get("public_route", "?")
    sort_key, label = classify_status(first.get("departurestatus", "?"))
    set_next_bus(route, label, time_color_for(sort_key))

    rebuild_ticker(trips)

    print("Next bus:", f"{route}-{label}",
          "| Ticker buses:", [t.get("public_route", "?") for t in trips[1:1 + MAX_SCROLL_BUSES]])
    return True


check_switch_button = app_switch.make_switch_button("bus_tracker.py")

set_message("SCANNING", "STAND BY..")
last_poll = time.monotonic() - POLL_SECONDS

while True:
    check_switch_button()
    advance_scroll()

    now = time.monotonic()
    if now - last_poll >= POLL_SECONDS:
        last_poll = now
        trips = fetch_departures()
        check_switch_button()
        if trips is None:
            set_message("NO DATA", "CHECK KEY" if not (NJT_USERNAME and NJT_PASSWORD) else "RETRYING..")
        elif not render(trips):
            set_message("NO BUSES", "FOUND")
    display.refresh(minimum_frames_per_second=0)
    time.sleep(SCROLL_TICK_SECONDS)
