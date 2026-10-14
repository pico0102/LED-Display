#!/usr/bin/env python3
"""tools/test_logic.py - Unit tests for pure logic modules.
Runs on desktop Python (unittest).
Modules tested: time_common, sports_logic, sleeper_logic.
Board-only modules (board, displayio, etc.) must NEVER be imported by these modules.
"""

import os
import sys
import unittest

# Ensure repo root is on sys.path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Check if modules exist before importing to allow running during earlier phases
try:
    import time_common
except ImportError:
    time_common = None

try:
    import sports_logic
except ImportError:
    sports_logic = None

try:
    import sleeper_logic
except ImportError:
    sleeper_logic = None

try:
    import bus_logic
except ImportError:
    bus_logic = None


class TestPureModulesImport(unittest.TestCase):
    def test_framework_ready(self):
        """Smoke test verifying unittest framework runs."""
        self.assertTrue(True)


@unittest.skipIf(time_common is None, "time_common not implemented yet (Phase 2)")
class TestTimeLogic(unittest.TestCase):
    def test_civil_calendar_roundtrip(self):
        """Test days_from_civil and civil_from_days for various dates."""
        cases = [
            (1970, 1, 1),
            (2000, 2, 29),  # century leap year
            (2024, 2, 29),  # regular leap year
            (2026, 3, 8),
            (2026, 10, 13),
            (2026, 11, 1),
            (2030, 12, 31),
        ]
        for y, m, d in cases:
            days = time_common.days_from_civil(y, m, d)
            y2, m2, d2 = time_common.civil_from_days(days)
            self.assertEqual((y, m, d), (y2, m2, d2), f"Mismatch for {y}-{m}-{d}")

    def test_leap_years(self):
        """Test days count between Feb 28 and Mar 1 on leap and non-leap years."""
        # 2024 is a leap year (Feb 29 exists)
        d_feb28_2024 = time_common.days_from_civil(2024, 2, 28)
        d_feb29_2024 = time_common.days_from_civil(2024, 2, 29)
        d_mar01_2024 = time_common.days_from_civil(2024, 3, 1)
        self.assertEqual(d_feb29_2024 - d_feb28_2024, 1)
        self.assertEqual(d_mar01_2024 - d_feb29_2024, 1)

        # 2025 is not a leap year
        d_feb28_2025 = time_common.days_from_civil(2025, 2, 28)
        d_mar01_2025 = time_common.days_from_civil(2025, 3, 1)
        self.assertEqual(d_mar01_2025 - d_feb28_2025, 1)

    def test_parse_iso_utc_both_shapes(self):
        """Test parse_iso_utc for both short and full ISO formats."""
        ts1 = time_common.parse_iso_utc("2026-10-18T17:00Z")
        ts2 = time_common.parse_iso_utc("2026-10-18T17:00:00Z")
        self.assertEqual(ts1, ts2)

        # 2026-10-13T22:00:00Z
        ts3 = time_common.parse_iso_utc("2026-10-13T22:00:00Z")
        # 2026-10-13 is Tuesday
        self.assertEqual(time_common.weekday(ts3), 1)  # Tuesday = 1

    def test_parse_rfc1123(self):
        """Test parse_rfc1123 for HTTP Date header."""
        ts = time_common.parse_rfc1123("Tue, 13 Oct 2026 22:15:03 GMT")
        ts_iso = time_common.parse_iso_utc("2026-10-13T22:15:03Z")
        self.assertEqual(ts, ts_iso)

    def test_eastern_dst_spring_boundary(self):
        """US DST 2026 starts 2nd Sunday of March (2026-03-08) at 07:00 UTC."""
        ts_before = time_common.parse_iso_utc("2026-03-08T06:59:00Z")
        ts_after = time_common.parse_iso_utc("2026-03-08T07:00:00Z")

        # 06:59Z is still EST (-5 hours = -18000s)
        self.assertEqual(time_common.eastern_offset(ts_before), -18000)
        # 07:00Z transitions to EDT (-4 hours = -14400s)
        self.assertEqual(time_common.eastern_offset(ts_after), -14400)

    def test_eastern_dst_fall_boundary(self):
        """US DST 2026 ends 1st Sunday of November (2026-11-01) at 06:00 UTC."""
        ts_before = time_common.parse_iso_utc("2026-11-01T05:59:00Z")
        ts_after = time_common.parse_iso_utc("2026-11-01T06:00:00Z")

        # 05:59Z is still EDT (-4 hours = -14400s)
        self.assertEqual(time_common.eastern_offset(ts_before), -14400)
        # 06:00Z transitions back to EST (-5 hours = -18000s)
        self.assertEqual(time_common.eastern_offset(ts_after), -18000)

    def test_fmt_game_time(self):
        """Test fmt_game_time for 2026-10-18T17:00Z -> ('SUN', '1:00P', 'OCT 18')."""
        ts = time_common.parse_iso_utc("2026-10-18T17:00Z")
        day_str, time_str, date_str = time_common.fmt_game_time(ts)
        self.assertEqual(day_str, "SUN")
        self.assertEqual(time_str, "1:00P")
        self.assertEqual(date_str, "OCT 18")

    def test_fmt_clock(self):
        """Test fmt_clock for 2026-10-13T22:04:00Z (6:04 PM EDT)."""
        ts = time_common.parse_iso_utc("2026-10-13T22:04:00Z")
        self.assertEqual(time_common.fmt_clock(ts), "6:04P")

        # Morning test: 14:04Z -> 10:04A EDT
        ts_am = time_common.parse_iso_utc("2026-10-13T14:04:00Z")
        self.assertEqual(time_common.fmt_clock(ts_am), "10:04A")



@unittest.skipIf(sports_logic is None, "sports_logic not implemented yet (Phase 4)")
class TestSportsLogic(unittest.TestCase):
    def test_rank_formatting(self):
        """Test #2 NFCE style rank string formatting."""
        self.assertEqual(sports_logic.fmt_rank(2, "NFC East"), "#2 NFCE")
        self.assertEqual(sports_logic.fmt_rank(7, "Metropolitan"), "#7 METRO")
        self.assertEqual(sports_logic.fmt_rank(2, "American League East"), "#2 ALE")
        self.assertIsNone(sports_logic.fmt_rank(None, "Metropolitan"))

    def test_norm_nfl_states(self):
        """Test norm_nfl for pre, in, post, and season over (played >= 17)."""
        # Pre-game: Week 6
        rec_data = {"summary": "2-3"}
        ev_data = {
            "date": "2026-10-19T00:20Z",
            "shortName": "DAL @ GB",
            "competitions": [{"competitors": [{"id": "6", "homeAway": "away"}, {"id": "9", "homeAway": "home"}]}],
        }
        st_data = {"type": {"state": "pre"}}
        nfl_pre = sports_logic.norm_nfl(rec_data, ev_data, st_data, rank=2)
        self.assertEqual(nfl_pre["state"], "pre")
        self.assertEqual(nfl_pre["abbr"], "DAL")
        self.assertEqual(nfl_pre["opp"], "GB")
        self.assertFalse(nfl_pre["home"])
        self.assertIsNone(nfl_pre["my"])
        self.assertEqual(nfl_pre["record"], "2-3")
        self.assertEqual(nfl_pre["rank"], "#2 NFCE")

        # In-game (Live)
        st_data_live = {"type": {"state": "in", "shortDetail": "Q3 4:12"}, "period": 3, "displayClock": "4:12"}
        nfl_live = sports_logic.norm_nfl(rec_data, ev_data, st_data_live, my_score_data=17, opp_score_data=14)
        self.assertEqual(nfl_live["state"], "live")
        self.assertEqual(nfl_live["my"], 17)
        self.assertEqual(nfl_live["their"], 14)
        self.assertEqual(nfl_live["status"], "Q3 4:12")

        # Post-game (Final)
        st_data_post = {"type": {"state": "post"}, "period": 4}
        nfl_post = sports_logic.norm_nfl(rec_data, ev_data, st_data_post, my_score_data=20, opp_score_data=23)
        self.assertEqual(nfl_post["state"], "final")
        self.assertEqual(nfl_post["my"], 20)
        self.assertEqual(nfl_post["their"], 23)
        self.assertEqual(nfl_post["status"], "FINAL")

        # Season over: played >= 17
        rec_data_off = {"summary": "10-7"}
        nfl_off = sports_logic.norm_nfl(rec_data_off, ev_data, st_data)
        self.assertEqual(nfl_off["state"], "off")

    def test_norm_nhl_game_choice(self):
        """Test NHL game choice: live beats future; recent final within 3h; none -> off."""
        sched_live_and_fut = {
            "games": [
                {"id": 1, "gameState": "LIVE", "startTimeUTC": "2026-10-13T22:00:00Z", "awayTeam": {"abbrev": "NJD", "score": 2}, "homeTeam": {"abbrev": "DET", "score": 1}},
                {"id": 2, "gameState": "FUT", "startTimeUTC": "2026-10-15T23:00:00Z", "awayTeam": {"abbrev": "NJD"}, "homeTeam": {"abbrev": "TOR"}},
            ]
        }
        nhl_res = sports_logic.norm_nhl(sched_live_and_fut)
        self.assertEqual(nhl_res["state"], "live")
        self.assertEqual(nhl_res["opp"], "DET")
        self.assertEqual(nhl_res["my"], 2)
        self.assertEqual(nhl_res["their"], 1)

        # Fut beats none
        sched_fut_only = {
            "games": [
                {"id": 2, "gameState": "FUT", "startTimeUTC": "2026-10-15T23:00:00Z", "awayTeam": {"abbrev": "TOR"}, "homeTeam": {"abbrev": "NJD"}},
            ]
        }
        nhl_fut = sports_logic.norm_nhl(sched_fut_only)
        self.assertEqual(nhl_fut["state"], "pre")
        self.assertEqual(nhl_fut["opp"], "TOR")
        self.assertTrue(nhl_fut["home"])

        # Empty schedule -> off
        nhl_off = sports_logic.norm_nhl({"games": []})
        self.assertEqual(nhl_off["state"], "off")

    def test_norm_mlb_inning_text(self):
        """Test MLB inning text and status strings."""
        sched_live = {
            "dates": [{
                "games": [{
                    "status": {"abstractGameState": "Live"},
                    "teams": {"home": {"team": {"id": 147, "abbreviation": "NYY"}, "score": 4}, "away": {"team": {"id": 111, "abbreviation": "BOS"}, "score": 2}},
                    "linescore": {"currentInning": 5, "inningHalf": "Top"},
                }]
            }]
        }
        mlb_live = sports_logic.norm_mlb(sched_live)
        self.assertEqual(mlb_live["state"], "live")
        self.assertEqual(mlb_live["status"], "T5")
        self.assertEqual(mlb_live["my"], 4)
        self.assertEqual(mlb_live["their"], 2)

        # Final extra inning
        sched_f10 = {
            "dates": [{
                "games": [{
                    "status": {"abstractGameState": "Final"},
                    "teams": {"home": {"team": {"id": 147, "abbreviation": "NYY"}, "score": 5}, "away": {"team": {"id": 111, "abbreviation": "BOS"}, "score": 4}},
                    "linescore": {"currentInning": 10},
                }]
            }]
        }
        mlb_f10 = sports_logic.norm_mlb(sched_f10)
        self.assertEqual(mlb_f10["state"], "final")
        self.assertEqual(mlb_f10["status"], "F/10")

        # Empty schedule -> off
        mlb_off = sports_logic.norm_mlb({"dates": []})
        self.assertEqual(mlb_off["state"], "off")

    def test_rotation_selector(self):
        """Test rotation selector when live teams exist vs none live."""
        t_live = {"state": "live", "abbr": "NJD", "rank": "#7 METRO"}
        t_pre = {"state": "pre", "abbr": "DAL", "rank": "#2 NFCE"}
        t_off = {"state": "off", "abbr": "NYY", "rank": "#2 ALE"}

        # When one team is live: only rotate among live teams (no standings)
        live_only, screens = sports_logic.choose_display_screen([t_live, t_pre, t_off])
        self.assertTrue(live_only)
        self.assertEqual(len(screens), 1)
        self.assertEqual(screens[0][0], "game")
        self.assertEqual(screens[0][1]["abbr"], "NJD")

        # When no team is live: rotate through all 3 teams; include standings if available
        live_only_none, screens_all = sports_logic.choose_display_screen([t_pre, t_off])
        self.assertFalse(live_only_none)
        # t_pre has game (5s) and standings (4s); t_off has game (5s) only
        self.assertEqual(len(screens_all), 3)
        self.assertEqual(screens_all[0], ("game", t_pre, 5))
        self.assertEqual(screens_all[1], ("standings", t_pre, 4))
        self.assertEqual(screens_all[2], ("game", t_off, 5))

    def test_score_colors(self):
        """Test score color selection: green leading, red trailing, yellow tied."""
        self.assertEqual(sports_logic.score_color(17, 14), sports_logic.COLOR_GREEN)
        self.assertEqual(sports_logic.score_color(10, 14), sports_logic.COLOR_RED)
        self.assertEqual(sports_logic.score_color(14, 14), sports_logic.COLOR_YELLOW)


@unittest.skipIf(sleeper_logic is None, "sleeper_logic not implemented yet (Phase 5)")
class TestSleeperLogic(unittest.TestCase):
    def test_calc_fpts(self):
        """Test fpts integer and fpts_decimal combination."""
        settings = {"fpts": 597, "fpts_decimal": 18}
        self.assertAlmostEqual(sleeper_logic.calc_fpts(settings), 597.18, places=2)

    def test_calc_rank_with_ties(self):
        """Test ranking rosters by wins desc, fpts desc."""
        rosters = [
            {"roster_id": 1, "settings": {"wins": 4, "fpts": 550, "fpts_decimal": 0}},
            {"roster_id": 2, "settings": {"wins": 3, "fpts": 600, "fpts_decimal": 0}},
            {"roster_id": 3, "settings": {"wins": 3, "fpts": 590, "fpts_decimal": 50}},  # tied on wins with #2, lower fpts
            {"roster_id": 4, "settings": {"wins": 1, "fpts": 400, "fpts_decimal": 0}},
        ]
        # Roster 2 should be #2 (wins=3, fpts=600)
        rank2, total = sleeper_logic.calc_rank(rosters, 2)
        self.assertEqual(rank2, 2)
        self.assertEqual(total, 4)

        # Roster 3 should be #3 (wins=3, fpts=590.5)
        rank3, _ = sleeper_logic.calc_rank(rosters, 3)
        self.assertEqual(rank3, 3)

    def test_calc_ytp_synthetic_schedule(self):
        """Test YTP count with pre_game, complete, bye, and DEF."""
        schedule = [
            {"week": 6, "home": "KC", "away": "DET", "status": "pre_game"},
            {"week": 6, "home": "SEA", "away": "SF", "status": "complete"},
            {"week": 6, "home": "DAL", "away": "GB", "status": "pre_game"},
            # Notice 'MIA' has no game this week (Bye)
        ]
        player_teams = {
            "101": "KC",   # pre_game -> YTP
            "102": "SEA",  # complete -> not YTP
            "103": "MIA",  # bye -> not YTP
            "104": "DAL",  # pre_game -> YTP
        }
        # Starters: 101(KC), 102(SEA), 103(MIA), 104(DAL), 'SEA'(DEF, complete), '0'(empty)
        starters = ["101", "102", "103", "104", "SEA", "0"]
        ytp = sleeper_logic.calc_ytp(starters, schedule, 6, player_teams)
        # Expected: 101 and 104 are YTP = 2
        self.assertEqual(ytp, 2)

    def test_win_prob_identical_teams(self):
        """Test win probability is 50% for identical teams with equal YTP."""
        p = sleeper_logic.calc_win_prob(
            my_points=50.0, opp_points=50.0,
            my_ytp=5, opp_ytp=5,
            my_fpts_total=500.0, my_games=5,
            opp_fpts_total=500.0, opp_games=5,
        )
        self.assertEqual(p, 50)

    def test_win_prob_decided(self):
        """Test win probability when YTP both 0 (decided game)."""
        p_win = sleeper_logic.calc_win_prob(
            my_points=100.0, opp_points=95.0,
            my_ytp=0, opp_ytp=0,
            my_fpts_total=500.0, my_games=5,
            opp_fpts_total=500.0, opp_games=5,
        )
        self.assertEqual(p_win, 100)

        p_loss = sleeper_logic.calc_win_prob(
            my_points=90.0, opp_points=95.0,
            my_ytp=0, opp_ytp=0,
            my_fpts_total=500.0, my_games=5,
            opp_fpts_total=500.0, opp_games=5,
        )
        self.assertEqual(p_loss, 0)

    def test_win_prob_opponent_empty_starters(self):
        """Test opponent starters empty -> ytp_opp is None, defaults to 10 slots."""
        p = sleeper_logic.calc_win_prob(
            my_points=0.0, opp_points=0.0,
            my_ytp=10, opp_ytp=None,
            my_fpts_total=500.0, my_games=5,
            opp_fpts_total=500.0, opp_games=5,
        )
        # Identical averages and both effective YTP 10 -> 50%
        self.assertEqual(p, 50)

    def test_screen_formatting(self):
        """Test screen layouts A, B, and C."""
        # Screen A: leading 98.4-87.1 -> row2 green
        r1, r2, r3, c1, c2, c3 = sleeper_logic.format_screen_a(6, 62, 98.4, 87.1, 3, 5)
        self.assertEqual(r1, "WK6 W:62%")
        self.assertEqual(r2, "98.4-87.1")
        self.assertEqual(r3, "YTP 3 v 5")
        self.assertEqual(c2, sleeper_logic.COLOR_GREEN)

        # Screen B
        rb1, rb2, rb3, _, _, _ = sleeper_logic.format_screen_b("1-4", "Alice", 6)
        self.assertEqual(rb1, "VS 1-4")
        self.assertEqual(rb2, "Alice")
        self.assertEqual(rb3, "WK6 UP NEX")

        # Screen C
        rc1, rc2, rc3, _, _, _ = sleeper_logic.format_screen_c("pinec0ne", "3-2", 597.2, 6, 12)
        self.assertEqual(rc1, "PINEC0NE")
        self.assertEqual(rc2, "3-2 597.2")
        self.assertEqual(rc3, "#6 OF 12")

    def test_null_safety(self):
        """Test robust handling of None/null fields from Sleeper API."""
        # Null settings in fpts
        self.assertEqual(sleeper_logic.calc_fpts({"fpts": None, "fpts_decimal": None}), 0.0)
        self.assertEqual(sleeper_logic.calc_fpts(None), 0.0)

        # Null rank in Screen C
        rc1, rc2, rc3, _, _, _ = sleeper_logic.format_screen_c("pinec0ne", "3-2", 597.2, None, 12)
        self.assertEqual(rc3, "#? OF 12")

        # Empty/None starters
        self.assertIsNone(sleeper_logic.calc_ytp(None, [], 6, {}))
        self.assertIsNone(sleeper_logic.calc_ytp([], [], 6, {}))


@unittest.skipIf(bus_logic is None, "bus_logic not implemented yet (Phase 6)")
class TestBusLogic(unittest.TestCase):
    def test_classify_status(self):
        """Test parsing of various departurestatus formats."""
        self.assertEqual(bus_logic.classify_status("in 18 mins"), (18, "18m"))
        self.assertEqual(bus_logic.classify_status("in 3 Min"), (3, "3m"))
        self.assertEqual(bus_logic.classify_status("All Aboard"), (-1, "DUE"))
        self.assertEqual(bus_logic.classify_status("Due"), (-1, "DUE"))
        self.assertEqual(bus_logic.classify_status("09:43 PM"), (9999, "09:43P"))
        self.assertEqual(bus_logic.classify_status(""), (9999, "?"))
        self.assertEqual(bus_logic.classify_status(None), (9999, "?"))

    def test_time_color_for(self):
        """Test color thresholds (<3 red, <5 yellow, >=5 green)."""
        self.assertEqual(bus_logic.time_color_for(-1), bus_logic.COLOR_RED)
        self.assertEqual(bus_logic.time_color_for(2), bus_logic.COLOR_RED)
        self.assertEqual(bus_logic.time_color_for(3), bus_logic.COLOR_YELLOW)
        self.assertEqual(bus_logic.time_color_for(4), bus_logic.COLOR_YELLOW)
        self.assertEqual(bus_logic.time_color_for(5), bus_logic.COLOR_GREEN)
        self.assertEqual(bus_logic.time_color_for(9999), bus_logic.COLOR_GREEN)

    def test_is_catchable(self):
        """Test catchability given walk minutes."""
        # walk_min = 4
        self.assertFalse(bus_logic.is_catchable(-1, 4))
        self.assertFalse(bus_logic.is_catchable(2, 4))
        self.assertFalse(bus_logic.is_catchable(3, 4))
        self.assertTrue(bus_logic.is_catchable(4, 4))
        self.assertTrue(bus_logic.is_catchable(10, 4))
        self.assertTrue(bus_logic.is_catchable(9999, 4))

        # walk_min = 0 (at the stop)
        self.assertTrue(bus_logic.is_catchable(-1, 0))
        self.assertTrue(bus_logic.is_catchable(0, 0))

    def test_should_leave_now(self):
        """Test leave-now trigger range (walk_min .. walk_min + 1)."""
        # walk_min = 4
        self.assertFalse(bus_logic.should_leave_now(2, 4))
        self.assertFalse(bus_logic.should_leave_now(3, 4))
        self.assertTrue(bus_logic.should_leave_now(4, 4))
        self.assertTrue(bus_logic.should_leave_now(5, 4))
        self.assertFalse(bus_logic.should_leave_now(6, 4))
        self.assertFalse(bus_logic.should_leave_now(9999, 4))
        self.assertFalse(bus_logic.should_leave_now(-1, 4))

    def test_select_display_trips(self):
        """Test selection of next catchable bus and ticker buses."""
        trips = [
            {"public_route": "87", "departurestatus": "in 2 mins"},
            {"public_route": "86", "departurestatus": "in 5 mins"},
            {"public_route": "84", "departurestatus": "in 12 mins"},
        ]
        next_t, ticker, leave_now = bus_logic.select_display_trips(trips, walk_min=4)
        # Next catchable bus should be 86 (5 mins)
        self.assertEqual(next_t.get("public_route"), "86")
        self.assertTrue(leave_now)  # 5 mins is within 4..5
        # Ticker should contain 87 (2 mins) and 84 (12 mins)
        self.assertEqual([t.get("public_route") for t in ticker], ["87", "84"])


if __name__ == "__main__":
    unittest.main()
