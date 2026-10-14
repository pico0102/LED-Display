# LED Display – Google Home Voice Control Implementation Plan

Audience: Autonomous Coding Agent (Antigravity Flash). Execute Step 1 through Step 6 sequentially. Do not skip verification commands.

---

## Section 0: Project & Hardware Invariants

- **Hardware:** Adafruit MatrixPortal S3 (ESP32-S3, ~2 MB PSRAM), 64x32 HUB75 RGB matrix panel, running **CircuitPython 10.2.1**[cite: 1]. Physical buttons are `board.BUTTON_UP` and `board.BUTTON_DOWN`[cite: 1].
- **Display Geometry:** 64x32 pixels, `BIT_DEPTH = 4`[cite: 1]. Uses `terminalio.FONT` (`CHAR_W = 6` px/char) across 3 text rows at `ROW_Y = (6, 16, 26)`[cite: 1]. **Hard limit: 10 characters per row** (60 px; 11 chars is 66 px and overflows)[cite: 1].
- **Brightness Invariant:** Software brightness adjustments do NOT work on this panel. Do **not** implement brightness voice commands or modify `BRIGHTNESS = 0.12` in `display_common.py`[cite: 1].
- **Untouched App Files Invariant:** `flight_wall.py`, `bus_tracker.py`, `sports_tracker.py`, `sleeper_matchup.py`, and `idle_clock.py` **must not be edited**[cite: 1]. Every app already calls `check_switch_button()` inside its main loop[cite: 1].
- **Available Libraries:** Only `adafruit_requests.mpy`, `adafruit_connection_manager.mpy`, and `adafruit_display_text` exist in `lib/`[cite: 1]. `adafruit_minimqtt` is **not** installed[cite: 1]. All network transport in `voice_control.py` must use built-in `socketpool`, `struct`, and `errno`[cite: 1].

---

## Section 1: Architectural Impact

### 1.1 Existing Files to Modify
| File | Modification Summary |
| :--- | :--- |
| `network_common.py` | Cache the `socketpool.SocketPool(wifi.radio)` instance in a module-level `_cached_pool` global during `connect_wifi_and_get_session()`[cite: 1] and expose `get_socket_pool()`. |
| `display_common.py` | 1. Update `tick()` to use `network_common.get_socket_pool()` instead of creating a new `SocketPool`[cite: 1].<br>2. Add `show_voice_toast(target_label)` to render a 3-row (`<=10` chars/row) transition splash screen on the cached display[cite: 1]. |
| `app_switch.py` | 1. Update `SwitchRequested(BaseException)` to accept `(direction=0, target_index=None, source="button")`[cite: 1].<br>2. Export `PROGRAM_LABELS` mapping each index `0..4` of `PROGRAMS` to its display toast name.<br>3. Inside `make_switch_button()`, determine `current_idx` from `current_program` and poll `voice_control.poll(current_idx)` inside `check()`[cite: 1]. |
| `code.py` | In the `except app_switch.SwitchRequested as e:` block[cite: 1], if `e.target_index is not None`, set `idx = e.target_index`. If `e.source == "voice"`, call `display_common.show_voice_toast(...)` and `time.sleep(0.5)` before loading the target app. |
| `settings.toml.example` | Add voice configuration keys (`AIO_USERNAME`, `AIO_KEY`, `AIO_FEED`, `VOICE_PORT`, `VOICE_TOKEN`)[cite: 1]. |
| `tools/test_logic.py` | Add `TestVoiceLogic(unittest.TestCase)` to unit-test `voice_logic.py` on desktop Python[cite: 1]. |

### 1.2 New Files to Create
| File | Location | Role |
| :--- | :--- | :--- |
| `voice_logic.py` | Repo Root (copied to board) | **Pure Python (zero hardware imports)**[cite: 1]. Parses incoming MQTT/HTTP/UDP payloads and natural-language phrases from Google Home/IFTTT into normalized switch actions and raw MQTT 3.1.1 packet bytes. |
| `voice_control.py` | Repo Root (copied to board) | **Non-blocking hardware transport.** Maintains a persistent, non-blocking raw MQTT 3.1.1 TCP connection to `io.adafruit.com:1883` (serverless cloud push) AND a non-blocking local TCP webhook listener on `VOICE_PORT` (`8080`) using a single pre-allocated `bytearray(256)`. |
| `tools/send_voice_cmd.py` | `tools/` (desktop only) | CLI test script to send local HTTP/TCP or Adafruit IO cloud test commands to the board. |

---

## Section 2: Data Contracts & Memory Constraints

### 2.1 Canonical Program Index & Voice Alias Contract (`voice_logic.py`)
`app_switch.PROGRAMS` defines the 5-app rotation order[cite: 1]:

    PROGRAMS = (
        "flight_wall.py",      # Index 0
        "bus_tracker.py",      # Index 1
        "sports_tracker.py",   # Index 2
        "sleeper_matchup.py",  # Index 3
        "idle_clock.py",       # Index 4
    )

`PROGRAM_LABELS` (used for Row 3 of the `0.5s` splash screen, strictly `<= 10` chars)[cite: 1]:

    PROGRAM_LABELS = (
        "-> FLIGHTS",  # Index 0 (10 chars)
        "-> BUS",      # Index 1 (6 chars)
        "-> SPORTS",   # Index 2 (9 chars)
        "-> FANTASY",  # Index 3 (10 chars)
        "-> CLOCK",    # Index 4 (8 chars)
    )

`voice_logic.py` keyword mapping table (evaluated case-insensitively after stripping punctuation):
- **Index `0` (`flight_wall.py`)**[cite: 1]: `("flight", "flights", "plane", "planes", "sky", "aircraft", "0")`
- **Index `1` (`bus_tracker.py`)**[cite: 1]: `("bus", "buses", "transit", "njt", "commute", "1")`
- **Index `2` (`sports_tracker.py`)**[cite: 1]: `("sport", "sports", "score", "scores", "game", "games", "devils", "cowboys", "yankees", "nhl", "nfl", "mlb", "2")`
- **Index `3` (`sleeper_matchup.py`)**[cite: 1]: `("fantasy", "sleeper", "matchup", "football", "3")`
- **Index `4` (`idle_clock.py`)**[cite: 1]: `("clock", "time", "weather", "idle", "home", "4")`
- **Step `+1` (Next)**: `("next", "up", "forward", "cycle")`
- **Step `-1` (Previous)**: `("prev", "previous", "down", "back")`
- **Hold Rotation ON**: `("hold", "lock", "pause", "stay")` -> Sets `app_switch.hold_rotation = True`[cite: 1]
- **Hold Rotation OFF**: `("resume", "unlock", "rotate")` -> Sets `app_switch.hold_rotation = False`[cite: 1]

### 2.2 Normalized Action Dictionary
`voice_logic.parse_command(raw_text, expected_token="")` returns `None` or:

    {
        "action": "target" | "step" | "hold",
        "target_index": int | None,  # 0..4 when action == "target", else None
        "direction": int,            # +1 or -1 when action == "step", else 0
        "hold": bool | None,         # True/False when action == "hold", else None
    }

### 2.3 Splash Screen Layout Contract (`display_common.show_voice_toast`)
- **Panel:** 64x32, `terminalio.FONT`, `CHAR_W = 6`, `ROW_Y = (6, 16, 26)`[cite: 1].
- **Row 0 (`y = 6`):** `"VOICE CMD"` (9 chars, centered at `x = center_x("VOICE CMD")`, color `0x00FFFF` cyan)[cite: 1].
- **Row 1 (`y = 16`):** `"SWITCH TO"` (9 chars, centered at `x = center_x("SWITCH TO")`, color `0xFFFFFF` white)[cite: 1].
- **Row 2 (`y = 26`):** `str(target_label)[:10]` (e.g. `"-> SPORTS"`, centered at `x = center_x(...)`, color `0x00FF00` green)[cite: 1].
- **Duration:** Displayed in `code.py` for `0.5` seconds (`time.sleep(0.5)`) immediately prior to `__import__(mod)`[cite: 1].

### 2.4 CircuitPython Memory & Non-Blocking I/O Constraints
1. **Why Serverless Raw MQTT (`io.adafruit.com:1883`) Instead of HTTP Polling:**
   - `bus_tracker.py` advances its scrolling ticker every `0.1s` (`SCROLL_TICK_SECONDS = 0.1`)[cite: 1].
   - Polling an HTTPS URL every few seconds blocks the single-threaded ESP32-S3 for 500–1200ms during TLS handshakes, visibly freezing the bus ticker.
   - By maintaining a single non-blocking TCP socket (`sock.setblocking(False)`) to `io.adafruit.com` port `1883`, `voice_control.poll()` checks `sock.recv_into(_RX_BUF)` on every `0.1s` tick in **< 0.3ms** with **0 bytes of heap allocation**.
   - When Google Home triggers an IFTTT webhook to Adafruit IO, the broker pushes a compact `< 64-byte` MQTT `PUBLISH` packet down the open socket, switching the screen in `< 100ms` with zero ticker stutter.
2. **Pre-Allocated Static Buffer:**
   - `voice_control.py` allocates `_RX_BUF = bytearray(256)` once at import time.
   - `sys.modules.pop(mod, None)` in `code.py` only unloads the active screen module[cite: 1]; `app_switch.py` and `voice_control.py` stay resident across in-memory app switches so the MQTT socket and LAN listener remain open across transitions.
   - Heap safety net in `code.py` (`gc.mem_free() < 150000`) remains intact[cite: 1].

---

## Section 3: Step-by-Step Task Breakdown

### Step 1: Backup Original Files
- **Target Files:** `docs/backup/`
- **Precise Actions:**
  1. Create directory `docs/backup/` if it does not exist[cite: 1].
  2. Copy `flight_wall.py`, `app_switch.py`, `code.py`, `display_common.py`, and `network_common.py` into `docs/backup/<name>.orig`[cite: 1].
- **Verification:** Confirm `docs/backup/flight_wall.py.orig` exists and matches `flight_wall.py`[cite: 1].

---

### Step 2: Create Pure Logic Module (`voice_logic.py`) & Unit Tests (`tools/test_logic.py`)
- **Target Files:** `voice_logic.py` (create), `tools/test_logic.py` (modify)[cite: 1].
- **Precise Logic Changes in `voice_logic.py`:**
  1. **Zero hardware imports** (only `json` and `struct`)[cite: 1].
  2. Define `ALIASES` mapping indices `0..4`, step directions `+1`/`-1`, and hold booleans `True`/`False`.
  3. Implement `resolve_action(text)`:
     - Convert `text` to lowercase, replace punctuation (`"`, `'`, `,`, `.`, `!`, `?`, `-`, `_`, `/`, `:`) with spaces, and split into tokens.
     - Check if any token (or the full stripped string) matches a keyword for indices `0..4`, step `+1`/`-1`, or hold `True`/`False`.
     - Return the normalized dict (`{"action": ..., "target_index": ..., "direction": ..., "hold": ...}`) or `None`.
  4. Implement `parse_command(raw_text, expected_token="")`:
     - Handle 3 input formats:
       a. **HTTP Request Line:** e.g. `GET /switch?app=sports&token=xyz HTTP/1.1` -> parse query params `app` and `token`.
       b. **JSON String:** e.g. `{"app": "sports", "token": "xyz"}` or Adafruit IO JSON `{"value": "sports"}` -> extract `app`, `value`, or `command`.
       c. **Raw Text / MQTT Payload:** e.g. `"sports"`, `"switch to fantasy"`, or `"CMD:sports:xyz"`.
     - If `expected_token` is non-empty and the input is HTTP or `CMD:` format, verify token matches `expected_token`; return `None` on mismatch.
     - Pass extracted command string to `resolve_action()` and return the result.
  5. Implement lightweight MQTT 3.1.1 byte builders/parsers (pure functions for unit testing):
     - `build_mqtt_connect(client_id, username, password, keepalive=60)` -> returns `bytes` for MQTT `CONNECT` packet (`0x10`).
     - `build_mqtt_subscribe(topic, packet_id=1)` -> returns `bytes` for MQTT `SUBSCRIBE` packet (`0x82`).
     - `build_mqtt_pingreq()` -> returns `b"\xc0\x00"`.
     - `parse_mqtt_publish(buf, n)` -> inspects `buf[:n]`. If `(buf[0] & 0xF0) == 0x30` (MQTT `PUBLISH`), decodes the variable-length remaining-length header, skips the 2-byte topic length + topic string (and 2-byte packet ID if QoS > 0), and returns the UTF-8 payload string (or `None` if not a `PUBLISH` packet).
- **Precise Logic Changes in `tools/test_logic.py`:**
  1. Import `voice_logic` at the top alongside `time_common`, `sports_logic`, `sleeper_logic`, `bus_logic`, `weather_logic`[cite: 1].
  2. Add `TestVoiceLogic(unittest.TestCase)` testing:
     - All 5 screen target keywords (`flights` -> 0, `bus` -> 1, `sports`/`devils` -> 2, `fantasy`/`sleeper` -> 3, `clock`/`weather` -> 4).
     - Natural language phrases (`"please show the devils game"` -> 2, `"switch to bus tracker"` -> 1).
     - Step commands (`"next"` -> `+1`, `"previous"` -> `-1`) and Hold commands (`"hold"` -> `True`, `"resume"` -> `False`).
     - HTTP GET query parsing with valid and invalid `expected_token`.
     - MQTT `CONNECT`, `SUBSCRIBE`, and `parse_mqtt_publish()` round-trip packet decoding.
- **Verification:** Run `python tools/test_logic.py` and confirm all tests pass[cite: 1].

---

### Step 3: Shared SocketPool & Voice Toast UI (`network_common.py`, `display_common.py`, `settings.toml.example`)
- **Target Files:** `network_common.py`, `display_common.py`, `settings.toml.example`[cite: 1].
- **Precise Logic Changes:**
  1. **`network_common.py`**:
     - Add `_cached_pool = None` at module level[cite: 1].
     - In `connect_wifi_and_get_session()`, assign `_cached_pool = pool` after `pool = socketpool.SocketPool(wifi.radio)`[cite: 1].
     - Add function `get_socket_pool()`:

           def get_socket_pool():
               """Return cached SocketPool if Wi-Fi is connected, else None."""
               global _cached_pool
               if not wifi.radio.connected:
                   return None
               if _cached_pool is None:
                   _cached_pool = socketpool.SocketPool(wifi.radio)
               return _cached_pool

  2. **`display_common.py`**:
     - In `tick()`, replace `pool = socketpool.SocketPool(wifi.radio)` with `import network_common; pool = network_common.get_socket_pool()` and guard with `if pool:`[cite: 1].
     - Add `show_voice_toast(target_label)` right below `show_error(text)`[cite: 1]:

           def show_voice_toast(target_label):
               """Display a 3-line centered voice command confirmation splash screen."""
               import terminalio
               from adafruit_display_text.label import Label

               disp = init_matrix_display()
               group = displayio.Group()

               rows = (
                   ("VOICE CMD", 0x00FFFF),
                   ("SWITCH TO", WHITE),
                   (str(target_label)[:10], 0x00FF00),
               )
               for i, (line_str, color) in enumerate(rows):
                   lbl = Label(terminalio.FONT, text=line_str, color=color)
                   lbl.x = center_x(line_str)
                   lbl.y = ROW_Y[i]
                   group.append(lbl)

               disp.root_group = group
               disp.refresh(minimum_frames_per_second=0)

  3. **`settings.toml.example`**:
     - Append configuration template at the bottom of the file[cite: 1]:

           # Google Home Voice Control (Adafruit IO MQTT + Local LAN Webhook)
           AIO_USERNAME = "your-adafruit-io-username"
           AIO_KEY = "your-adafruit-io-key"
           AIO_FEED = "led-display"
           VOICE_PORT = 8080
           VOICE_TOKEN = ""

- **Verification:** Run `python tools/test_logic.py` and `python tools/check_apis.py`[cite: 1].

---

### Step 4: Non-Blocking Voice Transport (`voice_control.py`)
- **Target Files:** `voice_control.py` (create).
- **Precise Logic Changes:**
  1. Read environment variables via `os.getenv()`:
     - `AIO_USERNAME = os.getenv("AIO_USERNAME", "")`
     - `AIO_KEY = os.getenv("AIO_KEY", "")`
     - `AIO_FEED = os.getenv("AIO_FEED", "led-display")`
     - `VOICE_PORT = int(os.getenv("VOICE_PORT", "8080"))`
     - `VOICE_TOKEN = os.getenv("VOICE_TOKEN", "")`
  2. Pre-allocate static module state:
     - `_RX_BUF = bytearray(256)`
     - `_mqtt_sock = None`
     - `_mqtt_connected = False`
     - `_last_mqtt_ping = 0.0`
     - `_last_mqtt_retry = 0.0`
     - `_lan_sock = None`
     - `MQTT_KEEPALIVE = 50`
     - `MQTT_RETRY_SECONDS = 30`
  3. Implement `_poll_lan()`:
     - Lazily bind `_lan_sock` (`SOCK_STREAM`, non-blocking `setblocking(False)`) to `("0.0.0.0", VOICE_PORT)` if `VOICE_PORT > 0`.
     - Call `client, _ = _lan_sock.accept()`. On `OSError` (`EAGAIN`), return `None`.
     - If a client connects: `client.settimeout(0.2)`, `n = client.recv_into(_RX_BUF)`, send `b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK"`, close `client`, and parse `_RX_BUF[:n]` via `voice_logic.parse_command(raw, VOICE_TOKEN)`.
  4. Implement `_poll_mqtt()`:
     - If not `AIO_USERNAME` or not `AIO_KEY` or `AIO_USERNAME.startswith("your-")`, return `None`.
     - If `_mqtt_sock is None`:
       - Throttle connection attempts to once every `MQTT_RETRY_SECONDS` (`30s`) so bad credentials or offline internet never block the loop.
       - Connect TCP socket (`pool.socket(pool.AF_INET, pool.SOCK_STREAM)`) with `settimeout(2.0)` to `("io.adafruit.com", 1883)`.
       - Send `voice_logic.build_mqtt_connect(...)`, read 4-byte `CONNACK` into `_RX_BUF`, send `voice_logic.build_mqtt_subscribe(f"{AIO_USERNAME}/feeds/{AIO_FEED}")`.
       - Set `_mqtt_sock.setblocking(False)` immediately after subscribing.
     - When `_mqtt_sock` is connected:
       - Send `voice_logic.build_mqtt_pingreq()` if `now - _last_mqtt_ping >= MQTT_KEEPALIVE`.
       - Call `n = _mqtt_sock.recv_into(_RX_BUF)`.
       - If `n == 0` (remote closed), close `_mqtt_sock` and set `_mqtt_sock = None`.
       - If `n > 0`, extract payload via `voice_logic.parse_mqtt_publish(_RX_BUF, n)` and return `voice_logic.parse_command(payload)`.
  5. Implement `poll(current_idx)`:
     - Check `_poll_lan()` first, then `_poll_mqtt()`.
     - Wrap both in `try/except Exception:` so network errors never propagate into the active screen app.
- **Error Handling:** Ignore non-blocking `OSError` codes (`errno.EAGAIN`, `errno.EWOULDBLOCK`, `errno.ETIMEDOUT`, or numeric `11`, `35`, `116`). On any other socket `OSError`, cleanly close `_mqtt_sock` and reset to `None`.

---

### Step 5: Wire `app_switch.py` and `code.py` for Direct Jump & Splash Toast
- **Target Files:** `app_switch.py`, `code.py`[cite: 1].
- **Precise Logic Changes in `app_switch.py`:**
  1. Import `voice_control` at module level.
  2. Define `PROGRAM_LABELS = ("-> FLIGHTS", "-> BUS", "-> SPORTS", "-> FANTASY", "-> CLOCK")`.
  3. Update `SwitchRequested`[cite: 1]:

         class SwitchRequested(BaseException):
             """Raised when user requests switching apps via button or voice."""
             def __init__(self, direction=0, target_index=None, source="button"):
                 super().__init__(direction)
                 self.direction = direction
                 self.target_index = target_index
                 self.source = source

  4. In `make_switch_button(current_program=None, pin=None)`[cite: 1]:
     - Compute `current_idx = PROGRAMS.index(current_program) if current_program in PROGRAMS else _read_index()`[cite: 1].
     - Inside `check()`, right after draining `_keys.events` and before the `AUTO_ROTATE_SECONDS` check[cite: 1]:

           # 3. Voice control check (non-blocking LAN + MQTT)
           cmd = voice_control.poll(current_idx)
           if cmd is not None:
               start_time = time.monotonic()
               act = cmd.get("action")
               if act == "hold":
                   global hold_rotation
                   hold_rotation = bool(cmd.get("hold"))
               elif act == "step":
                   raise SwitchRequested(direction=cmd.get("direction", 1), source="voice")
               elif act == "target":
                   t_idx = cmd.get("target_index")
                   if t_idx is not None and t_idx != current_idx:
                       raise SwitchRequested(direction=0, target_index=t_idx, source="voice")

- **Precise Logic Changes in `code.py`:**
  1. Update the `except app_switch.SwitchRequested as e:` block[cite: 1]:

         except app_switch.SwitchRequested as e:
             if getattr(e, "target_index", None) is not None:
                 idx = e.target_index % len(app_switch.PROGRAMS)
             else:
                 idx = app_switch.next_index(idx, e.direction)
             app_switch._write_index(idx)
             if getattr(e, "source", "button") == "voice":
                 toast_lbl = app_switch.PROGRAM_LABELS[idx]
                 display_common.show_voice_toast(toast_lbl)
                 time.sleep(0.5)

- **Verification:** Run `python tools/test_logic.py`[cite: 1].

---

### Step 6: Create Desktop CLI Tester (`tools/send_voice_cmd.py`) & Final Audit
- **Target Files:** `tools/send_voice_cmd.py` (create).
- **Precise Logic Changes:**
  1. Create a pure-stdlib Python 3 script (`argparse`, `urllib.request`, `json`) supporting two modes:
     - **LAN Mode (`--host <ip>`):** Sends `GET http://<host>:8080/switch?app=<cmd>&token=<token>`.
     - **Cloud MQTT REST Mode (`--aio-user`, `--aio-key`):** Sends `POST [https://io.adafruit.com/api/v2/](https://io.adafruit.com/api/v2/)<user>/feeds/led-display/data` with JSON `{"value": "<cmd>"}` and header `X-AIO-Key: <key>`.

---

## Section 4: Final Verification Checklist

1. Run `python tools/test_logic.py` -> must pass 100% including `TestVoiceLogic`[cite: 1].
2. Run `python tools/check_apis.py` -> must pass 100%[cite: 1].
3. Run `fc /b docs\backup\flight_wall.py.orig flight_wall.py` -> must confirm `flight_wall.py` is byte-identical[cite: 1].
4. Output final summary listing all modified/created files and the exact root `.py` files to copy to `CIRCUITPY`[cite: 1].