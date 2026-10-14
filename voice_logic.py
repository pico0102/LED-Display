# voice_logic.py - Pure Python voice and command logic for MatrixPortal S3.
# Zero hardware imports (board, displayio, wifi, socketpool must NOT be imported here).
# Can be unit-tested on desktop Python.

import json
import struct

# Canonical mapping of program indices (0..4) to voice alias keywords
TARGET_ALIASES = {
    0: ("flight", "flights", "plane", "planes", "sky", "aircraft", "0"),
    1: ("bus", "buses", "transit", "njt", "commute", "1"),
    2: ("sport", "sports", "score", "scores", "game", "games", "devils", "cowboys", "yankees", "nhl", "nfl", "mlb", "2"),
    3: ("fantasy", "sleeper", "matchup", "football", "3"),
    4: ("clock", "time", "weather", "idle", "home", "4"),
}

STEP_NEXT_ALIASES = ("next", "up", "forward", "cycle")
STEP_PREV_ALIASES = ("prev", "previous", "down", "back")

HOLD_ON_ALIASES = ("hold", "lock", "pause", "stay")
HOLD_OFF_ALIASES = ("resume", "unlock", "rotate")

PUNCTUATION = "\"',.!?-_/:"


def resolve_action(text):
    """Parse normalized natural-language text into an action dictionary.
    
    Returns:
        dict: {"action": "target"|"step"|"hold", "target_index": int|None,
               "direction": int, "hold": bool|None}
        or None if no recognized keyword found.
    """
    if not text or not isinstance(text, str):
        return None

    cleaned = text.lower()
    for ch in PUNCTUATION:
        cleaned = cleaned.replace(ch, " ")
    tokens = cleaned.split()
    if not tokens:
        return None

    # 1. Target screen check
    for token in tokens:
        for idx, keywords in TARGET_ALIASES.items():
            if token in keywords:
                return {
                    "action": "target",
                    "target_index": idx,
                    "direction": 0,
                    "hold": None,
                }

    # 2. Step forward/back check
    for token in tokens:
        if token in STEP_NEXT_ALIASES:
            return {
                "action": "step",
                "target_index": None,
                "direction": 1,
                "hold": None,
            }
        if token in STEP_PREV_ALIASES:
            return {
                "action": "step",
                "target_index": None,
                "direction": -1,
                "hold": None,
            }

    # 3. Hold on/off check
    for token in tokens:
        if token in HOLD_ON_ALIASES:
            return {
                "action": "hold",
                "target_index": None,
                "direction": 0,
                "hold": True,
            }
        if token in HOLD_OFF_ALIASES:
            return {
                "action": "hold",
                "target_index": None,
                "direction": 0,
                "hold": False,
            }

    return None


def parse_command(raw_text, expected_token=""):
    """Parse incoming HTTP, JSON, CMD: or raw MQTT payload into normalized action dict.
    
    If expected_token is non-empty and input is HTTP or CMD: format,
    verify token matches expected_token; return None on mismatch.
    """
    if isinstance(raw_text, (bytes, bytearray)):
        try:
            raw_text = raw_text.decode("utf-8")
        except Exception:
            return None

    if not raw_text or not isinstance(raw_text, str):
        return None

    s = raw_text.strip()
    if not s:
        return None

    # Format A: HTTP Request Line (e.g. GET /switch?app=sports&token=xyz HTTP/1.1)
    if s.startswith("GET ") or s.startswith("POST "):
        first_line = s.split("\r\n")[0].split("\n")[0]
        parts = first_line.split()
        if len(parts) >= 2:
            path = parts[1]
            params = {}
            if "?" in path:
                query = path.split("?", 1)[1]
                for pair in query.split("&"):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        params[k.strip().lower()] = v.strip()
                    elif pair:
                        params[pair.strip().lower()] = ""

            token = params.get("token", "")
            if expected_token and token != expected_token:
                return None

            cmd_cand = (
                params.get("app")
                or params.get("cmd")
                or params.get("command")
                or params.get("value")
            )
            if cmd_cand:
                return resolve_action(cmd_cand)
            return None

    # Format B: JSON String (e.g. {"app": "sports", "token": "xyz"} or {"value": "sports"})
    if s.startswith("{") and s.endswith("}"):
        try:
            data = json.loads(s)
            if isinstance(data, dict):
                token = data.get("token", "")
                if expected_token and token and token != expected_token:
                    return None
                cmd_cand = (
                    data.get("app")
                    or data.get("value")
                    or data.get("command")
                    or data.get("cmd")
                )
                if cmd_cand and isinstance(cmd_cand, str):
                    return resolve_action(cmd_cand)
        except Exception:
            pass

    # Format C: CMD: prefix format (e.g. "CMD:sports:xyz" or "CMD:sports")
    if s.upper().startswith("CMD:"):
        parts = s.split(":")
        cmd_cand = parts[1] if len(parts) > 1 else ""
        token = parts[2] if len(parts) > 2 else ""
        if expected_token and token != expected_token:
            return None
        return resolve_action(cmd_cand)

    # Format D: Raw Text / MQTT Payload (e.g. "sports", "switch to fantasy")
    return resolve_action(s)


# MQTT 3.1.1 Helper Functions (Pure Python)

def _encode_remaining_len(length):
    encoded = bytearray()
    while True:
        byte = length % 128
        length = length // 128
        if length > 0:
            byte |= 0x80
        encoded.append(byte)
        if length == 0:
            break
    return bytes(encoded)


def _encode_str(s):
    if s is None:
        return b""
    b = s.encode("utf-8") if isinstance(s, str) else bytes(s)
    return struct.pack(">H", len(b)) + b


def build_mqtt_connect(client_id, username="", password="", keepalive=60):
    """Build raw MQTT 3.1.1 CONNECT packet bytes."""
    flags = 0x02  # Clean Session
    payload = bytearray(_encode_str(client_id))
    if username:
        flags |= 0x80
        payload.extend(_encode_str(username))
    if password:
        flags |= 0x40
        payload.extend(_encode_str(password))

    var_header = bytearray(b"\x00\x04MQTT\x04")
    var_header.append(flags)
    var_header.extend(struct.pack(">H", keepalive))

    rem_len = len(var_header) + len(payload)
    return b"\x10" + _encode_remaining_len(rem_len) + bytes(var_header) + bytes(payload)


def build_mqtt_subscribe(topic, packet_id=1):
    """Build raw MQTT 3.1.1 SUBSCRIBE packet bytes (QoS 0)."""
    var_header = struct.pack(">H", packet_id)
    payload = _encode_str(topic) + b"\x00"
    rem_len = len(var_header) + len(payload)
    return b"\x82" + _encode_remaining_len(rem_len) + var_header + payload


def build_mqtt_pingreq():
    """Build raw MQTT 3.1.1 PINGREQ packet bytes."""
    return b"\xc0\x00"


def parse_mqtt_publish(buf, n):
    """Inspect buf[:n]. If MQTT PUBLISH packet, extract UTF-8 payload string.
    
    Returns payload string if valid PUBLISH packet, else None.
    """
    if n < 2 or (buf[0] & 0xF0) != 0x30:
        return None

    qos = (buf[0] >> 1) & 0x03

    multiplier = 1
    rem_len = 0
    idx = 1
    while idx < n:
        byte = buf[idx]
        rem_len += (byte & 0x7F) * multiplier
        multiplier *= 128
        idx += 1
        if (byte & 0x80) == 0:
            break

    hdr_end = idx
    if idx + 2 > n:
        return None

    topic_len = struct.unpack(">H", buf[idx:idx + 2])[0]
    idx += 2 + topic_len
    if qos > 0:
        idx += 2  # Skip 2-byte packet ID

    if idx > n:
        return None

    pkt_end = min(n, hdr_end + rem_len)
    payload_bytes = buf[idx:pkt_end]
    try:
        return payload_bytes.decode("utf-8")
    except Exception:
        return None
