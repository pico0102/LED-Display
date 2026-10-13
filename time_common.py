# time_common.py -- pure time math and SNTP/HTTP time synchronization.
# Hardware-free pure Python: safe to import and unit test on desktop.

import struct
import time

WEEKDAY_NAMES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
MONTH_NAMES = ("", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
RFC_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Module state for timekeeping
_base_unix = None
_base_mono = None
_last_sync_mono = None


def days_from_civil(y, m, d):
    """Howard Hinnant algorithm: compute days since 1970-01-01 for given civil date."""
    y -= m <= 2
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + 9 if m <= 2 else m - 3) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def civil_from_days(z):
    """Howard Hinnant algorithm: compute (year, month, day) from days since 1970-01-01."""
    z += 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    y += m <= 2
    return y, m, d


def weekday(unix_ts):
    """Return day of week for unix timestamp: 0 = Mon, 1 = Tue, ..., 6 = Sun."""
    days = unix_ts // 86400
    return (days + 3) % 7


def parse_iso_utc(s):
    """Parse UTC ISO-8601 string (e.g. '2026-10-18T17:00Z' or '2026-10-13T22:00:00Z') -> unix timestamp."""
    y = int(s[0:4])
    m = int(s[5:7])
    d = int(s[8:10])
    h = int(s[11:13])
    minute = int(s[14:16])
    sec = 0
    if len(s) >= 19 and s[16] == ':':
        sec = int(s[17:19])
    days = days_from_civil(y, m, d)
    return days * 86400 + h * 3600 + minute * 60 + sec


def parse_rfc1123(date_str):
    """Parse RFC 1123 HTTP Date header (e.g. 'Tue, 13 Oct 2026 22:15:03 GMT') -> unix timestamp."""
    parts = date_str.strip().split()
    day_idx = 1 if parts[0].endswith(",") else 0
    d = int(parts[day_idx])
    m = RFC_MONTHS.get(parts[day_idx + 1], 1)
    y = int(parts[day_idx + 2])
    time_parts = parts[day_idx + 3].split(":")
    h = int(time_parts[0])
    minute = int(time_parts[1])
    sec = int(time_parts[2])
    days = days_from_civil(y, m, d)
    return days * 86400 + h * 3600 + minute * 60 + sec


def eastern_offset(utc_ts):
    """Return Eastern Time offset in seconds (-14400 for EDT, -18000 for EST).
    US DST rules:
    - Starts 2nd Sunday of March at 07:00 UTC
    - Ends 1st Sunday of November at 06:00 UTC
    """
    days = utc_ts // 86400
    y, _, _ = civil_from_days(days)

    # 2nd Sunday of March:
    w_mar1 = (days_from_civil(y, 3, 1) + 3) % 7
    sun1_mar = 1 + (6 - w_mar1) % 7
    sun2_mar = sun1_mar + 7
    dst_start = days_from_civil(y, 3, sun2_mar) * 86400 + 7 * 3600

    # 1st Sunday of November:
    w_nov1 = (days_from_civil(y, 11, 1) + 3) % 7
    sun1_nov = 1 + (6 - w_nov1) % 7
    dst_end = days_from_civil(y, 11, sun1_nov) * 86400 + 6 * 3600

    if dst_start <= utc_ts < dst_end:
        return -14400  # EDT (-4 hours)
    return -18000     # EST (-5 hours)


def fmt_game_time(unix_utc):
    """Format UTC unix timestamp into Eastern game display tuple:
    ('SUN', '1:00P', 'OCT 18')."""
    local = unix_utc + eastern_offset(unix_utc)
    days = local // 86400
    tod = local % 86400
    h = tod // 3600
    minute = (tod % 3600) // 60

    w = weekday(local)
    weekday_str = WEEKDAY_NAMES[w]

    suffix = "A" if h < 12 else "P"
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    time_str = f"{h12}:{minute:02d}{suffix}"

    _, m, d = civil_from_days(days)
    date_str = f"{MONTH_NAMES[m]} {d}"

    return weekday_str, time_str, date_str


def fmt_clock(unix_utc):
    """Format UTC unix timestamp into Eastern 12-hour clock string: '6:04P'."""
    local = unix_utc + eastern_offset(unix_utc)
    tod = local % 86400
    h = tod // 3600
    minute = (tod % 3600) // 60
    suffix = "A" if h < 12 else "P"
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    return f"{h12}:{minute:02d}{suffix}"


def set_time(unix_secs, mono_now=None):
    """Directly set base time (used by tests or sync)."""
    global _base_unix, _base_mono, _last_sync_mono
    if mono_now is None:
        mono_now = time.monotonic()
    _base_unix = unix_secs
    _base_mono = mono_now
    _last_sync_mono = mono_now


def utc_now():
    """Return current UTC unix timestamp, or None if never synchronized."""
    if _base_unix is None or _base_mono is None:
        return None
    return _base_unix + int(time.monotonic() - _base_mono)


def local_now():
    """Return current Eastern unix timestamp, or None if never synchronized."""
    u = utc_now()
    if u is None:
        return None
    return u + eastern_offset(u)


def needs_resync(resync_interval=3600):
    """Return True if time has never been synced or more than resync_interval has elapsed."""
    if _last_sync_mono is None:
        return True
    return (time.monotonic() - _last_sync_mono) >= resync_interval


def sync_ntp(pool):
    """Raw SNTP over UDP to pool.ntp.org and time.google.com with 3 s timeout.
    Returns unix timestamp or None."""
    global _base_unix, _base_mono, _last_sync_mono
    servers = ("pool.ntp.org", "time.google.com")
    req = b"\x1b" + 47 * b"\0"
    buf = bytearray(48)

    for server in servers:
        s = None
        try:
            addr = pool.getaddrinfo(server, 123)[0][4]
            s = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)
            s.settimeout(3.0)
            s.sendto(req, addr)
            n, _ = s.recvfrom_into(buf)
            if n >= 48:
                secs = struct.unpack("!I", buf[40:44])[0] - 2208988800
                mono_now = time.monotonic()
                _base_unix = secs
                _base_mono = mono_now
                _last_sync_mono = mono_now
                print("NTP synced with", server, ":", secs)
                return secs
        except Exception as e:
            print(f"NTP sync failed with {server}:", e)
        finally:
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass
    return None


def sync_http(session):
    """Fallback time synchronization via HTTP Date header."""
    global _base_unix, _base_mono, _last_sync_mono
    try:
        resp = session.get("https://api.sleeper.app/v1/state/nfl")
        date_hdr = resp.headers.get("Date") or resp.headers.get("date")
        resp.close()
        if date_hdr:
            secs = parse_rfc1123(date_hdr)
            mono_now = time.monotonic()
            _base_unix = secs
            _base_mono = mono_now
            _last_sync_mono = mono_now
            print("HTTP Date synced:", secs)
            return secs
    except Exception as e:
        print("HTTP time sync failed:", e)
    return None
