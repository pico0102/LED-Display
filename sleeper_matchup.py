# sleeper_matchup.py -- Sleeper Fantasy Football Matchup Tracker
# Displays current matchup status, live win probability, scores,
# opponent preview, yet-to-play (YTP) counts, and league standing.
#
# Rotates every 6 seconds through 3 screens:
#   Screen A: Matchup win probability, live points, yet-to-play counts (YTP)
#   Screen B: Opponent record, display name, upcoming game preview
#   Screen C: User profile, record, total points, and league rank
#
# Press the board's UP or DOWN button to cycle between apps (see app_switch.py).
#
# ============================================================
# WHERE TO CONFIGURE THINGS
# ============================================================
#   Sleeper league ID ................... SLEEPER_LEAGUE_ID (settings.toml)
#   Sleeper username .................... SLEEPER_USERNAME (settings.toml)
#   Screen rotation interval (seconds) .. ROTATE_SECONDS (default 6)
# ============================================================

import os
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
import sleeper_logic

# Settings
SLEEPER_LEAGUE_ID = os.getenv("SLEEPER_LEAGUE_ID", "1389359956657967104")
SLEEPER_USERNAME = os.getenv("SLEEPER_USERNAME", "pinec0ne")
ROTATE_SECONDS = 6

POLL_MATCHUP_INTERVAL = 60
POLL_SCHEDULE_INTERVAL = 300
POLL_ROSTERS_INTERVAL = 600

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
    """Update display rows with centered text and colors."""
    lbl_r1.text = str(r1)[:10]
    lbl_r1.color = c1
    lbl_r1.x = center_x(lbl_r1.text)

    lbl_r2.text = str(r2)[:10]
    lbl_r2.color = c2
    lbl_r2.x = center_x(lbl_r2.text)

    lbl_r3.text = str(r3)[:10]
    lbl_r3.color = c3
    lbl_r3.x = center_x(lbl_r3.text)


set_screen_text("SLEEPER", "LOADING..", "")

session = connect_wifi_and_get_session()
check_switch_button = app_switch.make_switch_button("sleeper_matchup.py")

# Session state caches
_user_id = None
_users_cache = {}
_rosters_cache = None
_rosters_last_poll = 0
_schedule_cache = None
_schedule_last_poll = 0
_matchups_cache = None
_matchups_last_poll = 0
_player_teams_cache = {}
_state_cache = None


def fetch_json(url):
    """Safely fetch JSON over HTTP with closed response and memory cleanup."""
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


def resolve_user_and_league():
    """Initial user and league metadata setup."""
    global _user_id, _users_cache, _state_cache
    if _state_cache is None:
        _state_cache = fetch_json("https://api.sleeper.app/v1/state/nfl")

    if _user_id is None:
        user_data = fetch_json(f"https://api.sleeper.app/v1/user/{SLEEPER_USERNAME}")
        if user_data:
            _user_id = user_data.get("user_id")

    if not _users_cache:
        users_list = fetch_json(f"https://api.sleeper.app/v1/league/{SLEEPER_LEAGUE_ID}/users")
        if users_list:
            _users_cache = {u.get("user_id"): u for u in users_list if "user_id" in u}


def get_player_team(pid):
    """Lookup NFL team abbreviation for player ID (cached in session dict)."""
    global _player_teams_cache
    if not pid or pid == "0":
        return None

    pid_str = str(pid)
    # Direct defense team code
    if len(pid_str) <= 3 and pid_str.isupper():
        return pid_str

    if pid_str in _player_teams_cache:
        return _player_teams_cache[pid_str]

    # Fetch from lightweight unofficial player endpoint (1.1 KB)
    url = f"https://api.sleeper.com/players/nfl/{pid_str}"
    p_data = fetch_json(url)
    if p_data and p_data.get("team"):
        team = p_data.get("team")
        _player_teams_cache[pid_str] = team
        return team
    return None


resolve_user_and_league()

# Rotation tracking
current_screen = 0
last_screen_change = time.monotonic()

while True:
    check_switch_button()
    now_mono = time.monotonic()

    # 1. Periodically refresh state/week
    if _state_cache is None or now_mono - _matchups_last_poll >= 1800:
        s = fetch_json("https://api.sleeper.app/v1/state/nfl")
        if s:
            _state_cache = s

    week = _state_cache.get("week", 1) if _state_cache else 1
    season_type = _state_cache.get("season_type", "regular") if _state_cache else "regular"
    season = _state_cache.get("season", "2026") if _state_cache else "2026"

    # Offseason screen
    if season_type != "regular":
        set_screen_text("SLEEPER", "OFFSEASON", "SEE YA SOON", WHITE, WHITE, sleeper_logic.COLOR_GRAY)
        time.sleep(1.0)
        continue

    # 2. Refresh rosters (every 10 min)
    if _rosters_cache is None or (now_mono - _rosters_last_poll) >= POLL_ROSTERS_INTERVAL:
        r_list = fetch_json(f"https://api.sleeper.app/v1/league/{SLEEPER_LEAGUE_ID}/rosters")
        if r_list:
            _rosters_cache = r_list
            _rosters_last_poll = now_mono
        check_switch_button()

    # 3. Refresh NFL schedule (every 5 min)
    if _schedule_cache is None or (now_mono - _schedule_last_poll) >= POLL_SCHEDULE_INTERVAL:
        sch = fetch_json(f"https://api.sleeper.app/schedule/nfl/regular/{season}")
        if sch:
            _schedule_cache = sch
            _schedule_last_poll = now_mono
        check_switch_button()

    # 4. Refresh matchups (every 60 sec)
    if _matchups_cache is None or (now_mono - _matchups_last_poll) >= POLL_MATCHUP_INTERVAL:
        m_list = fetch_json(f"https://api.sleeper.app/v1/league/{SLEEPER_LEAGUE_ID}/matchups/{week}")
        if m_list:
            _matchups_cache = m_list
            _matchups_last_poll = now_mono
        check_switch_button()

    # Identify user roster and opponent
    my_roster = None
    if _rosters_cache and _user_id:
        for r in _rosters_cache:
            if r.get("owner_id") == _user_id or (_user_id in (r.get("co_owners") or [])):
                my_roster = r
                break

    if not my_roster:
        set_screen_text("NOT IN", "LEAGUE", "CHECK USER", WHITE, sleeper_logic.COLOR_RED, WHITE)
        time.sleep(0.5)
        continue

    my_roster_id = my_roster.get("roster_id")
    my_st = my_roster.get("settings", {})
    my_record = f"{my_st.get('wins', 0)}-{my_st.get('losses', 0)}"
    my_games = my_st.get("wins", 0) + my_st.get("losses", 0) + my_st.get("ties", 0)
    my_fpts_total = sleeper_logic.calc_fpts(my_st)
    rank, total_teams = sleeper_logic.calc_rank(_rosters_cache, my_roster_id)

    # Matchup details
    my_match = None
    opp_match = None
    if _matchups_cache:
        for m in _matchups_cache:
            if m.get("roster_id") == my_roster_id:
                my_match = m
                break
        if my_match:
            mid = my_match.get("matchup_id")
            for m in _matchups_cache:
                if m.get("matchup_id") == mid and m.get("roster_id") != my_roster_id:
                    opp_match = m
                    break

    my_pts = float(my_match.get("points", 0.0)) if my_match else 0.0
    opp_pts = float(opp_match.get("points", 0.0)) if opp_match else 0.0

    # Opponent roster details
    opp_roster = None
    opp_record = "?-?"
    opp_games = 0
    opp_fpts_total = 0.0
    if opp_match and _rosters_cache:
        for r in _rosters_cache:
            if r.get("roster_id") == opp_match.get("roster_id"):
                opp_roster = r
                break
        if opp_roster:
            ost = opp_roster.get("settings", {})
            opp_record = f"{ost.get('wins', 0)}-{ost.get('losses', 0)}"
            opp_games = ost.get("wins", 0) + ost.get("losses", 0) + ost.get("ties", 0)
            opp_fpts_total = sleeper_logic.calc_fpts(ost)

    opp_user = _users_cache.get(opp_roster.get("owner_id")) if opp_roster else None
    opp_name = opp_user.get("display_name", "OPPONENT") if opp_user else "OPPONENT"

    # Resolve starter player teams (at most 2 uncached players per tick to keep display responsive)
    my_starters = my_match.get("starters", []) if my_match else []
    opp_starters = opp_match.get("starters", []) if opp_match else []
    uncached_count = 0
    for pid in (my_starters + opp_starters):
        if pid and pid != "0" and str(pid) not in _player_teams_cache:
            get_player_team(pid)
            uncached_count += 1
            if uncached_count >= 2:
                break

    # Calculate YTP and Win Probability
    my_ytp = sleeper_logic.calc_ytp(my_starters, _schedule_cache, week, _player_teams_cache)
    opp_ytp = sleeper_logic.calc_ytp(opp_starters, _schedule_cache, week, _player_teams_cache)
    win_prob = sleeper_logic.calc_win_prob(
        my_pts, opp_pts, my_ytp, opp_ytp,
        my_fpts_total, my_games, opp_fpts_total, opp_games
    )

    # Rotate screens every ROTATE_SECONDS
    if now_mono - last_screen_change >= ROTATE_SECONDS:
        current_screen = (current_screen + 1) % 3
        last_screen_change = now_mono

    # Render Screen
    if current_screen == 0:
        r1, r2, r3, c1, c2, c3 = sleeper_logic.format_screen_a(week, win_prob, my_pts, opp_pts, my_ytp, opp_ytp)
        set_screen_text(r1, r2, r3, c1, c2, c3)
    elif current_screen == 1:
        r1, r2, r3, c1, c2, c3 = sleeper_logic.format_screen_b(opp_record, opp_name, week)
        set_screen_text(r1, r2, r3, c1, c2, c3)
    else:
        r1, r2, r3, c1, c2, c3 = sleeper_logic.format_screen_c(SLEEPER_USERNAME, my_record, my_fpts_total, rank, total_teams)
        set_screen_text(r1, r2, r3, c1, c2, c3)

    time.sleep(0.1)
