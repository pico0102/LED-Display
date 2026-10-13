# network_common.py -- shared Wi-Fi + HTTP session setup used by every
# program. Import from here instead of duplicating the connect logic.

import os
import ssl
import wifi
import socketpool
import adafruit_requests


def connect_wifi_and_get_session():
    """Connect to Wi-Fi (creds from settings.toml) and return a requests Session."""
    wifi.radio.connect(os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD"))
    print("Connected to", os.getenv("CIRCUITPY_WIFI_SSID"))
    pool = socketpool.SocketPool(wifi.radio)
    return adafruit_requests.Session(pool, ssl.create_default_context())
