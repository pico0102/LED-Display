# sports_tracker.py -- Sports Score & Schedule Tracker
# Cycles through Cowboys (NFL), Devils (NHL), and Yankees (MLB).
#
# Shows live scores with period/clock, upcoming game dates/times,
# finals, division standings, or "season over" when inactive.
# Live games take priority and rotate among live teams only.
#
# Press the board's UP or DOWN button to cycle between apps (see app_switch.py).
#
# ============================================================
# WHERE TO CONFIGURE THINGS
# ============================================================
#   Screen rotation time for live games ... ROT_LIVE_SECONDS (default 8)
#   Screen rotation time for games ....... ROT_GAME_SECONDS (default 5)
#   Screen rotation time for standings ... ROT_STANDINGS_SECONDS (default 4)
#   Score change flash duration .......... FLASH_SECONDS (default 3.0)
#   NHL / MLB standings refresh interval . STANDINGS_REFRESH_SECONDS (default 1800)
# ============================================================

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
import sports_logic

# Screen rotation settings
ROT_LIVE_SECONDS = 8
ROT_GAME_SECONDS = 5
ROT_STANDINGS_SECONDS = 4
FLASH_SECONDS = 3.0
STANDINGS_REFRESH_SECONDS = 1800

# Polling intervals (seconds)
POLL_LIVE = 20
POLL_PRE = 300
POLL_OFF = 1800

# Display setup
display = init_matrix_display()
main_group = displayio.Group()

lbl_r1 = Label(terminalio.FONT, color=WHITE, x=0, y=ROW_Y[0])
lbl_r2 = Label(terminalio.FONT, color=WHITE, x=0, y=ROW_Y[1])
lbl_r3 = Label(terminalio.FONT, color=WHITE, x=0, y=ROW_Y[2])

for lbl in (lbl_r1, lbl_r2, lbl_r3):
    main_group.append(lbl)

display.root_group = main_group


def set_screen_text(r1, r2, r3, c1=WHITE, c2=WHITE, c3=WHITE):
    """Update all 3 screen labels with text and colors."""
    lbl_r1.text = str(r1)[:10]
    lbl_r1.color = c1
    lbl_r1.x = center_x(lbl_r1.text)

    lbl_r2.text = str(r2)[:10]
    lbl_r2.color = c2
    lbl_r2.x = center_x(lbl_r2.text)

    lbl_r3.text = str(r3)[:10]
    lbl_r3.color = c3
    lbl_r3.x = center_x(lbl_r3.text)


set_screen_text("SPORTS", "LOADING..", "")

session = connect_wifi_and_get_session()
check_switch_button = app_switch.make_switch_button("sports_tracker.py")

# Session caches
_dal_events_cache = None
_dal_event_detail_cache = {}
_dal_record_cache = None
_dal_record_time = 0

_njd_standings_cache = None
_njd_standings_time = 0

_nyy_standings_cache = None
_nyy_standings_time = 0


def fetch_json(url):
    """Safely fetch JSON over HTTP and close response."""
    r = None
    try:
        r = session.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        print("HTTP error:", url[:50], e)
        return None
    finally:
        if r is not None:
            try:
                r.close()
            except Exception:
                pass
        gc.collect()


def get_dal_data(now_utc):
    """Fetch Dallas Cowboys NFL data from ESPN Core API."""
    global _dal_events_cache, _dal_record_cache, _dal_record_time
    now_mono = time.monotonic()
    year = 2026

    # 1. Events list (cached for session)
    if _dal_events_cache is None:
        url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{year}/types/2/teams/6/events"
        data = fetch_json(url)
        if data:
            _dal_events_cache = data.get("items", [])

    # 2. Record (polled every 10 min)
    if _dal_record_cache is None or (now_mono - _dal_record_time) > 600:
        url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{year}/types/2/teams/6/records/0"
        rec = fetch_json(url)
        if rec:
            _dal_record_cache = rec
            _dal_record_time = now_mono

    if not _dal_events_cache or not _dal_record_cache:
        return {"state": "off", "abbr": "DAL", "record": "2-3", "rank": "#2 NFCE"}

    summary = _dal_record_cache.get("summary", "0-0")
    try:
        played = sum(int(p) for p in summary.split("-"))
    except Exception:
        played = 0

    if played >= 17 or played >= len(_dal_events_cache):
        return sports_logic.norm_nfl(_dal_record_cache, None, None, rank=2)

    event_ref = _dal_events_cache[played].get("$ref")
    if not event_ref:
        return sports_logic.norm_nfl(_dal_record_cache, None, None, rank=2)

    ev_id = str(_dal_events_cache[played].get("id", played))
    if ev_id not in _dal_event_detail_cache:
        ev_data = fetch_json(event_ref)
        if ev_data:
            _dal_event_detail_cache[ev_id] = ev_data
    event_data = _dal_event_detail_cache.get(ev_id)
    if not event_data:
        return sports_logic.norm_nfl(_dal_record_cache, None, None, rank=2)

    status_data = None
    comps = event_data.get("competitions", [])
    if comps:
        status_ref = comps[0].get("status", {}).get("$ref")
        if status_ref:
            status_data = fetch_json(status_ref)

    my_score = None
    opp_score = None
    if status_data and status_data.get("type", {}).get("state") in ("in", "post"):
        ev_num = event_data.get("id")
        opp_id = None
        if comps:
            for c in comps[0].get("competitors", []):
                if str(c.get("id")) != "6":
                    opp_id = str(c.get("id"))
                    break
        my_url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{ev_num}/competitions/{ev_num}/competitors/6/score?lang=en&region=us"
        s1 = fetch_json(my_url)
        if s1:
            my_score = s1.get("value")
        if opp_id:
            opp_url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{ev_num}/competitions/{ev_num}/competitors/{opp_id}/score?lang=en&region=us"
            s2 = fetch_json(opp_url)
            if s2:
                opp_score = s2.get("value")

    return sports_logic.norm_nfl(_dal_record_cache, event_data, status_data, my_score, opp_score, rank=2)


def get_njd_data(now_utc):
    """Fetch NJ Devils NHL data from official NHL API."""
    global _njd_standings_cache, _njd_standings_time
    now_mono = time.monotonic()

    # Standings (every 30 min)
    if _njd_standings_cache is None or (now_mono - _njd_standings_time) > STANDINGS_REFRESH_SECONDS:
        st_data = fetch_json("https://api-web.nhle.com/v1/standings/now")
        if st_data:
            _njd_standings_cache = st_data
            _njd_standings_time = now_mono

    sched_data = fetch_json("https://api-web.nhle.com/v1/club-schedule/NJD/week/now")
    landing_data = None
    if sched_data and sched_data.get("games"):
        for g in sched_data["games"]:
            if g.get("gameState") in ("LIVE", "CRIT"):
                landing_data = fetch_json(f"https://api-web.nhle.com/v1/gamecenter/{g['id']}/landing")
                break

    return sports_logic.norm_nhl(sched_data, landing_data, _njd_standings_cache, now_utc)


def get_nyy_data(now_utc):
    """Fetch NY Yankees MLB data from StatsAPI."""
    global _nyy_standings_cache, _nyy_standings_time
    now_mono = time.monotonic()

    # Standings (every 30 min)
    if _nyy_standings_cache is None or (now_mono - _nyy_standings_time) > STANDINGS_REFRESH_SECONDS:
        url = "https://statsapi.mlb.com/api/v1/standings?leagueId=103&season=2026&standingsTypes=regularSeason&fields=records,division,id,teamRecords,team,id,divisionRank,gamesBack,wins,losses"
        st = fetch_json(url)
        if st:
            _nyy_standings_cache = st
            _nyy_standings_time = now_mono

    # Schedule: today to +7 days
    today_str = "2026-10-13"
    if now_utc is not None:
        y, m, d = time_common.civil_from_days((now_utc + time_common.eastern_offset(now_utc)) // 86400)
        today_str = f"{y:04d}-{m:02d}-{d:02d}"

    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId=147&startDate={today_str}&endDate={today_str}&hydrate=linescore,team"
    sched = fetch_json(url)
    return sports_logic.norm_mlb(sched, _nyy_standings_cache, now_utc)


# State tracking
team_order = ["NJD", "DAL", "NYY"]
teams_data = {}
last_poll = {"DAL": 0, "NJD": 0, "NYY": 0}
prev_scores = {"DAL": None, "NJD": None, "NYY": None}
score_flash_until = 0

# Initial fetch for all teams
for t in team_order:
    check_switch_button()
    now_utc = time_common.utc_now()
    if t == "DAL":
        rec = get_dal_data(now_utc)
    elif t == "NJD":
        rec = get_njd_data(now_utc)
    else:
        rec = get_nyy_data(now_utc)

    if rec:
        teams_data[t] = rec
        prev_scores[t] = (rec.get("my"), rec.get("their"))
    last_poll[t] = time.monotonic()
    gc.collect()

# Rotation state
screens = []
live_mode = False
current_screen_idx = 0
screen_start_time = time.monotonic()

while True:
    check_switch_button()
    now_mono = time.monotonic()
    now_utc = time_common.utc_now()

    # 1. Round-robin staggered polling
    for t in team_order:
        rec = teams_data.get(t)
        state = rec.get("state", "off") if rec else "off"
        interval = POLL_LIVE if state == "live" else (POLL_PRE if state == "pre" else POLL_OFF)

        if now_mono - last_poll[t] >= interval:
            last_poll[t] = now_mono
            if t == "DAL":
                new_rec = get_dal_data(now_utc)
            elif t == "NJD":
                new_rec = get_njd_data(now_utc)
            else:
                new_rec = get_nyy_data(now_utc)

            check_switch_button()

            if new_rec:
                # Check for score change to trigger flash
                old_s = prev_scores.get(t)
                new_s = (new_rec.get("my"), new_rec.get("their"))
                if new_rec.get("state") == "live" and old_s != new_s and old_s is not None:
                    score_flash_until = now_mono + FLASH_SECONDS
                prev_scores[t] = new_s
                teams_data[t] = new_rec

            gc.collect()
            break  # Poll only ONE team per tick to avoid blocking

    # 2. Update screen rotation schedule
    active_teams = [teams_data[t] for t in team_order if t in teams_data]
    live_mode, new_screens = sports_logic.choose_display_screen(
        active_teams,
        ROT_LIVE_SECONDS,
        ROT_GAME_SECONDS,
        ROT_STANDINGS_SECONDS,
    )
    if not screens or len(screens) != len(new_screens):
        screens = new_screens
        current_screen_idx = 0
        screen_start_time = now_mono

    # Hold Phase 8 auto-rotate if any game is live
    app_switch.hold_rotation = live_mode

    # 3. Advance screen if duration elapsed
    if screens:
        if current_screen_idx >= len(screens):
            current_screen_idx = 0
        screen_type, team_rec, duration = screens[current_screen_idx]

        if now_mono - screen_start_time >= duration:
            current_screen_idx = (current_screen_idx + 1) % len(screens)
            screen_start_time = now_mono
            screen_type, team_rec, duration = screens[current_screen_idx]

        # 4. Render current screen
        if screen_type == "game":
            r1, r2, r3, c1, c2, c3 = sports_logic.format_game_screen(team_rec, now_utc)
            # Handle score change flashing for live games
            if team_rec.get("state") == "live" and now_mono < score_flash_until:
                # Alternate white/yellow every 250ms
                c2 = WHITE if int(now_mono * 4) % 2 == 0 else sports_logic.COLOR_YELLOW
            set_screen_text(r1, r2, r3, c1, c2, c3)
        elif screen_type == "standings":
            res = sports_logic.format_standings_screen(team_rec)
            if res:
                set_screen_text(res[0], res[1], res[2], WHITE, WHITE, WHITE)

    display.refresh(minimum_frames_per_second=0)
    time.sleep(0.1)
