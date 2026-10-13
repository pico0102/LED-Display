# sleeper_logic.py -- Pure logic for Sleeper fantasy football matchups,
# win probability, yet-to-play (YTP) counts, and standings ranking.
# Hardware-free pure Python: safe to import and unit test on desktop.

import math

COLOR_WHITE = 0xFFFFFF
COLOR_RED = 0xFF0000
COLOR_YELLOW = 0xFFFF00
COLOR_GREEN = 0x00FF00
COLOR_GRAY = 0x888888


def calc_fpts(settings):
    """Combine fpts integer and fpts_decimal into float (e.g. 597 + 18/100 -> 597.18)."""
    if not settings:
        return 0.0
    fpts = settings.get("fpts") or 0
    dec = settings.get("fpts_decimal") or 0
    return float(fpts) + float(dec) / 100.0


def calc_rank(rosters, target_roster_id):
    """Sort rosters by (wins desc, fpts desc).
    Returns (1-based rank, total_rosters)."""
    if not rosters:
        return None, 0

    def sort_key(r):
        st = r.get("settings") or {}
        wins = st.get("wins") or 0
        fpts = calc_fpts(st)
        return (wins, fpts)

    sorted_rosters = sorted(rosters, key=sort_key, reverse=True)
    for idx, r in enumerate(sorted_rosters):
        if r.get("roster_id") == target_roster_id:
            return idx + 1, len(sorted_rosters)
    return None, len(sorted_rosters)


def calc_ytp(starters, nfl_schedule, week, player_teams):
    """Count non-'0' starters whose NFL team has a game this week with status == 'pre_game'.
    starters: list of player_id strings (e.g. ['4046', 'SEA', ...])
    nfl_schedule: list of game dicts from schedule endpoint
    week: current week number
    player_teams: dict mapping player_id -> team_abbrev (e.g. '4046' -> 'KC')
    Returns integer YTP count, or None if starters list is empty/unassigned."""
    if not starters or all(s == "0" for s in starters):
        return None

    # Map each NFL team to its game status for the target week
    team_status = {}
    if nfl_schedule:
        for g in nfl_schedule:
            if g.get("week") == week:
                status = g.get("status", "pre_game")
                h = g.get("home")
                a = g.get("away")
                if h:
                    team_status[h] = status
                if a:
                    team_status[a] = status

    ytp = 0
    for pid in starters:
        if not pid or pid == "0":
            continue

        # DEF slot uses team code directly (e.g. 'SEA')
        if pid in team_status or (len(pid) <= 3 and pid.isupper()):
            team = pid
        else:
            team = player_teams.get(str(pid))

        if not team:
            # If player team is unknown, assume pre_game to avoid undercounting
            ytp += 1
            continue

        # Bye week check: team not in schedule for this week -> not YTP
        if team not in team_status:
            continue

        st = team_status.get(team)
        if st == "pre_game":
            ytp += 1

    return ytp


def calc_win_prob(my_points, opp_points, my_ytp, opp_ytp,
                  my_fpts_total, my_games, opp_fpts_total, opp_games):
    """Calculate win probability percentage (0 to 100) using logistic normal approximation.
    p = 1 / (1 + exp(-1.702 * (proj_me - proj_opp) / sigma))"""
    eff_my_ytp = 10 if my_ytp is None else my_ytp
    eff_opp_ytp = 10 if opp_ytp is None else opp_ytp

    # Decided game
    if eff_my_ytp == 0 and eff_opp_ytp == 0:
        if my_points > opp_points:
            return 100
        elif my_points < opp_points:
            return 0
        return 50

    avg_me = (my_fpts_total / my_games / 10.0) if my_games > 0 else 10.0
    avg_opp = (opp_fpts_total / opp_games / 10.0) if opp_games > 0 else 10.0

    proj_me = my_points + eff_my_ytp * avg_me
    proj_opp = opp_points + eff_opp_ytp * avg_opp

    sigma = 6.0 * math.sqrt(max(eff_my_ytp + eff_opp_ytp, 1))
    diff = proj_me - proj_opp
    z = -1.702 * diff / sigma

    # Guard against float overflow in exp
    if z > 20:
        p = 0.0
    elif z < -20:
        p = 1.0
    else:
        p = 1.0 / (1.0 + math.exp(z))

    prob_pct = int(round(p * 100))
    # Clamp to 1..99 for in-progress games
    return max(1, min(99, prob_pct))


def format_score_line(my_pts, opp_pts):
    """Format row 2 score line: '98.4-87.1' (shrink to integers if > 9 chars)."""
    s = f"{my_pts:.1f}-{opp_pts:.1f}"
    if len(s) > 9:
        s = f"{int(round(my_pts))}-{int(round(opp_pts))}"
    return s[:10]


def format_screen_a(week, win_prob, my_pts, opp_pts, my_ytp, opp_ytp):
    """Screen A (Main Matchup):
    row1: WK6 W:62%
    row2: 98.4-87.1 (colored by lead)
    row3: YTP 3 v 5"""
    r1 = f"WK{week} W:{win_prob}%"[:10]
    r2 = format_score_line(my_pts, opp_pts)

    y_me = str(my_ytp) if my_ytp is not None else "?"
    y_opp = str(opp_ytp) if opp_ytp is not None else "?"
    r3 = f"YTP {y_me} v {y_opp}"[:10]

    if my_pts > opp_pts:
        c2 = COLOR_GREEN
    elif my_pts < opp_pts:
        c2 = COLOR_RED
    else:
        c2 = COLOR_YELLOW

    return r1, r2, r3, COLOR_WHITE, c2, COLOR_WHITE


def format_screen_b(opp_record, opp_display_name, week):
    """Screen B (Opponent):
    row1: VS 1-4
    row2: opponent display name (<=10 chars)
    row3: WK6 UP NEXT"""
    r1 = f"VS {opp_record}"[:10]
    r2 = str(opp_display_name)[:10]
    r3 = f"WK{week} UP NEXT"[:10]
    return r1, r2, r3, COLOR_WHITE, COLOR_WHITE, COLOR_GRAY


def format_screen_c(username, my_record, my_fpts, rank, total_teams):
    """Screen C (User profile):
    row1: PINEC0NE
    row2: 3-2 597.2
    row3: #6 OF 12"""
    r1 = str(username)[:10].upper()
    r2 = f"{my_record} {my_fpts:.1f}"[:10]
    rank_str = f"#{rank}" if rank is not None else "#?"
    r3 = f"{rank_str} OF {total_teams}"[:10]
    return r1, r2, r3, COLOR_WHITE, COLOR_WHITE, COLOR_WHITE
