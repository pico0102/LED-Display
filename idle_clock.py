# idle_clock.py -- Idle Clock and Weather display.
# Displays 3 lines:
#   1) Date, centered: "TUE 10/13" (Eastern US time, auto-DST)
#   2) Time, centered: "6:04P" (12-hour format)
#   3) Weather, centered: "67F CLEAR" (from Open-Meteo keyless API)
#
# Weather is refreshed every 15 minutes.
# Press the board's UP or DOWN button to cycle between apps (see app_switch.py).
#
# ============================================================
# WHERE TO CONFIGURE THINGS
# ============================================================
#   Screen brightness (0.0-1.0) ........ display_common.py (BRIGHTNESS)
#   Home latitude/longitude ............ settings.toml (HOME_LAT / HOME_LON)
#   Weather refresh interval (sec) ..... POLL_WEATHER_INTERVAL (default 900)
# ============================================================

import os
import gc
import time
import terminalio
import displayio
from adafruit_display_text.label import Label

from display_common import (
    DISPLAY_WIDTH,
    WHITE,
    ROW_Y,
    init_matrix_display,
    center_x,
)
from network_common import connect_wifi_and_get_session
import app_switch
import time_common
import weather_logic

# Location configuration from settings.toml (defaults to NYC/Jersey City area)
HOME_LAT = float(os.getenv("HOME_LAT", "40.7178"))
HOME_LON = float(os.getenv("HOME_LON", "-74.0431"))
POLL_WEATHER_INTERVAL = 900  # 15 minutes

COLOR_DATE = WHITE
COLOR_CLOCK = 0xFFFF00   # Warm yellow for time
COLOR_WEATHER = 0x00FFFF # Cool cyan for weather

# Display setup
display = init_matrix_display()
main_group = displayio.Group()

lbl_date = Label(terminalio.FONT, color=COLOR_DATE, x=0, y=ROW_Y[0])
lbl_clock = Label(terminalio.FONT, color=COLOR_CLOCK, x=0, y=ROW_Y[1])
lbl_weather = Label(terminalio.FONT, color=COLOR_WEATHER, x=0, y=ROW_Y[2])

for lbl in (lbl_date, lbl_clock, lbl_weather):
    main_group.append(lbl)

display.root_group = main_group


def set_centered_text(lbl, text, color=None):
    """Update label text, color, and center horizontally."""
    lbl.text = str(text)[:10]
    if color is not None:
        lbl.color = color
    lbl.x = center_x(lbl.text)


set_centered_text(lbl_date, "CLOCK")
set_centered_text(lbl_clock, "SYNCING..")
set_centered_text(lbl_weather, "STAND BY..", WHITE)

session = connect_wifi_and_get_session()
check_switch_button = app_switch.make_switch_button("idle_clock.py")

weather_text = "WEATHER --"
last_weather_poll = 0


def fetch_weather():
    """Fetch current temperature and WMO weather code from Open-Meteo."""
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={HOME_LAT}&longitude={HOME_LON}&"
        f"current=temperature_2m,weather_code&temperature_unit=fahrenheit"
    )
    r = None
    try:
        r = session.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            data = r.json()
            curr = data.get("current") or {}
            temp = curr.get("temperature_2m")
            code = curr.get("weather_code")
            return weather_logic.format_weather(temp, code)
    except Exception as e:
        print("Weather fetch failed:", e)
    finally:
        if r is not None:
            try:
                r.close()
            except Exception:
                pass
        gc.collect()
    return None


last_rendered_min = -1

while True:
    check_switch_button()
    now_mono = time.monotonic()

    # 1. Weather polling every 15 minutes
    if now_mono - last_weather_poll >= POLL_WEATHER_INTERVAL or last_weather_poll == 0:
        last_weather_poll = now_mono
        w = fetch_weather()
        if w:
            weather_text = w
        set_centered_text(lbl_weather, weather_text, COLOR_WEATHER)
        check_switch_button()

    # 2. Timekeeping and display update
    now_utc = time_common.utc_now()
    if now_utc is None:
        # Try HTTP sync fallback if NTP hasn't synced
        time_common.sync_http(session)
        now_utc = time_common.utc_now()

    if now_utc is not None:
        # Check if periodic NTP resync is needed (every 1 hour)
        if time_common.needs_resync(3600):
            time_common.sync_http(session)

        current_min = (now_utc // 60)
        if current_min != last_rendered_min:
            last_rendered_min = current_min
            date_str = time_common.fmt_date(now_utc)
            clock_str = time_common.fmt_clock(now_utc)
            set_centered_text(lbl_date, date_str, COLOR_DATE)
            set_centered_text(lbl_clock, clock_str, COLOR_CLOCK)
    else:
        set_centered_text(lbl_date, "NO CLOCK", WHITE)
        set_centered_text(lbl_clock, "--:--", WHITE)

    display.refresh(minimum_frames_per_second=0)
    time.sleep(0.1)
