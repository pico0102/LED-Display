# LED Display – Implementation Plan (v2, verified)

Audience: an AI model implementing this with no prior context. Execute phase by phase. Each phase ends with a **USER TEST** checkpoint: stop and ask the user to copy files to the board and confirm before continuing. All API facts below were **verified live on 2026-10-13** unless marked `UNVERIFIED`.

## 0. Project facts

- Hardware: Adafruit MatrixPortal S3 (ESP32-S3, ~2 MB PSRAM), 64x32 HUB75 panel, **CircuitPython 10.2.1**. Buttons `board.BUTTON_UP`, `board.BUTTON_DOWN`.
- **Screen = 3 rows x max 10 characters** (`terminalio.FONT`, 6 px/char, rows at y = 6, 16, 26). A 10-char string is 60 px; 11 chars (66 px) overflows. **No progress bars** (never worked on this panel). Text only. Colors in use: white, red `0xFF0000`, yellow `0xFFFF00`, green `0x00FF00`. Panel G/B wires are swapped and already corrected in `display_common.py` - use normal RGB hex, never re-compensate.
- The user copies **every file in the repo root onto the board**. Runtime files go in the root (or `lib/`). Dev-only helpers go in `tools/` (small; harmless if copied).
- Not a git repo. There is **no git diff** - before Phase 1 copy `flight_wall.py` to `tools/flight_wall.py.orig`-style backup *outside the root* (e.g. `docs/backup/flight_wall.py.orig`) and confirm at the end with `fc /b` that `flight_wall.py` is byte-identical. (`code_v1.py`, `code_working.py` are old backups; ignore, don't delete.)
- Desktop has **Python 3.12.10** (`python`). Keep logic in **pure-Python modules with no hardware imports** so they can be unit-tested on the desktop (see Phase 0b).
- Libs in `lib/`: `adafruit_requests`, `adafruit_connection_manager`, `adafruit_display_text` (label, bitmap_label, scrolling_label, ...). Built-ins available: `keypad`, `displayio`, `wifi`, `socketpool`, `ssl`, `gc`, `struct`, `math`, `json`. Nothing else is guaranteed.
- CircuitPython limits: no `typing`/dataclasses/zoneinfo/`calendar`. `math.erf` NOT guaranteed (use `math.exp`). `time.localtime()`/`time.time()` epoch is unreliable on this board -> do all date math with own functions (Phase 2).
- Repo conventions to keep: every program starts with a header comment block, including "WHERE TO CONFIGURE THINGS"; config constants at the top; heavy comments explaining *why*. **Preserve existing comments/docstrings that are unrelated to your change.** Update the "UP button" lines in headers to "UP/DOWN".
- Secrets in `settings.toml` (Wi-Fi, OpenSky, NJT). Never print/echo/commit them. You may append non-secret keys.

### Existing code, as analyzed
| File | What it does | Constraints it creates |
|---|---|---|
| `code.py` | boot launcher: reads `/program_state.txt` index, `supervisor.set_next_code_file()` + `reload()` | will become a runner loop |
| `app_switch.py` | `PROGRAMS` tuple; `make_switch_button(filename)` -> `check()`; press => `switch_to_next` => **reboot** | creates `DigitalInOut(BUTTON_UP)` on every call -> **second call in the same session raises "pin in use"** (see Phase 1) |
| `display_common.py` | calls `displayio.release_displays()` at import; `init_matrix_display()` builds RGBMatrix every call | calling twice builds the matrix twice -> must be cached |
| `network_common.py` | `connect_wifi_and_get_session()` reconnects + new Session **every call** | must cache; add retry |
| `flight_wall.py` (552 lines) | top-level script, `while True`, sleep 0.5 s, network calls up to 10 s timeout each. Calls `check_switch_button()` at loop top, after fetch, between candidates. None of these calls is inside a `try/except` | **must not be edited** (user request). Works with exception-based switching only if the exception is not swallowed (it isn't) |
| `bus_tracker.py` (333 lines) | NJT BUSDV2, stop 21061, 3-row UI, ticker, color-coded times, loop 0.1 s. `check()` calls also outside any `try` | will be edited (Phase 6) |

---
## Phase 0 – Safety net and desktop tooling (do first, small)
1. Back up `flight_wall.py`, `bus_tracker.py`, `app_switch.py`, `code.py`, `display_common.py`, `network_common.py` into `docs/backup/` (`*.orig`).
2. **0b – `tools/check_apis.py`** (desktop, stdlib `urllib` only): hits each endpoint listed in this plan and asserts every JSON path/key the code will read exists (print OK/FAIL per path). Run it at the start and after each new adapter; it is the contract test for the board code.
3. **`tools/test_logic.py`** (desktop, `unittest`): imports the pure modules (`time_common`, `sports_logic`, `sleeper_logic`) and tests them (cases listed per phase). Run `python tools/test_logic.py` before every USER TEST. Board-only modules (`board`, `displayio`...) must never be imported by these modules.

---
## Phase 1 – Non-reboot switching (framework)
Goal: UP = next app, DOWN = previous app, no reboot.

### Design (fixes found in review)
- **Use `keypad.Keys`**, not polled `DigitalInOut`. It scans in the background and queues press events, so (a) short taps are never missed even while an app sleeps 0.5 s / blocks on a 10 s HTTP call (flight_wall does both), (b) debounce is built in, (c) the "wait until released at boot" hack is unnecessary: just clear the event queue when an app starts. Create it **once at `app_switch` module level** (module stays loaded across app swaps, so no "pin in use").
  ```python
  _keys = keypad.Keys((board.BUTTON_UP, board.BUTTON_DOWN), value_when_pressed=False, pull=True)
  _event = keypad.Event()
  ```
  UP is key 0, DOWN is key 1; act on `_event.pressed`.
- **`class SwitchRequested(BaseException)`** (not `Exception`) with `.direction` (+1/-1). Subclassing `BaseException` means a stray `except Exception:` inside any app can't swallow it. Raising from `check()` propagates out of the app's `while True` to the runner.
- `make_switch_button(current_program)` keeps its name and signature and returns `check()`; `check()`: (1) `display_common.tick()` (Phase 3 brightness hook), (2) drain `_keys.events`, on the first press raise `SwitchRequested`, (3) optional auto-rotate (Phase 8). Calling `make_switch_button` clears the queue.
- `PROGRAMS = ("flight_wall.py", "bus_tracker.py", "sports_tracker.py", "sleeper_matchup.py", "idle_clock.py")`; add each file only when it exists (add as phases land, not all up front, or the runner will fail on missing imports). Keep `_read_index/_write_index/current_index`, remove `switch_to_next` (no remaining caller; grep to confirm), add `next_index(idx, direction)` = `(idx + direction) % len(PROGRAMS)`.
- Persist selected index best-effort (existing `_write_index`, already tolerates a read-only filesystem).

### `code.py` -> runner (not a reloader)
```python
import gc, sys, supervisor, time
import app_switch

idx = app_switch.current_index()
loads = 0
while True:
    name = app_switch.PROGRAMS[idx]
    mod = name[:-3]
    try:
        __import__(mod)                    # runs the app's top-level loop until SwitchRequested
    except app_switch.SwitchRequested as e:
        idx = app_switch.next_index(idx, e.direction)
        app_switch._write_index(idx)
    except Exception as e:                  # app crashed (wifi down at boot, bad JSON...)
        print("App crashed:", name, repr(e))
        display_common.show_error("ERR " + mod[:6])   # 3-line message, see Phase 3
        time.sleep(5)                       # then move on to the SAME app again via reload
        supervisor.reload()
    sys.modules.pop(mod, None)
    gc.collect()
    loads += 1
    if loads % 8 == 0 or gc.mem_free() < 150000:
        supervisor.reload()                 # fragmentation safety net; index is persisted
```
Do NOT catch `BaseException` generally (would break Ctrl-C/auto-reload). `ReloadException` must pass through.

### Other framework edits
- `display_common.py`: cache the display in a module global; `init_matrix_display()` returns the cached object on later calls; `release_displays()` runs only on first creation (keep the existing G/B pin comment verbatim). Each app already sets its own `display.root_group`.
- `network_common.py`: cache session (module-global); if `wifi.radio.connected` return cached; else connect **with up to 3 retries** (sleep 2 s) then raise. Keep the function name/signature (flight_wall and bus_tracker import it).
- Add `display_common.show_error(text)` (3 centered white lines, builds its own Group on the cached display).

**Acceptance / USER TEST:** UP/DOWN swap between flight_wall and bus_tracker in ~1-2 s with **no** "Auto-reload"/soft reboot lines in the serial console; a quick tap during flight_wall's 0.5 s sleep still registers; `fc /b` shows flight_wall.py unchanged. Note for user: during a flight_wall network call (up to ~10-20 s worst case) the switch happens when that call returns (existing behavior, unchanged).

---
## Phase 2 – Time (`time_common.py`, pure logic + one network function)
Needed for: game times, brightness schedule, clock app. **Don't use worldtimeapi.org** (flaky, was my v1 mistake).

1. `sync_ntp(pool)`: raw SNTP over UDP, no library: send `b'\x1b' + 47*b'\0'` to `pool.getaddrinfo("pool.ntp.org", 123)[0][4]`, `recv_into` a 48-byte buffer, `secs = struct.unpack("!I", buf[40:44])[0] - 2208988800` (= UTC unix). Timeout 3 s, try 2 servers (`pool.ntp.org`, `time.google.com`). Store `base_unix` and `time.monotonic()`.
2. Fallback: HTTP `Date:` header of any HTTPS response (e.g. HEAD/GET `https://api.sleeper.app/v1/state/nfl`), parse RFC 1123 (`Tue, 13 Oct 2026 22:15:03 GMT`).
3. `utc_now()` = `base_unix + (monotonic - base_mono)`; resync hourly (called lazily from `tick()` / apps; never blocks more than the timeout). If never synced, `utc_now()` returns `None` and **every caller must degrade** (full brightness, no clock, "date only" game times).
4. **Eastern offset computed locally (no API):** US DST: starts 2nd Sunday of March at 07:00 UTC, ends 1st Sunday of November at 06:00 UTC -> offset -4h in between, else -5h. Implement `eastern_offset(utc)`.
5. Pure helpers: `days_from_civil(y,m,d)` / `civil_from_days(z)` (Howard Hinnant algorithms), `weekday(unix_local)`, `parse_iso_utc("2026-10-18T17:00Z" | "2026-10-13T22:00:00Z")` -> unix, `fmt_game_time(unix_utc)` -> `("SUN", "1:00P", "OCT 18")`, `fmt_clock(unix_utc)` -> `"6:04P"`.
6. **test_logic cases:** 2026-03-08 06:59Z vs 07:00Z, 2026-11-01 05:59Z vs 06:00Z boundaries, `fmt_game_time` for `2026-10-18T17:00Z` == SUN 1:00P, leap day, parse of both ISO shapes.

## Phase 3 – Brightness schedule (global)
- `display_common.py`: constants `BRIGHTNESS_DAY=0.12` (this is today's `BRIGHTNESS`; keep `BRIGHTNESS` name as the day value so existing comments stay true), `BRIGHTNESS_NIGHT=0.04`, `NIGHT_START_HOUR=22`, `NIGHT_END_HOUR=7`, `OFF_START_HOUR=0`, `OFF_END_HOUR=6` (brightness 0.0 during off window). Document in the header block.
- `tick()` (called from every `check()`, so flight_wall gets it too): at most once per 30 s compute local hour via `time_common`; set `display.brightness`; if time unknown -> day brightness. `tick()` is also where hourly time resync is triggered.
- Pure function `brightness_for_hour(h)` unit-tested.

**USER TEST (together with Phase 1/2):** temporarily set `NIGHT_START_HOUR` to the current hour to see dimming.

---
## Phase 4 – Sports tracker (`sports_tracker.py`, pure logic in `sports_logic.py`)

### Verified findings that drive the design
- **ESPN `teams/{id}` `nextEvent` is NOT reliable** (22 KB each): for DAL it returned a *finished* game from Oct 8 (state `post`) days later; for the Devils it skipped a game that was LIVE. Do **not** use it for schedule/live state. Season-over detection via ESPN: NYY `nextEvent` = `2027-02-19` "TBD" (spring training).
- ESPN scoreboard (180 KB+), schedule (277 KB-1.1 MB), standings (157 KB), scoreboard header (255 KB), NHL scoreboard (135-315 KB) are **too big - never fetch**.
- Use **a small purpose-built source per league**:

| Team | Source | Size |
|---|---|---|
| Cowboys (NFL) | ESPN **core** API (below) | ~2 KB + 13 KB once + ~1 KB per poll |
| Devils (NHL) | official `https://api-web.nhle.com/v1/...` | 5.6 KB week schedule, 4.7 KB landing, 58 KB standings every 30 min |
| Yankees (MLB) | official `https://statsapi.mlb.com/api/v1/...` | <3 KB schedule, ~13 KB filtered standings |

### Normalized per-team record (the only thing the UI sees)
```python
{"state": "live"|"pre"|"final"|"off",   # off = season over
 "abbr": "DAL", "opp": "GB", "home": False,
 "my": 17, "their": 14,                  # ints, None if pre
 "status": "Q3 4:12",                    # live/final text, <=10 chars
 "start_utc": 1792xxxxxx,                # pre
 "record": "2-3", "rank": "#2 NFCE",     # rank may be None
 "fetched": monotonic_seconds}
```
Adapters (`fetch_dal()`, `fetch_njd()`, `fetch_nyy()`) live in `sports_tracker.py` (network); the normalization of raw JSON -> record lives in `sports_logic.py` as pure functions (`norm_nfl(...)`, `norm_nhl(...)`, `norm_mlb(...)`) so they can be unit-tested against saved sample JSON (store 3 trimmed samples in `tools/samples/`, **not root**).

### NFL adapter - Dallas (ESPN team id 6) via core API
Season year `Y` = current year if month >= 3 else year-1 (NFL 2026 season now).
1. `GET https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{Y}/types/2/teams/6/events` -> `items[].$ref` = **17 regular-season events in chronological order** (verified; 1.9 KB). Event id = number in the ref before `?`. Cache for the whole session.
2. `GET .../seasons/{Y}/types/2/teams/6/records/0` -> `summary` ("2-3" or "2-3-1"). `played = sum of the ints`. Poll every 10 min.
3. `played >= 17` -> `off` (playoffs: out of scope; document). Else current game = `events[played]` (a live game isn't counted in the record yet; a just-finished game stays `events[played]` until ESPN updates the record - good, shows FINAL).
4. `GET .../nfl/events/{id}?lang=en&region=us` (13 KB, **cache per event id**): read `date` (ISO UTC), `shortName` ("DAL @ GB"; opponent abbr = the other side), `competitions[0].competitors[]` -> `id` and `homeAway` (`UNVERIFIED` exact keys: **inspect the real response and fix paths**).
5. Status (poll 15 s only when state is `in` or kickoff within 30 min; else every 5 min): `GET .../events/{id}/competitions/{id}/status` -> `type.state` (`pre`/`in`/`post`), `displayClock`, `period`, `type.shortDetail`. Scores: `GET .../competitions/{id}/competitors/{teamId}/score` -> `value` (float -> int), once for team 6 and once for opponent id.
6. Rank: `UNVERIFIED` - try division standings in core API (`.../seasons/{Y}/types/2/groups/{divisionId}/standings/0`; groups list is `.../types/2/groups` -> ids 7 and 8 are the conferences). If not workable in 20 min, **ship record only** (`rank=None`). Do not fall back to the 157 KB standings endpoint.

### NHL adapter - Devils (`NJD`)
1. `GET https://api-web.nhle.com/v1/club-schedule/NJD/week/now` -> `games[]` with `gameState` (`FUT`,`PRE`,`LIVE`,`CRIT`,`OFF`,`FINAL`), `startTimeUTC`, `awayTeam{abbrev,score}`, `homeTeam{...}`, `periodDescriptor{number,periodType}`, `id` (verified: a Devils game was `LIVE` 1-0 on 2026-10-13). Also `nextStartDate`.
2. Choose: first `LIVE`/`CRIT`; else the first game not final (`FUT`/`PRE`); else the most recent final within 3 h; else if no future game this week, query `club-schedule/NJD/week/{nextStartDate}` (once, max 2 hops); if `nextStartDate` is missing/null -> `off`.
3. While live: `GET .../gamecenter/{id}/landing` (4.7 KB) every 20 s -> `clock.timeRemaining`, `clock.inIntermission`, `periodDescriptor.number` -> status text `P1 13:44`, `OT`, `SO`, `INT` (intermission).
4. Record/rank: `GET https://api-web.nhle.com/v1/standings/now` (58 KB; **at most every 30 min**, then `gc.collect()`) -> entry with `teamAbbrev.default == "NJD"`: `wins`, `losses`, `otLosses`, `points`, `divisionSequence` (verified: 2-3-0, 4 pts, divSeq 7), `divisionName` ("Metropolitan"). Record string `W-L-OTL`. If the fetch fails keep the last value.

### MLB adapter - Yankees (team id 147)
1. `GET https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId=147&startDate=<today>&endDate=<today+7>&hydrate=linescore,team` (use ET date from `time_common`; if time unknown use only the live/yesterday-less call below). Games: `status.abstractGameState` (`Preview`/`Live`/`Final`), `gameDate` (UTC ISO), `teams.away/home` -> `score`, `team.abbreviation`; `linescore.currentInning`, `linescore.inningHalf` (`Top`/`Bottom`). Status text `T5`/`B5`, `FINAL`, `F/10` for extras. (`UNVERIFIED` against a live game - verify field names with `tools/check_apis.py` on the next game day.)
2. No game within 7 days: widen to 30 days; none -> `off` (also confirm with ESPN `teams/nyy` `nextEvent.date` being > 30 days away or season type preseason). Verified today: schedule for today was empty (0 games).
3. Standings (every 30 min): `GET https://statsapi.mlb.com/api/v1/standings?leagueId=103&season=<Y>&standingsTypes=regularSeason&fields=records,division,id,teamRecords,team,id,divisionRank,gamesBack,wins,losses` -> 12.8 KB (verified; the `fields` filter works). Find `team.id == 147`: `divisionRank`, `wins`, `losses`. Record from here (`93-68`).

### Screens (3 rows, <=10 chars; center with `center_x`)
- **Live:** row1 `DAL@GB` (road team first; my team abbr in white/accent, opponent white) - row2 score `17-14`, `my-their`, green leading / red trailing / yellow tied - row3 status `Q3 4:12`. (NFL: `Q1..Q4`, `OT`, `HALF`; MLB `T5`/`B5`; NHL `P1 13:44`.)
- **Pre:** row1 `DAL@GB` - row2 `SUN 1:00P` - row3 `OCT 18`; if the game is today row3 `TODAY`; if time unknown row2 shows date only.
- **Final:** row1 matchup - row2 score (green win / red loss) - row3 `FINAL` (`FINAL OT`, `FINAL SO`). Show for up to 3 h after the end, then show next game.
- **Season over (`off`):** row1 team name (`YANKEES`, `DEVILS`, `COWBOYS`) - row2 `SEASON` - row3 `OVER 93-68` (record, <=10 chars; omit record if too long). Use a dim gray `0x888888` for rows 2-3 so it reads as "inactive".
- **Standings page:** row1 team name - row2 record (`2-3` / `2-3-0`) - row3 `#2 NFCE` style (`#`+rank+short division: `NFCE`, `ALE`, `METRO`; map table in `sports_logic.py`). Omit page if rank unknown.
- Error: row1 team, row2 `NO DATA`; keep showing stale data up to 5 min first.

### Rotation rules (user spec)
1. Compute `live = [teams with state == "live"]`. If any: rotate **only among live teams'** game screens every 8 s (one live team = stay on it). No standings pages.
2. If none live: rotate through all three teams; per team show game page 5 s then (if available) standings page 4 s. A team in `off` shows its "season over" page, same timing.
3. Score change on a live team: flash row 2 white/yellow for 3 s.
4. Loop like `bus_tracker.py`: `check_switch_button()` every tick, `display.refresh(minimum_frames_per_second=0)`, `time.sleep(0.1)`. Never block more than one HTTP call between checks; poll teams one at a time on staggered timers (round-robin) instead of all three in one burst.
5. `gc.collect()` after each parse; always `r.close()`.
6. Auto-jumping to the sports app when a game starts is out of scope (single-threaded board).

**test_logic cases:** `norm_nfl` for (pre / in / post / played>=17), NHL game choice (live beats future; none -> off; final within 3 h), MLB inning text, rank/record formatting, rotation selector given sample states (live only vs all), flash logic.

**USER TEST:** all three teams page through; check Devils (live tonight/next game), Yankees `SEASON OVER`, Cowboys `DAL@GB SUN 1:00P` (next game Oct 18). Verify Cowboys' Sunday live path next game day (flag as unverified until then).

---
## Phase 5 – Sleeper fantasy (`sleeper_matchup.py`, pure logic in `sleeper_logic.py`)

### Corrections found in review (important)
- The username is **`pinec0ne` (zero)**. `pinecone` (letter o) is a *different* Sleeper account that is **not in your league**. Using `pinecone` would silently find no roster. Resolved IDs (verified):
  - league `1389359956657967104` "Loser eats an egg", 12 teams, in_season, 2026
  - `pinec0ne` -> user_id `735942590872018944` -> **roster_id 4** ("Tony Romo's DUI Mugshot"), 3-2, `fpts` 597.18
  - Resolve at runtime (don't hardcode IDs): `GET /v1/user/pinec0ne`, then `GET /v1/league/{L}/rosters` and match `owner_id` (also check `co_owners`). If no roster matches show `NOT IN`/`LEAGUE`.
- Starter slots (10): `QB,RB,RB,WR,WR,TE,FLEX,FLEX,K,DEF`. Empty slot id is `"0"`. DEF/K ids: DEF is the team abbreviation (e.g. `SEA`).
- Sleeper `state` already says `week:6` on Tuesday after Monday night (`display_week:5`); **use `week`**. Matchups for week 6 exist but `points` are 0.0 and the **opponent's `starters` is empty** until they set a lineup (handle: `ytp = "?"`).

### Endpoints (all keyless; sizes verified)
1. `https://api.sleeper.app/v1/state/nfl` -> `week`, `season_type` (`regular` else show `OFFSEASON`).
2. `https://api.sleeper.app/v1/league/{L}/rosters` (cache; refresh records every 10 min) -> per roster `owner_id`, `settings{wins,losses,ties,fpts,fpts_decimal}` (fpts = `597.18` = `fpts + fpts_decimal/100`).
3. `https://api.sleeper.app/v1/league/{L}/users` (cache once) -> `display_name`, `metadata.team_name`.
4. `https://api.sleeper.app/v1/league/{L}/matchups/{week}` (~6 KB) -> two entries share `matchup_id`: `roster_id`, `points`, `starters` (list of ids), `starters_points`.
5. **NFL schedule status for YTP:** `https://api.sleeper.app/schedule/nfl/regular/{season}` (27 KB, list of `{week, date, home, away, status, game_id}`; `status` currently `complete` / `pre_game`; the in-progress value is `UNVERIFIED` -> treat anything not in {`complete`,`pre_game`} as *live/started*). Poll every 5 min (60 s on Sun/Mon/Thu when any week game is not `pre_game`/`complete`).
6. **Player -> NFL team:** `https://api.sleeper.com/players/nfl/{player_id}` (note `.com`, **1.1 KB per player**, verified: 4046 -> `team: "KC"`, also `position`, `last_name`, `injury_status`). Cache `player_id -> team` for the session in a module-level dict in `network_common`-style shared cache (survives app swaps). Never use `/v1/players/nfl` (5 MB). ~20 calls the first time, then free. This endpoint is unofficial: on failure show `?` for YTP, never crash.

### Logic (all in `sleeper_logic.py`, pure)
- **YTP (yet-to-play) for a roster** = count of non-`"0"` starters whose NFL team has a game this week with `status == "pre_game"`. (Bye = not YTP. Started/complete = not YTP.)
- **Win probability:** per-slot expected points `avg = (fpts_total / games) / 10` where `games = W+L+T` (default `avg = 10.0` if `games == 0`). `proj = points + ytp * avg` for each side. `sigma = 6.0 * sqrt(max(ytp_me + ytp_opp, 1))`. `p = 1 / (1 + exp(-1.702 * (proj_me - proj_opp) / sigma))` (logistic approximation of the normal CDF; no `math.erf`). If `ytp_me + ytp_opp == 0`: `p = 1.0 / 0.0 / 0.5` by comparing `points`. Display `int(round(p*100))` clamped to 1..99 unless the game is decided (then 100 or 0 - 3-char `100%` is fine within the row budget below).
- **Rank:** sort the 12 rosters by (wins desc, fpts desc); my 1-based position.
- **Test cases:** p == 0.5 for identical teams with equal ytp; p -> 1.0/0.0 when ytp both 0 and points differ; opponent starters empty -> `ytp_opp = None` and `p` computed with default 10 slots; ytp counts with synthetic schedule (pre_game / complete / bye); rank ordering with ties on wins; `fpts` decimal combination.

### Screens (rotate every 6 s; 3 rows, <=10 chars)
- **A (main):** row1 `WK6 W:62%` (my win prob; `WK6 W:100%` is exactly 10 chars) - row2 `98.4-87.1` (my points - opponent points, 1 decimal; if >9 chars shrink to integers; two Labels so my score is green when leading, red when trailing, white tied) - row3 `YTP 3 v 5` (me v opponent; `?` if unknown).
- **B (opponent):** row1 `VS` + record, e.g. `VS 1-4` - row2 opponent `display_name[:10]` - row3 `WK6` + kickoff-free text `SUN 10/18`-style only if cheap; otherwise `UP NEXT`. (Keep it simple: skip row3 detail if it costs extra calls.)
- **C (me):** row1 `PINEC0NE` - row2 `3-2 597.2` - row3 `#6 OF 12`.
- Pre-lineup / week not started: A still shows (`0.0-0.0`, win% from season averages, `YTP 10 v ?`).
- Errors: `NO DATA` / `RETRYING`; `OFFSEASON` if `season_type != regular`.
- Poll: matchup 60 s (20 s when any game live per schedule); show stale values for up to 5 min on failure.
- Add config at top of the file: `SLEEPER_LEAGUE_ID = os.getenv("SLEEPER_LEAGUE_ID", "1389359956657967104")`, `SLEEPER_USERNAME = os.getenv("SLEEPER_USERNAME", "pinec0ne")` (document in the header block; user may append these to `settings.toml`).
- **Out of scope (not feasible on this board):** projections (public API has none), injury/bye flags per player (needs 5 MB file or many calls), live per-player breakdown.

**USER TEST:** screens A/B/C show correct teams (user = roster 4). During the next live Sunday/Thu game, check YTP counts decrease and record the actual in-progress `status` string from the schedule endpoint (update the `UNVERIFIED` note).

---
## Phase 6 – Bus tracker upgrades (`bus_tracker.py`)
Keep all existing parsing/color/ticker logic (`classify_status`, `time_color_for`, `rebuild_ticker`, `advance_scroll`).
1. **Remove noise:** gate `print("NJT raw response:", data)` behind `DEBUG = False`.
2. **Leave-now cue** (user approved): config `WALK_MINUTES = 4` (**default is a guess - tell the user to set their real walking time**). Using the numeric minutes from `classify_status`:
   - Next *catchable* bus = first trip with `minutes >= WALK_MINUTES` (skip buses that can't be caught from row 2; they stay out of the ticker too, or stay in gray - choose gray `0x888888`).
   - If the catchable bus has `minutes <= WALK_MINUTES + 1` blink row 1 between the stop label and `LEAVE NOW` (red, 0.5 s toggle) - `LEAVE NOW` is 9 chars, fits.
   - Imminent/`DUE` (-1) and clock-time (9999) behave as today (no cue for 9999).
3. **Multiple stops:** `STOPS = [{"id": "21061", "label": "PLSD+BWRS", "walk_min": 4}]` (single entry now; code must work for N>=1). With N>1 poll each in turn and rotate display every `ROTATE_STOP_SECONDS = 8`. Don't refactor beyond what is needed; the file is top-level code - wrap per-stop state in a small dict.
4. **Service alerts: time-box 15 min.** Read NJT BUSDV2 docs (`developer.njtransit.com`) for an alerts/messages method. If one exists, append the text to the row-3 ticker. If not, **drop it and say so**; do not invent an endpoint.
5. NJT token: cache it in `network_common` module state (survives app swaps) to avoid re-auth on every entry.
6. Update header comments (new settings, UP/DOWN).

**USER TEST:** colors unchanged, `LEAVE NOW` appears when a bus is ~`WALK_MINUTES` away, ticker still scrolls.

---
## Phase 7 – Idle clock + weather (`idle_clock.py`)
- Rows: row1 date `TUE 10/13`; row2 time `6:04P` (use `time_common.fmt_clock`); row3 weather `67F CLEAR`.
- Weather (verified keyless): `https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&current=temperature_2m,weather_code&temperature_unit=fahrenheit` -> `current.temperature_2m`, `current.weather_code`. Poll every 15 min. Use the user's flight-tracker coordinates already in the repo: `HOME_LAT=40.7178`, `HOME_LON=-74.0431` (**copy the constants** into `idle_clock.py`; do NOT import `flight_wall` - importing it runs its infinite loop). Map WMO codes -> <=6-char words (`CLEAR`, `CLOUDY`, `FOG`, `RAIN`, `SNOW`, `STORM`).
- If time unknown: show `NO CLOCK`.

## Phase 8 – Optional auto-rotate (default OFF)
`AUTO_ROTATE_SECONDS = 0` in `app_switch.py`. When > 0, `check()` raises `SwitchRequested(+1)` after that many seconds since the app started, unless `app_switch.hold_rotation` is True (sports app sets it while any team is live). Button press resets it. Can't be aware of a flight on screen (file untouched), so keep default 0 and say so in the header comment.

---
## Execution order & rules
1. Phase 0 -> 1 -> **USER TEST** -> 2+3 -> USER TEST -> 4 -> USER TEST -> 5 -> USER TEST -> 6 -> 7 -> 8.
2. After each phase: `python tools/test_logic.py`, `python tools/check_apis.py`; re-read changed files for CircuitPython compatibility; add the new file to `PROGRAMS` only when its phase is done.
3. Never edit `flight_wall.py`; confirm with `fc /b docs\backup\flight_wall.py.orig flight_wall.py`.
4. Final report: what changed, what was skipped (alerts if no endpoint, playoffs, per-player flags, auto-jump), `UNVERIFIED` items still open, assumptions (`WALK_MINUTES`, lat/lon), and the exact list of files to copy to the board (root `*.py` + `lib/`; not `docs/`/`tools/`).

## Open items the implementer must verify (do not guess)
- ESPN core event JSON paths (`competitions[0].competitors[]` keys) and `.../status` shape - fix in code + `check_apis.py`.
- Sleeper schedule `status` value during a live game.
- MLB schedule/linescore field names on a game day.
- NFL division rank source (optional).
- `keypad.Keys` pull/polarity on the MatrixPortal S3 buttons (existing code treats pressed = `value == False` with pull-up; `value_when_pressed=False, pull=True` matches that). If events never arrive, fall back to polled `DigitalInOut` created once at module level.
- Free heap after loading each app (`gc.mem_free()`); the 150000 threshold in the runner is a guess.
