# voice_control.py - Non-blocking hardware transport for voice control.
# Supports persistent raw MQTT 3.1.1 push from Adafruit IO (port 1883)
# and non-blocking local LAN HTTP webhook (port 8080).
# Uses pre-allocated bytearray buffers to ensure 0-byte heap allocation during idle polling.

import os
import time
import errno
import gc
import voice_logic

# Configuration from environment (settings.toml)
AIO_USERNAME = os.getenv("AIO_USERNAME", "")
AIO_KEY = os.getenv("AIO_KEY", "")
AIO_FEED = os.getenv("AIO_FEED", "led-display")
VOICE_PORT = int(os.getenv("VOICE_PORT", "8080"))
VOICE_TOKEN = os.getenv("VOICE_TOKEN", "")

# Static pre-allocated receive buffer (reused across all socket calls)
_RX_BUF = bytearray(256)

# Module state preserved across in-memory app switches
_mqtt_sock = None
_mqtt_connected = False
_last_mqtt_ping = 0.0
_last_mqtt_retry = 0.0
_lan_sock = None

MQTT_KEEPALIVE = 50
MQTT_RETRY_SECONDS = 30

# Common non-blocking / would-block error numbers
_EAGAIN_SET = (
    11,  # EAGAIN (Linux/ESP32 lwIP)
    35,  # EAGAIN (BSD/macOS)
    116, # ETIMEDOUT (ESP32 lwIP)
    10035, # WSAEWOULDBLOCK (Windows)
    getattr(errno, "EAGAIN", 11),
    getattr(errno, "EWOULDBLOCK", 11),
    getattr(errno, "ETIMEDOUT", 116),
)


def _poll_lan():
    """Non-blocking check for local HTTP commands on VOICE_PORT."""
    global _lan_sock
    if VOICE_PORT <= 0:
        return None

    try:
        import network_common
        pool = network_common.get_socket_pool()
        if pool is None:
            return None

        if _lan_sock is None:
            _lan_sock = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
            _lan_sock.bind(("0.0.0.0", VOICE_PORT))
            _lan_sock.listen(1)
            _lan_sock.setblocking(False)

        client = None
        try:
            client, _ = _lan_sock.accept()
        except OSError as e:
            err = e.args[0] if e.args else 0
            if err in _EAGAIN_SET:
                return None
            try:
                _lan_sock.close()
            except Exception:
                pass
            _lan_sock = None
            return None

        if client is not None:
            try:
                client.settimeout(0.2)
                n = client.recv_into(_RX_BUF)
                resp = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK"
                try:
                    client.send(resp)
                except Exception:
                    pass
                if n and n > 0:
                    raw = _RX_BUF[:n]
                    return voice_logic.parse_command(raw, VOICE_TOKEN)
            finally:
                try:
                    client.close()
                except Exception:
                    pass
    except Exception:
        pass

    return None


def _poll_mqtt():
    """Non-blocking check for incoming Adafruit IO MQTT 3.1.1 messages."""
    global _mqtt_sock, _mqtt_connected, _last_mqtt_ping, _last_mqtt_retry
    if not AIO_USERNAME or not AIO_KEY or AIO_USERNAME.startswith("your-"):
        return None

    now = time.monotonic()
    if _mqtt_sock is None:
        if (now - _last_mqtt_retry) < MQTT_RETRY_SECONDS:
            return None
        _last_mqtt_retry = now

        try:
            import network_common
            pool = network_common.get_socket_pool()
            if pool is None:
                return None

            sock = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect(("io.adafruit.com", 1883))

            client_id = f"matrix-s3-{os.getenv('CIRCUITPY_WIFI_SSID', 'hub')[:8]}"
            conn_pkt = voice_logic.build_mqtt_connect(
                client_id, AIO_USERNAME, AIO_KEY, keepalive=MQTT_KEEPALIVE
            )
            sock.send(conn_pkt)

            n = sock.recv_into(_RX_BUF)
            if not n or n < 4 or (_RX_BUF[0] & 0xF0) != 0x20 or _RX_BUF[3] != 0x00:
                sock.close()
                return None

            sub_topic = f"{AIO_USERNAME}/feeds/{AIO_FEED}"
            sub_pkt = voice_logic.build_mqtt_subscribe(sub_topic, packet_id=1)
            sock.send(sub_pkt)

            sock.setblocking(False)
            _mqtt_sock = sock
            _mqtt_connected = True
            _last_mqtt_ping = now
            return None
        except Exception:
            _mqtt_sock = None
            _mqtt_connected = False
            return None

    # Check keepalive ping interval
    if (now - _last_mqtt_ping) >= MQTT_KEEPALIVE:
        _last_mqtt_ping = now
        try:
            _mqtt_sock.send(voice_logic.build_mqtt_pingreq())
        except Exception:
            try:
                _mqtt_sock.close()
            except Exception:
                pass
            _mqtt_sock = None
            _mqtt_connected = False
            return None

    # Non-blocking receive
    try:
        n = _mqtt_sock.recv_into(_RX_BUF)
    except OSError as e:
        err = e.args[0] if e.args else 0
        if err in _EAGAIN_SET:
            return None
        try:
            _mqtt_sock.close()
        except Exception:
            pass
        _mqtt_sock = None
        _mqtt_connected = False
        return None
    except Exception:
        try:
            _mqtt_sock.close()
        except Exception:
            pass
        _mqtt_sock = None
        _mqtt_connected = False
        return None

    if n is None:
        return None
    if n == 0:
        try:
            _mqtt_sock.close()
        except Exception:
            pass
        _mqtt_sock = None
        _mqtt_connected = False
        return None

    # Check if PUBLISH packet received
    pkt_type = _RX_BUF[0] & 0xF0
    if pkt_type == 0x30:
        payload = voice_logic.parse_mqtt_publish(_RX_BUF, n)
        if payload:
            return voice_logic.parse_command(payload)

    return None


def poll(current_idx=0):
    """Poll for incoming voice commands via local LAN HTTP or cloud MQTT push.
    
    Returns normalized action dict or None.
    """
    try:
        cmd = _poll_lan()
        if cmd is not None:
            return cmd
    except Exception:
        pass

    try:
        cmd = _poll_mqtt()
        if cmd is not None:
            return cmd
    except Exception:
        pass

    return None
