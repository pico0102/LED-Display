# code.py -- FlightWall Mini
# Static nearest-COMMERCIAL-flight card, 3 centered lines:
#   1) airline (colored) + flight number (white)
#   2) aircraft full name (e.g. B737-800)
#   3) origin > destination
# Data: OpenSky (position) + adsbdb.com (aircraft type & route), both free.
# Caches expanded aircraft type names and airline codes to CIRCUITPY.

import os
import ssl
import time
import math
import board
import wifi
import socketpool
import terminalio
import displayio
import rgbmatrix
import framebufferio
import adafruit_requests
from adafruit_display_text.label import Label

displayio.release_displays()

# --- Panel setup: 64x32, 2.5mm pitch, 1:16 scan (4 address lines) ---
DISPLAY_WIDTH = 64
DISPLAY_HEIGHT = 32
BIT_DEPTH = 4

matrix = rgbmatrix.RGBMatrix(
    width=DISPLAY_WIDTH,
    height=DISPLAY_HEIGHT,
    bit_depth=BIT_DEPTH,
    rgb_pins=[
        board.MTX_R1, board.MTX_G1, board.MTX_B1,
        board.MTX_R2, board.MTX_G2, board.MTX_B2,
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
display.brightness = 0.3

# --- Home coordinates: 07307 / Jersey City ---
HOME_LAT = 40.7178
HOME_LON = -74.0431

# --- Bounding box to search: roughly Newark to LGA/Teterboro airspace ---
BOUNDING_BOX = {
    "lamin": 40.62, "lomin": -74.20,
    "lamax": 40.88, "lomax": -73.85,
}
POLL_SECONDS = 15
RATE_LIMIT_BACKOFF_SECONDS = 60

# --- Airline prefix -> (name, bright color) ---
AIRLINES = {
    "DAL": ("DELTA", 0xFF0000),
    "UAL": ("UNITED", 0x3366FF),
    "AAL": ("AMERICAN", 0xFF6600),
    "SWA": ("SOUTHWEST", 0xFFD500),
    "FFT": ("FRONTIER", 0x00FF00),
    "JBU": ("JETBLUE", 0x00FFFF),
    "NKS": ("SPIRIT", 0xFF33CC),
    "ASA": ("ALASKA", 0xAA33FF),
    "BAW": ("BRITISH", 0xAA33FF),
    "DLH": ("LUFTHANSA", 0x9999FF),
    "AFR": ("AIRFRANCE", 0x5500FF),
    "FDX": ("FEDEX", 0xCC00FF),
    "UPS": ("UPS", 0x8B4513),
    "LOT": ("POLISHAIR", 0x4444FF),
    "ACA": ("AIRCANADA", 0xFF5500),
    "AMX": ("AEROMEXICO", 0xFFCC00),
    "IBE": ("IBERIA", 0xFF0088),
    "KLM": ("KLM", 0x0088FF),
    "SWR": ("SWISS", 0xFF3333),
    "VIR": ("VIRGIN", 0xFF0000),
    "EZY": ("EASYJET", 0xFFCC00),
    "RYR": ("RYANAIR", 0x000099),
    "KAL": ("KOREANAIR", 0x0055AA),
    "EDV": ("DELTA", 0xFF0000),
    "SKW": ("SKYWEST", 0x66CCFF),
    "RPA": ("REPUBLIC", 0x66CCFF),
    "ENY": ("ENVOY", 0xFF8800),
    "PDT": ("PIEDMONT", 0xFF8800),
    "JIA": ("PSAAIR", 0xFF8800),
    "ASH": ("AIRWISCONSIN", 0x2255FF),
    "GJS": ("GOJET", 0x2255FF),
    "QXE": ("HORIZONAIR", 0xAA33FF),
    "CFG": ("CONDOR", 0xFFCC00),
    "THY": ("TURKISH", 0xFF3333),
    "UAE": ("EMIRATES", 0xCC0000),
    "QTR": ("QATAR", 0x9900CC),
    "ETD": ("ETIHAD", 0xC08A00),
    "SAS": ("SCANDINAVIAN", 0x3366CC),
    "FIN": ("FINNAIR", 0x0099CC),
    "AUA": ("AUSTRIAN", 0xFF0000),
    "ITY": ("ITAAIRWAYS", 0x008800),
    "TAP": ("TAPPORTUGAL", 0x00AA55),
    "AVA": ("AVIANCA", 0xFF0000),
    "CMP": ("COPA", 0x0055AA),
    "LAN": ("LATAM", 0x660099),
    "ANA": ("ANA", 0x0055AA),
    "JAL": ("JAPANAIR", 0xFF0000),
    "CPA": ("CATHAY", 0x00A651),
    "SIA": ("SINGAPORE", 0xFFCC00),
    "CCA": ("AIRCHINA", 0xFF0000),
    "CES": ("CHINAEASTERN", 0x0066B3),
    "CSN": ("CHINASOUTH", 0x004C99),
    "AIC": ("AIRINDIA", 0xFF6600),
    "TSC": ("AIRTRANSAT", 0x0088CC),
    "WJA": ("WESTJET", 0x0099D8),
}
DEFAULT_AIRLINE_COLOR = 0x888888
WHITE = 0xFFFFFF
CHAR_W = 6

# --- Aircraft ICAO code -> full name (expanded as encountered) ---
AIRCRAFT_NAMES = {
    "B738": "B737-800",
    "B788": "B787-8",
    "B789": "B787-9",
    "B78X": "B787-10",
    "B38M": "B737MAX8",
    "B39M": "B737MAX9",
    "B3XM": "B737MAX10",
    "B77W": "B777-300ER",
    "B77L": "B777-200LR",
    "A20N": "A320neo",
    "A21N": "A321neo",
    "A19N": "A319neo",
    "A339": "A330-900",
    "E195": "E195",
    "A320": "A320",
    "A321": "A321",
    "A359": "A350-900",
    "A388": "A380",
    "E190": "E190",
    "CRJ9": "CRJ900",
    "DH4": "D8-400",
    "B777": "B777-200",
    "B779": "B777-9",
    "A330": "A330",
    "B763": "B767-300",
    "B752": "B757-200",
    "B753": "B757-300",
    "B733": "B737-300",
    "B734": "B737-400",
    "B735": "B737-500",
    "B736": "B737-600",
    "B737": "B737-700",
    "B747": "B747-400",
    "B744": "B747-400",
    "B748": "B747-8",
    "B762": "B767-200",
    "B764": "B767-400",
    "B772": "B777-200",
    "B773": "B777-300",
    "A300": "A300",
    "A310": "A310",
    "A319": "A319",
    "A332": "A330-200",
    "A333": "A330-300",
    "A342": "A340-200",
    "A343": "A340-300",
    "A345": "A340-500",
    "A346": "A340-600",
    "A380": "A380-800",
    "CRJ2": "CRJ200",
    "CRJ7": "CRJ700",
    "ERJ": "ERJ",
    "E170": "E170",
    "E175": "E175",
}

# --- Wi-Fi ---
wifi.radio.connect(os.getenv("CIRCUITPY_WIFI_SSID"), os.getenv("CIRCUITPY_WIFI_PASSWORD"))
print("Connected to", os.getenv("CIRCUITPY_WIFI_SSID"))
pool = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())

# --- OpenSky OAuth2 (client credentials) ---
OPENSKY_TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network"
    "/protocol/openid-connect/token"
)
OPENSKY_CLIENT_ID = os.getenv("OPENSKY_CLIENT_ID")
OPENSKY_CLIENT_SECRET = os.getenv("OPENSKY_CLIENT_SECRET")
opensky_token = None
opensky_token_expiry = 0


def get_opensky_token():
    """Fetch (and cache) an OpenSky OAuth2 access token."""
    global opensky_token, opensky_token_expiry
    if not OPENSKY_CLIENT_ID or not OPENSKY_CLIENT_SECRET:
        return None
    if opensky_token and time.monotonic() < opensky_token_expiry:
        return opensky_token
    try:
        r = requests.post(
            OPENSKY_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": OPENSKY_CLIENT_ID,
                "client_secret": OPENSKY_CLIENT_SECRET,
            },
        )
        data = r.json()
        r.close()
        opensky_token = data.get("access_token")
        expires_in = data.get("expires_in", 1800)
        # Refresh a bit early to avoid using a token that expires mid-request
        opensky_token_expiry = time.monotonic() + max(expires_in - 60, 60)
        return opensky_token
    except Exception as e:
        print("OpenSky auth failed:", e)
        opensky_token = None
        return None

main_group = displayio.Group()
display.root_group = main_group

ROW_Y = (6, 16, 26)
label_airline = Label(terminalio.FONT, color=DEFAULT_AIRLINE_COLOR, x=0, y=ROW_Y[0])
label_flightnum = Label(terminalio.FONT, color=WHITE, x=0, y=ROW_Y[0])
label_type = Label(terminalio.FONT, color=WHITE, x=0, y=ROW_Y[1])
label_route = Label(terminalio.FONT, color=WHITE, x=0, y=ROW_Y[2])
for lbl in (label_airline, label_flightnum, label_type, label_route):
    main_group.append(lbl)

# --- Small airplane icon (8x5), shown only on the idle/loading screen ---
PLANE_ICON_ROWS = (
    "00000100",
    "00001110",
    "11111111",
    "00001110",
    "00000100",
)
plane_bitmap = displayio.Bitmap(8, 5, 2)
plane_palette = displayio.Palette(2)
plane_palette[0] = 0x000000
plane_palette.make_transparent(0)
plane_palette[1] = 0x00FFFF
for py, row in enumerate(PLANE_ICON_ROWS):
    for px, ch in enumerate(row):
        plane_bitmap[px, py] = 1 if ch == "1" else 0
plane_icon = displayio.TileGrid(plane_bitmap, pixel_shader=plane_palette, x=0, y=ROW_Y[0] - 2)
plane_icon.hidden = True
main_group.append(plane_icon)


def center_x(text):
    return max(0, (DISPLAY_WIDTH - len(text) * CHAR_W) // 2)


def set_idle(title, line2, line3):
    """Friendly idle/loading screen with a small plane icon next to the title."""
    plane_icon.hidden = False
    icon_w = 8
    icon_gap = 2
    total_len = icon_w + icon_gap + len(title) * CHAR_W
    start_x = max(0, (DISPLAY_WIDTH - total_len) // 2)

    plane_icon.x = start_x

    label_airline.text = ""
    label_flightnum.text = title
    label_flightnum.color = 0x00FFFF
    label_flightnum.x = start_x + icon_w + icon_gap

    label_type.text = line2
    label_type.x = center_x(line2)

    label_route.text = line3
    label_route.x = center_x(line3)


def set_card(airline_text, flightnum_text, type_text, route_text, airline_color=DEFAULT_AIRLINE_COLOR):
    plane_icon.hidden = True
    gap_chars = 0
    total_len = len(airline_text) + gap_chars + len(flightnum_text)
    start_x = max(0, (DISPLAY_WIDTH - total_len * CHAR_W) // 2)

    label_airline.text = airline_text
    label_airline.color = airline_color
    label_airline.x = start_x

    label_flightnum.text = flightnum_text
    label_flightnum.color = WHITE
    label_flightnum.x = start_x + (len(airline_text) + gap_chars) * CHAR_W

    label_type.text = type_text
    label_type.x = center_x(type_text)

    label_route.text = route_text
    label_route.x = center_x(route_text)


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def is_commercial(callsign):
    prefix = callsign[:3]
    if len(callsign) < 4 or not prefix.isalpha():
        return False
    # Exclude US N-number general aviation tails
    if callsign[0] == "N" and callsign[1:2].isdigit():
        return False
    return True


def fetch_flights():
    url = (
        "https://opensky-network.org/api/states/all"
        f"?lamin={BOUNDING_BOX['lamin']}&lomin={BOUNDING_BOX['lomin']}"
        f"&lamax={BOUNDING_BOX['lamax']}&lomax={BOUNDING_BOX['lomax']}"
    )
    token = get_opensky_token()
    headers = {"Authorization": f"Bearer {token}"} if token else None
    try:
        response = requests.get(url, headers=headers)
    except Exception as e:
        print("Fetch failed:", e)
        return []

    status_code = response.status_code
    try:
        data = response.json()
    except Exception as e:
        print("Fetch failed:", e, "- status:", status_code, "body:", response.text[:200])
        response.close()
        if status_code == 429:
            return "rate_limited"
        return []
    response.close()

    flights = []
    for state in (data.get("states") or []):
        callsign = (state[1] or "").strip()
        icao24 = state[0]
        longitude, latitude = state[5], state[6]
        on_ground = state[8]
        if not callsign or on_ground or latitude is None or longitude is None:
            continue
        if not is_commercial(callsign):
            continue
        flights.append({
            "callsign": callsign, "icao24": icao24,
            "lat": latitude, "lon": longitude,
        })
    return flights


def nearest_flight(flights):
    best, best_dist = None, None
    for f in flights:
        dist = haversine_km(HOME_LAT, HOME_LON, f["lat"], f["lon"])
        if best_dist is None or dist < best_dist:
            best, best_dist = f, dist
    return best


def lookup_aircraft_type(icao24):
    """Fetch ICAO code from adsbdb and expand to full name."""
    try:
        r = requests.get(f"https://api.adsbdb.com/v0/aircraft/{icao24}")
        data = r.json()
        r.close()
        ac = data.get("response", {}).get("aircraft")
        if ac:
            icao_type = ac.get("icao_type")
            if icao_type:
                # Return expanded name if we have it, otherwise the short code
                return AIRCRAFT_NAMES.get(icao_type, icao_type)
    except Exception as e:
        print("Aircraft lookup failed:", e)
    return None


def lookup_route(callsign):
    """Fetch origin and destination from adsbdb."""
    try:
        r = requests.get(f"https://api.adsbdb.com/v0/callsign/{callsign}")
        data = r.json()
        r.close()
        route = data.get("response", {}).get("flightroute")
        if route:
            origin = route.get("origin", {}).get("iata_code")
            dest = route.get("destination", {}).get("iata_code")
            if origin and dest:  # Both must be present and non-empty
                return origin, dest
    except Exception as e:
        print("Route lookup failed:", e)
    return None, None


def render(flight):
    prefix = flight["callsign"][:3].upper()
    flight_number = flight["callsign"][3:]
    _, color = AIRLINES.get(prefix, ("UNKNOWN", DEFAULT_AIRLINE_COLOR))

    aircraft_type = lookup_aircraft_type(flight["icao24"])
    origin, dest = lookup_route(flight["callsign"])

    # Filter: skip if we couldn't look up both aircraft type and route
    if aircraft_type is None or origin is None or dest is None:
        return False

    set_card(
        prefix,
        flight_number,
        aircraft_type,
        f"{origin} > {dest}",
        airline_color=color,
    )
    return True


set_idle("SCANNING", "THE SKIES", "STAND BY..")
last_poll = time.monotonic() - POLL_SECONDS

while True:
    now = time.monotonic()
    if now - last_poll >= POLL_SECONDS:
        last_poll = now
        flights = fetch_flights()
        if flights == "rate_limited":
            last_poll = now + RATE_LIMIT_BACKOFF_SECONDS - POLL_SECONDS
        else:
            flight = nearest_flight(flights)
            print("Nearest flight:", flight)
            if flight:
                if not render(flight):
                    set_idle("SCANNING", "THE SKIES", "STAND BY..")
            else:
                set_idle("SCANNING", "THE SKIES", "STAND BY..")
    display.refresh(minimum_frames_per_second=0)
    time.sleep(1)
