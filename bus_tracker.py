# bus_tracker.py -- NJ Transit bus countdown and leave-now cue tracker.
# Displays 3 lines:
#   1) Stop label, white (e.g. "PLSD+BWRS") or blinking red "LEAVE NOW"
#      when the next catchable bus is within WALK_MINUTES + 1.
#   2) The very next catchable bus, centered, e.g. "87-DUE" (route white, time color-coded).
#      Buses that cannot be reached before departure are skipped or shown in gray.
#   3) A left-scrolling ticker of the remaining buses, e.g. "86-13m   84-18m"
#      (route white, time color-coded; uncatchable buses in dim gray).
#
# Time color coding: red if under 3 min (or an imminent status like "Due"),
# yellow if under 5 min, green otherwise (including clock-time trips).
#
# Multiple stops: STOPS list below configures one or more stops. If N > 1,
# the display rotates between stops every ROTATE_STOP_SECONDS (default 8s).
#
# Service alerts note: NJ Transit's BUSDV2 API does not provide a service alerts
# endpoint. Alerts are only provided via GTFS-RT Protocol Buffers (GTFSG2), which
# is unsupported on CircuitPython. Dropped per Implementation Plan Phase 6 spec.
#
# Press the board's UP or DOWN button to cycle between apps (see app_switch.py).
#
# ============================================================
# WHERE TO CONFIGURE THINGS
# ============================================================
#   Screen brightness (0.0-1.0) ........ display_common.py (BRIGHTNESS)
#   Bus stops to track ................. STOPS list below (or NJT_STOP_ID in settings.toml)
#   Walk time to stop (minutes) ........ BUS_WALK_MINUTES in settings.toml or walk_min in STOPS
#   Rotate multiple stops interval ..... ROTATE_STOP_SECONDS (default 8)
#   How often to poll for predictions .. POLL_SECONDS (default 30)
#   NJ Transit credentials ............. settings.toml (NJT_USERNAME / NJT_PASSWORD)
#   Verbose JSON debugging ............. DEBUG = False
# ============================================================

import os
import time
import terminalio
import displayio
from adafruit_display_text.label import Label

from display_common import DISPLAY_WIDTH, WHITE, CHAR_W, init_matrix_display, center_x
from network_common import connect_wifi_and_get_session
import network_common
import app_switch
from bus_logic import (
    COLOR_WHITE,
    COLOR_RED,
    COLOR_YELLOW,
    COLOR_GREEN,
    COLOR_GRAY,
    classify_status,
    time_color_for,
    is_catchable,
    should_leave_now,
    minutes_sort_key,
    select_display_trips,
)

# Debug logging toggle: gates raw JSON debug prints
DEBUG = False

# Simulation mode: set True or BUS_SIMULATE=true in settings.toml to test leave-now cue
SIMULATE_LEAVE_NOW = False

# Default stop and walk settings from settings.toml or defaults
DEFAULT_STOP_ID = os.getenv("NJT_STOP_ID", "21061")
DEFAULT_STOP_LABEL = os.getenv("NJT_STOP_LABEL", "PLSD+BWRS")
DEFAULT_WALK_MIN = int(os.getenv("BUS_WALK_MINUTES", "4"))

# Configured bus stops. Add additional stop dicts here for multi-stop rotation.
STOPS = [
    {"id": DEFAULT_STOP_ID, "label": DEFAULT_STOP_LABEL, "walk_min": DEFAULT_WALK_MIN},
]
ROTATE_STOP_SECONDS = 8

# How often (seconds) to poll NJ Transit for updated predictions.
POLL_SECONDS = 30

# How many buses (after the next catchable one) to include in the scrolling ticker
MAX_SCROLL_BUSES = 3

# Ticker scroll speed: pixels per main-loop tick.
SCROLL_SPEED_PX = 1
SCROLL_TICK_SECONDS = 0.1

BUSDV2_BASE = "https://pcsdata.njtransit.com/api/BUSDV2"
HTTP_TIMEOUT = 10

NJT_USERNAME = os.getenv("NJT_USERNAME")
NJT_PASSWORD = os.getenv("NJT_PASSWORD")

requests = connect_wifi_and_get_session()
display = init_matrix_display()

main_group = displayio.Group()
display.root_group = main_group

ROW_Y = (6, 16, 26)
label_title = Label(terminalio.FONT, color=WHITE, x=0, y=ROW_Y[0])
main_group.append(label_title)
label_title.text = DEFAULT_STOP_LABEL
label_title.x = center_x(DEFAULT_STOP_LABEL)

# Row 2 (next bus): two labels so the route can stay white while the time is color-coded
label_next_route = Label(terminalio.FONT, color=WHITE, x=0, y=ROW_Y[1])
label_next_time = Label(terminalio.FONT, color=WHITE, x=0, y=ROW_Y[1])
main_group.append(label_next_route)
main_group.append(label_next_time)

# Row 3 (ticker): group scrolled together
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
    """Row 2: next catchable bus, centered, static."""
    dash_label = f"-{label}"
    total_w = (len(route) + len(dash_label)) * CHAR_W
    start_x = max(0, (DISPLAY_WIDTH - total_w) // 2)

    label_next_route.text = route
    label_next_route.x = start_x

    label_next_time.text = dash_label
    label_next_time.color = color
    label_next_time.x = start_x + len(route) * CHAR_W


def rebuild_ticker(trips, walk_min):
    """Row 3: rebuild the scrolling ticker's contents from remaining trips."""
    global ticker_total_width, scrolling_active
    clear_ticker()

    x_cursor = 0
    for trip in trips[:MAX_SCROLL_BUSES]:
        route = trip.get("public_route", "?")
        sort_key, label = classify_status(trip.get("departurestatus", "?"))
        color = time_color_for(sort_key) if is_catchable(sort_key, walk_min) else COLOR_GRAY
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
    """Fetch (and cache) a BUSDV2 auth token. Cached in network_common so it survives app swaps."""
    cached = network_common.get_cached_njt_token()
    if cached:
        return cached

    if not NJT_USERNAME or not NJT_PASSWORD:
        return None

    try:
        r = requests.post(
            f"{BUSDV2_BASE}/authenticateUser",
            data={"username": NJT_USERNAME, "password": NJT_PASSWORD},
            timeout=HTTP_TIMEOUT,
        )
        data = r.json()
        r.close()
        if data.get("Authenticated") == "True" and data.get("UserToken"):
            token = data["UserToken"]
            expiry = time.monotonic() + 23 * 3600
            network_common.set_cached_njt_token(token, expiry)
            return token
        if DEBUG:
            print("NJT auth rejected:", data)
    except Exception as e:
        print("NJT auth failed:", e)
    network_common.clear_cached_njt_token()
    return None


def fetch_departures(stop_id):
    """Fetch departure predictions for a specific stop ID."""
    if SIMULATE_LEAVE_NOW or os.getenv("BUS_SIMULATE", "").lower() in ("1", "true"):
        return [
            {"public_route": "87", "departurestatus": "in 2 mins"},
            {"public_route": "86", "departurestatus": "in 4 mins"},
            {"public_route": "84", "departurestatus": "in 12 mins"},
            {"public_route": "82", "departurestatus": "in 25 mins"},
        ]

    token = get_njt_token()
    if not token:
        if DEBUG:
            print("No NJT token available -- check NJT_USERNAME/NJT_PASSWORD in settings.toml")
        return None

    response = None
    try:
        response = requests.post(
            f"{BUSDV2_BASE}/getBusDV",
            data={"token": token, "stop": str(stop_id), "direction": "", "route": ""},
            timeout=HTTP_TIMEOUT,
        )
        if response.status_code != 200:
            return None
        data = response.json()
    except Exception as e:
        print("Bus fetch failed:", e)
        return None
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

    if DEBUG:
        print("NJT raw response:", data)

    if isinstance(data, dict) and "errorMessage" in data:
        if DEBUG:
            print("NJT API error:", data["errorMessage"])
        network_common.clear_cached_njt_token()
        return None

    trips = data.get("DVTrip") or []
    return sorted(trips, key=minutes_sort_key)


# Initialize per-stop state
stop_states = []
for s in STOPS:
    stop_states.append({
        "id": s["id"],
        "label": s.get("label", s["id"]),
        "walk_min": s.get("walk_min", DEFAULT_WALK_MIN),
        "trips": None,
        "last_poll": 0,
    })

current_stop_idx = 0
last_stop_rotate = time.monotonic()
active_leave_now = False
active_stop_label = stop_states[0]["label"]


def render_active_stop():
    """Render the currently active stop on the matrix display."""
    global active_leave_now, active_stop_label
    s = stop_states[current_stop_idx]
    active_stop_label = s["label"]
    trips = s["trips"]

    if trips is None:
        active_leave_now = False
        label_title.text = active_stop_label
        label_title.color = WHITE
        label_title.x = center_x(active_stop_label)
        set_message("NO DATA", "CHECK KEY" if not (NJT_USERNAME and NJT_PASSWORD) else "RETRYING..")
        return

    next_trip, ticker_trips, leave_now = select_display_trips(trips, s["walk_min"])
    if not next_trip:
        active_leave_now = False
        label_title.text = active_stop_label
        label_title.color = WHITE
        label_title.x = center_x(active_stop_label)
        set_message("NO BUSES", "FOUND")
        return

    active_leave_now = leave_now
    if not active_leave_now:
        label_title.text = active_stop_label
        label_title.color = WHITE
        label_title.x = center_x(active_stop_label)

    route = next_trip.get("public_route", "?")
    sort_key, label = classify_status(next_trip.get("departurestatus", "?"))
    color = time_color_for(sort_key) if is_catchable(sort_key, s["walk_min"]) else COLOR_GRAY
    set_next_bus(route, label, color)
    rebuild_ticker(ticker_trips, s["walk_min"])

    if DEBUG:
        print(f"Stop {s['label']} next bus: {route}-{label} | leave_now={leave_now}")


check_switch_button = app_switch.make_switch_button("bus_tracker.py")
render_active_stop()

while True:
    check_switch_button()
    advance_scroll()

    now = time.monotonic()

    # 1. Staggered polling: poll at most one stop needing refresh per tick
    for s in stop_states:
        if now - s["last_poll"] >= POLL_SECONDS:
            s["last_poll"] = now
            s["trips"] = fetch_departures(s["id"])
            if s is stop_states[current_stop_idx]:
                render_active_stop()
            check_switch_button()
            break

    # 2. Multi-stop rotation (when N > 1 stops configured)
    if len(stop_states) > 1 and (now - last_stop_rotate >= ROTATE_STOP_SECONDS):
        current_stop_idx = (current_stop_idx + 1) % len(stop_states)
        last_stop_rotate = now
        render_active_stop()

    # 3. Leave-now cue blinking on Row 1 (0.5s toggle between red LEAVE NOW and white stop label)
    if active_leave_now:
        if int(now * 2) % 2 == 0:
            if label_title.text != "LEAVE NOW":
                label_title.text = "LEAVE NOW"
                label_title.color = COLOR_RED
                label_title.x = center_x("LEAVE NOW")
        else:
            if label_title.text != active_stop_label:
                label_title.text = active_stop_label
                label_title.color = WHITE
                label_title.x = center_x(active_stop_label)
    else:
        if label_title.text != active_stop_label or label_title.color != WHITE:
            label_title.text = active_stop_label
            label_title.color = WHITE
            label_title.x = center_x(active_stop_label)

    display.refresh(minimum_frames_per_second=0)
    time.sleep(SCROLL_TICK_SECONDS)
