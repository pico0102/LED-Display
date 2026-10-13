# sports_logic.py -- Pure logic for normalizing sports scores, schedules,
# standings, and screen rotation.
# Hardware-free pure Python: safe to import and unit test on desktop.

import time_common

TEAM_NAMES = {
    "DAL": "COWBOYS",
    "NJD": "DEVILS",
    "NYY": "YANKEES",
}

DIVISION_MAP = {
    # NHL
    "Metropolitan": "METRO",
    "Atlantic": "ATL",
    "Central": "CENT",
    "Pacific": "PAC",
    # MLB
    "American League East": "ALE",
    "AL East": "ALE",
    "American League Central": "ALC",
    "AL Central": "ALC",
    "American League West": "ALW",
    "AL West": "ALW",
    "National League East": "NLE",
    "NL East": "NLE",
    "National League Central": "NLC",
    "NL Central": "NLC",
    "National League West": "NLW",
    "NL West": "NLW",
    "East": "ALE",
    # NFL
    "NFC East": "NFCE",
    "NFC North": "NFCN",
    "NFC South": "NFCS",
    "NFC West": "NFCW",
    "AFC East": "AFCE",
    "AFC North": "AFCN",
    "AFC South": "AFCS",
    "AFC West": "AFCW",
}

# Colors
COLOR_WHITE = 0xFFFFFF
COLOR_RED = 0xFF0000
COLOR_YELLOW = 0xFFFF00
COLOR_GREEN = 0x00FF00
COLOR_GRAY = 0x888888


def fmt_rank(rank, div_name):
    """Format '#2 NFCE' style rank string (<=10 chars), or None if unknown."""
    if rank is None:
        return None
    short_div = DIVISION_MAP.get(div_name, div_name[:5] if div_name else "")
    res = f"#{rank} {short_div}".strip()
    return res[:10]


def score_color(my_score, their_score):
    """Determine score text color: green if leading, red if trailing, yellow tied."""
    if my_score is None or their_score is None:
        return COLOR_WHITE
    if my_score > their_score:
        return COLOR_GREEN
    elif my_score < their_score:
        return COLOR_RED
    return COLOR_YELLOW


def norm_nfl(record_data, event_data, status_data, my_score_data=None, opp_score_data=None, rank=None, div_name="NFC East"):
    """Normalize raw NFL ESPN core API data into standard team record."""
    summary = record_data.get("summary", "0-0") if record_data else "0-0"
    try:
        parts = [int(p) for p in summary.split("-")]
        played = sum(parts)
    except Exception:
        played = 0

    if played >= 17:
        return {
            "state": "off",
            "abbr": "DAL",
            "opp": "",
            "home": False,
            "my": None,
            "their": None,
            "status": "",
            "start_utc": None,
            "record": summary,
            "rank": fmt_rank(rank, div_name),
        }

    short_name = event_data.get("shortName", "DAL @ OPP") if event_data else "DAL @ OPP"
    opp = "OPP"
    if " @ " in short_name:
        p1, p2 = short_name.split(" @ ", 1)
        opp = p2 if p1 == "DAL" else p1
    elif " vs " in short_name:
        p1, p2 = short_name.split(" vs ", 1)
        opp = p2 if p1 == "DAL" else p1

    home = False
    if event_data:
        comps = event_data.get("competitions", [])
        if comps:
            for c in comps[0].get("competitors", []):
                if str(c.get("id")) == "6":
                    home = (c.get("homeAway") == "home")
                    break

    espn_state = "pre"
    if status_data:
        espn_state = status_data.get("type", {}).get("state", "pre")

    if espn_state == "in":
        state = "live"
    elif espn_state == "post":
        state = "final"
    else:
        state = "pre"

    my = int(my_score_data) if my_score_data is not None else None
    their = int(opp_score_data) if opp_score_data is not None else None

    # Status text
    status_str = ""
    if state == "live" and status_data:
        period = status_data.get("period", 1)
        clock = status_data.get("displayClock", "")
        short_det = status_data.get("type", {}).get("shortDetail", "")
        if "Halftime" in short_det or "HALFTIME" in short_det:
            status_str = "HALF"
        elif period > 4:
            status_str = f"OT {clock}".strip()
        else:
            status_str = f"Q{period} {clock}".strip()
    elif state == "final":
        period = status_data.get("period", 4) if status_data else 4
        status_str = "FINAL OT" if period > 4 else "FINAL"

    start_utc = None
    if event_data and event_data.get("date"):
        start_utc = time_common.parse_iso_utc(event_data["date"])

    return {
        "state": state,
        "abbr": "DAL",
        "opp": opp,
        "home": home,
        "my": my,
        "their": their,
        "status": status_str[:10],
        "start_utc": start_utc,
        "record": summary,
        "rank": fmt_rank(rank, div_name),
    }


def norm_nhl(schedule_data, landing_data=None, standings_data=None, now_utc=None):
    """Normalize raw NHL schedule/landing/standings data into standard team record."""
    games = schedule_data.get("games", []) if schedule_data else []

    # Standings info
    record_str = ""
    rank_str = None
    if standings_data:
        for s in standings_data.get("standings", []):
            if s.get("teamAbbrev", {}).get("default") == "NJD":
                w = s.get("wins", 0)
                l = s.get("losses", 0)
                ot = s.get("otLosses", 0)
                record_str = f"{w}-{l}-{ot}"
                seq = s.get("divisionSequence")
                div = s.get("divisionName", "Metropolitan")
                rank_str = fmt_rank(seq, div)
                break

    if not games:
        return {
            "state": "off",
            "abbr": "NJD",
            "opp": "",
            "home": False,
            "my": None,
            "their": None,
            "status": "",
            "start_utc": None,
            "record": record_str,
            "rank": rank_str,
        }

    # Find live game first
    chosen = None
    for g in games:
        if g.get("gameState") in ("LIVE", "CRIT"):
            chosen = g
            break

    # Else find first future game
    if chosen is None:
        for g in games:
            if g.get("gameState") in ("FUT", "PRE"):
                chosen = g
                break

    # Else find most recent final game within 3h (or any final if now_utc is None)
    if chosen is None:
        finals = [g for g in games if g.get("gameState") in ("FINAL", "OFF")]
        if finals:
            last_final = finals[-1]
            if now_utc is None:
                chosen = last_final
            elif last_final.get("startTimeUTC"):
                st = time_common.parse_iso_utc(last_final["startTimeUTC"])
                # Within 6 hours of start = ~3 hours after end
                if (now_utc - st) < 6 * 3600:
                    chosen = last_final

    if chosen is None:
        return {
            "state": "off",
            "abbr": "NJD",
            "opp": "",
            "home": False,
            "my": None,
            "their": None,
            "status": "",
            "start_utc": None,
            "record": record_str,
            "rank": rank_str,
        }

    game_state = chosen.get("gameState", "")
    if game_state in ("LIVE", "CRIT"):
        state = "live"
    elif game_state in ("FINAL", "OFF"):
        state = "final"
    else:
        state = "pre"

    home_abbr = chosen.get("homeTeam", {}).get("abbrev", "")
    away_abbr = chosen.get("awayTeam", {}).get("abbrev", "")
    home = (home_abbr == "NJD")
    opp = away_abbr if home else home_abbr

    my = None
    their = None
    if state in ("live", "final"):
        my_landing = None
        their_landing = None
        if landing_data:
            my_landing = landing_data.get("homeTeam" if home else "awayTeam", {}).get("score")
            their_landing = landing_data.get("awayTeam" if home else "homeTeam", {}).get("score")
        my_sched = chosen.get("homeTeam" if home else "awayTeam", {}).get("score")
        their_sched = chosen.get("awayTeam" if home else "homeTeam", {}).get("score")

        my_cand = [int(s) for s in (my_landing, my_sched) if s is not None]
        their_cand = [int(s) for s in (their_landing, their_sched) if s is not None]
        my = max(my_cand) if my_cand else 0
        their = max(their_cand) if their_cand else 0

    status_str = ""
    if state == "live":
        if landing_data and landing_data.get("clock"):
            clock = landing_data.get("clock", {})
            time_rem = clock.get("timeRemaining", "")
            in_intermission = clock.get("inIntermission", False)
            period_desc = landing_data.get("periodDescriptor", {})
            p_num = period_desc.get("number", 1)
            p_type = period_desc.get("periodType", "REG")
            if in_intermission:
                status_str = f"INT P{p_num}"[:10]
            elif p_type == "OT":
                status_str = f"OT {time_rem}".strip()[:10]
            elif p_type == "SO":
                status_str = "SO"
            else:
                status_str = f"P{p_num} {time_rem}".strip()[:10]
        else:
            status_str = "LIVE"
    elif state == "final":
        p_desc = chosen.get("periodDescriptor", {})
        p_type = p_desc.get("periodType", "REG")
        if p_type == "OT":
            status_str = "FINAL OT"
        elif p_type == "SO":
            status_str = "FINAL SO"
        else:
            status_str = "FINAL"

    start_utc = None
    if chosen.get("startTimeUTC"):
        start_utc = time_common.parse_iso_utc(chosen["startTimeUTC"])

    return {
        "state": state,
        "abbr": "NJD",
        "opp": opp,
        "home": home,
        "my": my,
        "their": their,
        "status": status_str[:10],
        "start_utc": start_utc,
        "record": record_str,
        "rank": rank_str,
    }


def norm_mlb(schedule_data, standings_data=None, now_utc=None):
    """Normalize raw MLB schedule and standings data into standard team record."""
    record_str = ""
    rank_str = None
    if standings_data:
        for rec in standings_data.get("records", []):
            for tr in rec.get("teamRecords", []):
                if tr.get("team", {}).get("id") == 147:
                    w = tr.get("wins", 0)
                    l = tr.get("losses", 0)
                    record_str = f"{w}-{l}"
                    div_rank = tr.get("divisionRank")
                    rank_str = fmt_rank(div_rank, "ALE")
                    break

    games = []
    if schedule_data:
        for d in schedule_data.get("dates", []):
            games.extend(d.get("games", []))

    if not games:
        return {
            "state": "off",
            "abbr": "NYY",
            "opp": "",
            "home": False,
            "my": None,
            "their": None,
            "status": "",
            "start_utc": None,
            "record": record_str,
            "rank": rank_str,
        }

    chosen = None
    for g in games:
        if g.get("status", {}).get("abstractGameState") == "Live":
            chosen = g
            break

    if chosen is None:
        for g in games:
            if g.get("status", {}).get("abstractGameState") == "Preview":
                chosen = g
                break

    if chosen is None:
        finals = [g for g in games if g.get("status", {}).get("abstractGameState") == "Final"]
        if finals:
            last_final = finals[-1]
            if now_utc is None:
                chosen = last_final
            elif last_final.get("gameDate"):
                st = time_common.parse_iso_utc(last_final["gameDate"])
                if (now_utc - st) < 6 * 3600:
                    chosen = last_final

    if chosen is None:
        return {
            "state": "off",
            "abbr": "NYY",
            "opp": "",
            "home": False,
            "my": None,
            "their": None,
            "status": "",
            "start_utc": None,
            "record": record_str,
            "rank": rank_str,
        }

    abs_state = chosen.get("status", {}).get("abstractGameState", "")
    if abs_state == "Live":
        state = "live"
    elif abs_state == "Final":
        state = "final"
    else:
        state = "pre"

    teams = chosen.get("teams", {})
    home = (teams.get("home", {}).get("team", {}).get("id") == 147)
    opp = teams.get("away" if home else "home", {}).get("team", {}).get("abbreviation", "OPP")

    my = None
    their = None
    if state in ("live", "final"):
        my_raw = teams.get("home" if home else "away", {}).get("score")
        their_raw = teams.get("away" if home else "home", {}).get("score")
        my = int(my_raw) if my_raw is not None else 0
        their = int(their_raw) if their_raw is not None else 0

    status_str = ""
    linescore = chosen.get("linescore", {})
    if state == "live":
        inning = linescore.get("currentInning", 1)
        half = linescore.get("inningHalf", "Top")
        h_letter = "T" if half == "Top" else "B"
        status_str = f"{h_letter}{inning}"
    elif state == "final":
        inning = linescore.get("currentInning", 9)
        if inning > 9:
            status_str = f"F/{inning}"
        else:
            status_str = "FINAL"

    start_utc = None
    if chosen.get("gameDate"):
        start_utc = time_common.parse_iso_utc(chosen["gameDate"])

    return {
        "state": state,
        "abbr": "NYY",
        "opp": opp,
        "home": home,
        "my": my,
        "their": their,
        "status": status_str[:10],
        "start_utc": start_utc,
        "record": record_str,
        "rank": rank_str,
    }


def format_game_screen(rec, now_utc=None):
    """Produce the 3 text rows and colors for a game screen.
    Returns: (row1, row2, row3, row1_color, row2_color, row3_color)"""
    state = rec.get("state", "off")
    abbr = rec.get("abbr", "")
    opp = rec.get("opp", "")
    home = rec.get("home", False)
    my = rec.get("my")
    their = rec.get("their")
    status = rec.get("status", "")
    start_utc = rec.get("start_utc")
    record = rec.get("record", "")

    # Matchup line (road team first)
    if home:
        matchup = f"{opp}@{abbr}"
    else:
        matchup = f"{abbr}@{opp}"
    matchup = matchup[:10]

    if state == "live":
        score_text = f"{my}-{their}"[:10]
        c2 = score_color(my, their)
        return matchup, score_text, status, COLOR_WHITE, c2, COLOR_WHITE

    elif state == "final":
        score_text = f"{my}-{their}"[:10]
        c2 = score_color(my, their)
        return matchup, score_text, status, COLOR_WHITE, c2, COLOR_WHITE

    elif state == "pre":
        if start_utc is not None:
            day_str, time_str, date_str = time_common.fmt_game_time(start_utc)
            # Check if game is today
            is_today = False
            if now_utc is not None:
                offset = time_common.eastern_offset(now_utc)
                local_now_day = (now_utc + offset) // 86400
                game_day = (start_utc + time_common.eastern_offset(start_utc)) // 86400
                is_today = (local_now_day == game_day)

            if is_today:
                return matchup, time_str[:10], "TODAY", COLOR_WHITE, COLOR_WHITE, COLOR_WHITE
            else:
                return matchup, f"{day_str} {time_str}"[:10], date_str[:10], COLOR_WHITE, COLOR_WHITE, COLOR_WHITE
        else:
            return matchup, "UPCOMING", "", COLOR_WHITE, COLOR_WHITE, COLOR_WHITE

    else:  # off (season over)
        team_name = TEAM_NAMES.get(abbr, abbr)
        r3 = f"OVER {record}".strip() if record else "OVER"
        return team_name[:10], "SEASON", r3[:10], COLOR_WHITE, COLOR_GRAY, COLOR_GRAY


def format_standings_screen(rec):
    """Produce the 3 text rows for a standings page:
    row1: team name
    row2: record (2-3 / 2-3-0 / 93-68)
    row3: #2 NFCE style rank"""
    abbr = rec.get("abbr", "")
    team_name = TEAM_NAMES.get(abbr, abbr)
    record = rec.get("record", "")
    rank = rec.get("rank")
    if not rank:
        return None
    return team_name[:10], record[:10], rank[:10], COLOR_WHITE, COLOR_WHITE, COLOR_WHITE


def choose_display_screen(teams, live_rot_time=8, game_rot_time=5, standings_rot_time=4):
    """Rotation selector logic.
    teams: list of normalized team records.
    Returns:
    - 'live_only': bool (True if we are in live-only mode)
    - schedule of screens to display: list of (screen_type, team_dict, duration_sec)
    """
    live_teams = [t for t in teams if t.get("state") == "live"]
    if live_teams:
        return True, [("game", t, live_rot_time) for t in live_teams]

    # No live teams: rotate through all teams
    screens = []
    for t in teams:
        screens.append(("game", t, game_rot_time))
        # Add standings page only if not off and rank exists
        if t.get("state") != "off" and t.get("rank"):
            screens.append(("standings", t, standings_rot_time))
    return False, screens
