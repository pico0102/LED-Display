# weather_logic.py -- Pure logic for WMO weather code mapping,
# temperature formatting, and weather display line generation.
# Hardware-free pure Python: safe to import and unit test on desktop.

COLOR_WHITE = 0xFFFFFF
COLOR_CYAN = 0x00FFFF
COLOR_YELLOW = 0xFFFF00
COLOR_GRAY = 0x888888

WMO_CODE_MAP = {
    0: "CLEAR",
    1: "CLEAR",
    2: "P.CLDY",
    3: "CLOUDY",
    45: "FOG",
    48: "FOG",
    51: "DRIZZL",
    53: "DRIZZL",
    55: "DRIZZL",
    56: "FRZ.DZ",
    57: "FRZ.DZ",
    61: "RAIN",
    63: "RAIN",
    65: "RAIN",
    66: "FRZ.RN",
    67: "FRZ.RN",
    71: "SNOW",
    73: "SNOW",
    75: "SNOW",
    77: "SNOW",
    80: "RAIN",
    81: "RAIN",
    82: "RAIN",
    85: "SNOW",
    86: "SNOW",
    95: "STORM",
    96: "STORM",
    99: "STORM",
}


def wmo_to_condition(code):
    """Map WMO numeric weather code to <=6-char description."""
    if code is None:
        return "CLEAR"
    return WMO_CODE_MAP.get(int(code), "CLEAR")


def format_weather(temp_f, weather_code):
    """Format temperature and WMO weather code into <=10 char string: '67F CLEAR'."""
    if temp_f is None:
        return "NO WEATHER"
    try:
        t = int(round(float(temp_f)))
    except (ValueError, TypeError):
        return "NO WEATHER"

    cond = wmo_to_condition(weather_code)
    s = f"{t}F {cond}"
    if len(s) > 10:
        max_cond_len = max(0, 10 - len(f"{t}F "))
        s = f"{t}F {cond[:max_cond_len]}"
    return s[:10]
