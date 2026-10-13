# network_common.py -- shared Wi-Fi + HTTP session setup used by every
# program. Import from here instead of duplicating the connect logic.
#
# ============================================================
# WHERE TO CONFIGURE THINGS
# ============================================================
#   Wi-Fi credentials ................... settings.toml (CIRCUITPY_WIFI_SSID / _PASSWORD)
# ============================================================

import os
import ssl
import time
import wifi
import socketpool
import adafruit_requests

_cached_session = None


def connect_wifi_and_get_session():
    """Connect to Wi-Fi (creds from settings.toml) and return a requests Session.
    Caches the session once connected; reconnects with up to 3 retries if disconnected."""
    global _cached_session

    if wifi.radio.connected and _cached_session is not None:
        return _cached_session

    ssid = os.getenv("CIRCUITPY_WIFI_SSID")
    password = os.getenv("CIRCUITPY_WIFI_PASSWORD")

    last_err = None
    for attempt in range(1, 4):
        try:
            print("Connecting to Wi-Fi", ssid, f"(attempt {attempt}/3)...")
            wifi.radio.connect(ssid, password)
            print("Connected to", ssid)
            break
        except Exception as e:
            last_err = e
            print(f"Wi-Fi connection attempt {attempt} failed:", e)
            if attempt < 3:
                time.sleep(2)
    else:
        raise last_err

    pool = socketpool.SocketPool(wifi.radio)
    _cached_session = adafruit_requests.Session(pool, ssl.create_default_context())
    return _cached_session
