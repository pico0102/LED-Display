#!/usr/bin/env python3
"""tools/check_apis.py - Desktop contract test for API endpoints.
Uses stdlib urllib only.
Hits each endpoint listed in docs/IMPLEMENTATION_PLAN.md and asserts
every JSON path/key the board code will read exists.
"""

import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LEDMatrixDisplay/1.0"
failures = 0


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [FAIL] HTTP request to {url}: {e}")
        global failures
        failures += 1
        return None


def check(name, condition, detail=""):
    global failures
    if condition:
        print(f"  [OK] {name}")
    else:
        print(f"  [FAIL] {name} ({detail})")
        failures += 1


def check_nfl():
    print("\n--- Checking NFL / Cowboys (ESPN Core API) ---")
    current_year = datetime.now().year if datetime.now().month >= 3 else datetime.now().year - 1
    events_url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{current_year}/types/2/teams/6/events"
    events = fetch_json(events_url)
    if not events:
        return

    items = events.get("items", [])
    check("events list items count == 17", len(items) == 17, f"count={len(items)}")
    if not items:
        return

    first_ref = items[0].get("$ref")
    check("events items[0].$ref exists", bool(first_ref), f"ref={first_ref}")

    rec_url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{current_year}/types/2/teams/6/records/0"
    rec = fetch_json(rec_url)
    if rec:
        check("record summary exists", "summary" in rec, f"summary={rec.get('summary')}")

    if first_ref:
        ev = fetch_json(first_ref)
        if ev:
            check("event date exists", "date" in ev, f"date={ev.get('date')}")
            check("event shortName exists", "shortName" in ev, f"shortName={ev.get('shortName')}")
            comps = ev.get("competitions", [])
            check("event competitions list non-empty", len(comps) > 0)
            if comps:
                comp = comps[0]
                competitors = comp.get("competitors", [])
                check("competitors list has 2 entries", len(competitors) == 2, f"len={len(competitors)}")
                for c in competitors:
                    check(f"competitor id={c.get('id')} has homeAway", "homeAway" in c)

                status_ref = comp.get("status", {}).get("$ref")
                check("competition status.$ref exists", bool(status_ref))
                if status_ref:
                    status = fetch_json(status_ref)
                    if status:
                        check("status type.state exists", "state" in status.get("type", {}))
                        check("status displayClock exists", "displayClock" in status)
                        check("status period exists", "period" in status)
                        check("status type.shortDetail exists", "shortDetail" in status.get("type", {}))

                score_url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{ev.get('id')}/competitions/{ev.get('id')}/competitors/6/score?lang=en&region=us"
                score_data = fetch_json(score_url)
                if score_data:
                    check("competitor score value exists", "value" in score_data, f"val={score_data.get('value')}")


def check_nhl():
    print("\n--- Checking NHL / Devils ---")
    sched_url = "https://api-web.nhle.com/v1/club-schedule/NJD/week/now"
    sched = fetch_json(sched_url)
    if sched:
        games = sched.get("games", [])
        check("schedule games non-empty", len(games) > 0, f"count={len(games)}")
        if games:
            g = games[0]
            check("game gameState exists", "gameState" in g, f"state={g.get('gameState')}")
            check("game startTimeUTC exists", "startTimeUTC" in g)
            check("game awayTeam.abbrev exists", "abbrev" in g.get("awayTeam", {}))
            check("game homeTeam.abbrev exists", "abbrev" in g.get("homeTeam", {}))
            check("game id exists", "id" in g, f"id={g.get('id')}")

            game_id = g.get("id")
            landing_url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/landing"
            landing = fetch_json(landing_url)
            if landing:
                check("landing periodDescriptor exists", "periodDescriptor" in landing)
                check("landing clock or gameState exists", "clock" in landing or "gameState" in landing)
                check("landing awayTeam.score exists", "score" in landing.get("awayTeam", {}))
                check("landing homeTeam.score exists", "score" in landing.get("homeTeam", {}))

    standings_url = "https://api-web.nhle.com/v1/standings/now"
    standings = fetch_json(standings_url)
    if standings:
        njd = next((s for s in standings.get("standings", []) if s.get("teamAbbrev", {}).get("default") == "NJD"), None)
        check("standings contains NJD", njd is not None)
        if njd:
            check("NJD wins exists", "wins" in njd, f"wins={njd.get('wins')}")
            check("NJD losses exists", "losses" in njd, f"losses={njd.get('losses')}")
            check("NJD otLosses exists", "otLosses" in njd, f"otLosses={njd.get('otLosses')}")
            check("NJD points exists", "points" in njd, f"points={njd.get('points')}")
            check("NJD divisionSequence exists", "divisionSequence" in njd, f"seq={njd.get('divisionSequence')}")
            check("NJD divisionName exists", "divisionName" in njd, f"div={njd.get('divisionName')}")


def check_mlb():
    print("\n--- Checking MLB / Yankees ---")
    today = datetime.now().strftime("%Y-%m-%d")
    sched_url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&teamId=147&startDate={today}&endDate={today}&hydrate=linescore,team"
    sched = fetch_json(sched_url)
    if sched:
        check("schedule response totalGames exists", "totalGames" in sched, f"totalGames={sched.get('totalGames')}")

    current_year = datetime.now().year
    standings_url = f"https://statsapi.mlb.com/api/v1/standings?leagueId=103&season={current_year}&standingsTypes=regularSeason&fields=records,division,id,teamRecords,team,id,divisionRank,gamesBack,wins,losses"
    standings = fetch_json(standings_url)
    if standings:
        nyy_rec = None
        for rec in standings.get("records", []):
            for tr in rec.get("teamRecords", []):
                if tr.get("team", {}).get("id") == 147:
                    nyy_rec = tr
                    break
        check("MLB standings contains Yankees (147)", nyy_rec is not None)
        if nyy_rec:
            check("Yankees divisionRank exists", "divisionRank" in nyy_rec, f"rank={nyy_rec.get('divisionRank')}")
            check("Yankees wins exists", "wins" in nyy_rec, f"wins={nyy_rec.get('wins')}")
            check("Yankees losses exists", "losses" in nyy_rec, f"losses={nyy_rec.get('losses')}")


def check_sleeper():
    print("\n--- Checking Sleeper Fantasy ---")
    state_url = "https://api.sleeper.app/v1/state/nfl"
    state = fetch_json(state_url)
    if state:
        check("state week exists", "week" in state, f"week={state.get('week')}")
        check("state season_type exists", "season_type" in state, f"type={state.get('season_type')}")
        check("state season exists", "season" in state, f"season={state.get('season')}")
        week = state.get("week")
        season = state.get("season")
    else:
        week = 6
        season = 2026

    user_url = "https://api.sleeper.app/v1/user/pinec0ne"
    user = fetch_json(user_url)
    if user:
        check("user user_id exists", "user_id" in user, f"id={user.get('user_id')}")
        check("user display_name exists", user.get("display_name") == "pinec0ne")

    league_id = "1389359956657967104"
    rosters_url = f"https://api.sleeper.app/v1/league/{league_id}/rosters"
    rosters = fetch_json(rosters_url)
    if rosters:
        check("rosters list has 12 items", len(rosters) == 12, f"len={len(rosters)}")
        user_id = user.get("user_id") if user else "735942590872018944"
        my_roster = next((r for r in rosters if r.get("owner_id") == user_id), None)
        check("user roster found in league", my_roster is not None)
        if my_roster:
            check("my roster roster_id exists", "roster_id" in my_roster, f"roster_id={my_roster.get('roster_id')}")
            settings = my_roster.get("settings", {})
            check("my roster settings.wins exists", "wins" in settings, f"wins={settings.get('wins')}")
            check("my roster settings.losses exists", "losses" in settings, f"losses={settings.get('losses')}")
            check("my roster settings.fpts exists", "fpts" in settings, f"fpts={settings.get('fpts')}")
            check("my roster settings.fpts_decimal exists", "fpts_decimal" in settings)

    users_url = f"https://api.sleeper.app/v1/league/{league_id}/users"
    users = fetch_json(users_url)
    if users:
        check("league users list non-empty", len(users) > 0)
        check("league user display_name exists", "display_name" in users[0])

    matchups_url = f"https://api.sleeper.app/v1/league/{league_id}/matchups/{week}"
    matchups = fetch_json(matchups_url)
    if matchups:
        check("matchups list non-empty", len(matchups) > 0, f"count={len(matchups)}")
        if matchups:
            m = matchups[0]
            check("matchup roster_id exists", "roster_id" in m)
            check("matchup points exists", "points" in m)
            check("matchup starters exists", "starters" in m)

    sched_url = f"https://api.sleeper.app/schedule/nfl/regular/{season}"
    nfl_sched = fetch_json(sched_url)
    if nfl_sched:
        check("NFL schedule list non-empty", len(nfl_sched) > 0, f"count={len(nfl_sched)}")
        if nfl_sched:
            g = nfl_sched[0]
            check("schedule status exists", "status" in g, f"status={g.get('status')}")
            check("schedule week exists", "week" in g, f"week={g.get('week')}")
            check("schedule home exists", "home" in g, f"home={g.get('home')}")
            check("schedule away exists", "away" in g, f"away={g.get('away')}")

    player_url = "https://api.sleeper.com/players/nfl/4046"
    player = fetch_json(player_url)
    if player:
        check("player team exists", "team" in player, f"team={player.get('team')}")
        check("player last_name exists", "last_name" in player, f"name={player.get('last_name')}")
        check("player position exists", "position" in player, f"pos={player.get('position')}")


def check_weather():
    print("\n--- Checking Weather (Open-Meteo) ---")
    weather_url = "https://api.open-meteo.com/v1/forecast?latitude=40.7178&longitude=-74.0431&current=temperature_2m,weather_code&temperature_unit=fahrenheit"
    data = fetch_json(weather_url)
    if data:
        current = data.get("current", {})
        check("current temperature_2m exists", "temperature_2m" in current, f"temp={current.get('temperature_2m')}")
        check("current weather_code exists", "weather_code" in current, f"code={current.get('weather_code')}")


def main():
    print("Running API Contract Checks...")
    check_nfl()
    check_nhl()
    check_mlb()
    check_sleeper()
    check_weather()

    print("\n===============================")
    if failures == 0:
        print("ALL API CONTRACT CHECKS PASSED!")
        sys.exit(0)
    else:
        print(f"{failures} API CONTRACT CHECKS FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
