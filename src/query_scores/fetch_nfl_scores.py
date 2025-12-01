#!/usr/bin/env python3
"""
Fetch NFL scores from footballdb.com.

Provides:
  - Library functions
  - CLI with options for:
      * year / week / type / league   (for HTML scores page)
      * team filter
      * JSON output
      * CSV output
      * optional timing debug
      * HTML homepage/scores page source (default)
      * XHR API source (--use-api) via gamescores.php
      * Hybrid mode (--hybrid) that merges HTML names with API scores
      * Optional polling in hybrid mode (--poll --interval 15)
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, List, Optional

import requests
from bs4 import BeautifulSoup

# Optional pandas import for DataFrame / CSV
try:
    import pandas as pd  # type: ignore
except ImportError:
    pd = None

# Optional lxml parser (faster than html.parser)
try:
    import lxml  # type: ignore  # noqa: F401

    BS_PARSER = "lxml"
except ImportError:
    BS_PARSER = "html.parser"


BASE_URL = "https://www.footballdb.com/"
GAMESCORES_URL = "https://www.footballdb.com/data/gamescores.php"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.footballdb.com/",
    "Connection": "keep-alive",
}

# For the XHR API endpoint we tweak headers slightly
HEADERS_API = dict(HEADERS)
HEADERS_API["Accept"] = "*/*"
HEADERS_API["X-Requested-With"] = "XMLHttpRequest"


@dataclass
class GameScore:
    game_id: Optional[str]
    date: str
    status: str
    away_team: Optional[str]
    away_score: Optional[int]
    home_team: Optional[str]
    home_score: Optional[int]


# ------------------------------------------------------------
# URL builder (for HTML scores page)
# ------------------------------------------------------------
def build_scores_url(
    league: str = "NFL",
    year: Optional[int] = None,
    gametype: str = "reg",
    week: Optional[int] = None,
    use_homepage: bool = False,
) -> str:
    """
    Build the URL to fetch scores from (HTML version).

    If use_homepage is True OR (year or week) is missing, returns the homepage.
    Otherwise returns the week/season-specific scores URL, e.g.:

      https://www.footballdb.com/scores/index.html?lg=NFL&yr=2025&type=reg&wk=13
    """
    if use_homepage or year is None or week is None:
        return BASE_URL

    league = league.upper()
    return (
        f"{BASE_URL.rstrip('/')}/scores/index.html"
        f"?lg={league}&yr={year}&type={gametype}&wk={week}"
    )


def _get_session(headers: Optional[dict] = None) -> requests.Session:
    """
    Create a requests.Session with browser-like headers.
    """
    session = requests.Session()
    session.headers.update(headers or HEADERS)
    return session


# ------------------------------------------------------------
# Shared HTML parsing helper
# ------------------------------------------------------------
def _parse_live_scores_from_root(
    root: BeautifulSoup,
    url: str,
    debug_timing: bool,
    t0: float,
    t1: float,
    t2: float,
) -> List[GameScore]:
    """
    Given a BeautifulSoup root that contains score tables, parse into GameScore list.
    """
    live_div = root.find("div", id="divLiveScores") or root

    games: List[GameScore] = []

    # Directly select all score tables inside the container
    for table in live_div.select("table.scoreboard_hp_tbl"):
        header_row = table.select_one("thead tr.header")
        if not header_row:
            continue

        date_cell = header_row.select_one("td.left")
        status_cell = header_row.select_one("td.center")

        date_text = date_cell.get_text(strip=True) if date_cell else ""
        status_text = status_cell.get_text(strip=True) if status_cell else ""

        game_id: Optional[str] = None
        if status_cell and status_cell.has_attr("id"):
            sid = status_cell["id"]
            if sid.startswith("gstatus_"):
                game_id = sid[len("gstatus_"):]

        body_rows = table.select("tbody tr.rowall")
        if len(body_rows) != 2:
            # Unexpected structure; skip this record
            continue

        away_row, home_row = body_rows

        def parse_team_row(row):
            tds = row.find_all("td")
            if len(tds) < 2:
                return None, None
            team_name = tds[0].get_text(strip=True)
            score_text = tds[1].get_text(strip=True)
            try:
                score_val = int(score_text)
            except ValueError:
                score_val = None  # "--" or blank when not started
            return team_name, score_val

        away_team, away_score = parse_team_row(away_row)
        home_team, home_score = parse_team_row(home_row)

        games.append(
            GameScore(
                game_id=game_id,
                date=date_text,
                status=status_text,
                away_team=away_team,
                away_score=away_score,
                home_team=home_team,
                home_score=home_score,
            )
        )

    t3 = time.perf_counter()

    if debug_timing:
        print(
            "timing (HTML): "
            f"network={t1 - t0:.3f}s, "
            f"parse={t2 - t1:.3f}s, "
            f"build={t3 - t2:.3f}s, "
            f"total={t3 - t0:.3f}s"
        )

    return games


# ------------------------------------------------------------
# HTML homepage / scores page scraper
# ------------------------------------------------------------
def fetch_live_scores(
    url: Optional[str] = None,
    session: Optional[requests.Session] = None,
    debug_timing: bool = False,
) -> List[GameScore]:
    """
    Fetch scores by scraping the HTML page (homepage or scores page).
    """
    if url is None:
        url = BASE_URL

    if session is None:
        session = _get_session(HEADERS)

    t0 = time.perf_counter()
    resp = session.get(url, timeout=10)
    t1 = time.perf_counter()

    if resp.status_code == 403:
        raise RuntimeError(
            f"Got 403 Forbidden from Footballdb for URL {url!r}. "
            "They may be blocking this client/user agent."
        )

    resp.raise_for_status()

    # Use lxml if available, else html.parser
    soup = BeautifulSoup(resp.text, BS_PARSER)
    t2 = time.perf_counter()

    return _parse_live_scores_from_root(soup, url, debug_timing, t0, t1, t2)


# ------------------------------------------------------------
# API JSON → GameScore mapper for gamescores.php
# ------------------------------------------------------------
def _games_from_api_json(data: Any) -> List[GameScore]:
    """
    Convert gamescores.php JSON into GameScore objects.

    JSON looks like:
      {
        "livescores": 0 or 1,
        "games": [
          {
            "gameid": "2025113001",
            "status": 1,
            "scorev": "25",
            "scoreh": "3",
            "period": "",
            "clock": "",
            "gamestatus": "FINAL",
            "gameurl": "/games/boxscore/arizona-cardinals-vs-baltimore-ravens-2025113001"
          },
          ...
        ]
      }

    IMPORTANT: gameurl's team slugs are NOT reliable (site bug),
    so we do NOT derive team names from gameurl here.
    Only scores, status, date, and game_id are trusted.
    """

    games: List[GameScore] = []

    game_list = []
    if isinstance(data, dict) and isinstance(data.get("games"), list):
        game_list = data["games"]
    elif isinstance(data, list):
        game_list = data
    else:
        return games  # unknown structure

    for g in game_list:
        if not isinstance(g, dict):
            continue

        game_id = g.get("gameid")
        status_str = str(g.get("gamestatus", ""))  # e.g. "FINAL", "8:20 PM"
        scorev = g.get("scorev")
        scoreh = g.get("scoreh")

        # --- Date from gameid (YYYYMMDDxx) ---
        date_str = ""
        if isinstance(game_id, str) and len(game_id) >= 8:
            try:
                d = datetime.strptime(game_id[:8], "%Y%m%d")
                # Match "Sun 11/30" style
                date_str = d.strftime("%a %m/%d")
            except ValueError:
                date_str = game_id[:8]

        def score_to_int(val: Any) -> Optional[int]:
            if val in (None, "--", ""):
                return None
            try:
                return int(val)
            except (TypeError, ValueError):
                return None

        away_score = score_to_int(scorev)
        home_score = score_to_int(scoreh)

        games.append(
            GameScore(
                game_id=str(game_id) if game_id is not None else None,
                date=date_str,
                status=status_str,
                away_team=None,  # hybrid mode will fill these from HTML
                away_score=away_score,
                home_team=None,
                home_score=home_score,
            )
        )

    return games


# ------------------------------------------------------------
# XHR API scraper (gamescores.php)
# ------------------------------------------------------------
def fetch_live_scores_api(
    session: Optional[requests.Session] = None,
    debug_timing: bool = False,
) -> List[GameScore]:
    """
    Fetch scores from the XHR endpoint:

        https://www.footballdb.com/data/gamescores.php

    This is what the homepage uses via XMLHttpRequest.

    It returns JSON like:
      {"livescores":0,"games":[{...}, ...]}

    We map that into GameScore objects.
    """
    url = GAMESCORES_URL

    if session is None:
        session = _get_session(HEADERS_API)

    t0 = time.perf_counter()
    resp = session.get(url, timeout=10)
    t1 = time.perf_counter()

    if resp.status_code == 403:
        raise RuntimeError(
            f"Got 403 Forbidden from Footballdb API for URL {url!r}. "
            "They may be blocking this client/user agent."
        )

    resp.raise_for_status()
    text = resp.text
    stripped = text.lstrip()

    # Should be JSON for gamescores.php
    if stripped.startswith("{") or stripped.startswith("["):
        data = resp.json()
        t2 = time.perf_counter()
        games = _games_from_api_json(data)
        t3 = time.perf_counter()

        if debug_timing:
            print(
                "timing (API JSON): "
                f"network={t1 - t0:.3f}s, "
                f"parse_json={t2 - t1:.3f}s, "
                f"convert={t3 - t2:.3f}s, "
                f"total={t3 - t0:.3f}s"
            )

        return games

    # Fallback: treat as HTML fragment (shouldn't really happen here)
    soup = BeautifulSoup(text, BS_PARSER)
    t2 = time.perf_counter()
    return _parse_live_scores_from_root(soup, url, debug_timing, t0, t1, t2)


# ------------------------------------------------------------
# Hybrid helper: merge HTML (names) + API (scores/status)
# ------------------------------------------------------------
def merge_html_and_api(html_games: List[GameScore], api_games: List[GameScore]) -> List[GameScore]:
    """
    Merge API scores/status into HTML games in-place, keyed by game_id.

    - html_games: from fetch_live_scores() (has names, initial status)
    - api_games: from fetch_live_scores_api() (fast scores, status, date, ids)

    Returns the same list object as html_games, with scores/status updated.
    """
    # Map HTML games by game_id
    mapping = {g.game_id: g for g in html_games if g.game_id}

    for ag in api_games:
        gid = ag.game_id
        if not gid or gid not in mapping:
            continue
        base = mapping[gid]
        # Update scores & status (keep names from HTML)
        if ag.date:
            base.date = ag.date
        base.status = ag.status
        if ag.away_score is not None:
            base.away_score = ag.away_score
        if ag.home_score is not None:
            base.home_score = ag.home_score

    return html_games


# ------------------------------------------------------------
# Sorting helpers
# ------------------------------------------------------------
def classify_game_status(status: str) -> str:
    """
    Classify a game's status into one of: 'live', 'upcoming', 'ended'.

    Uses simple heuristics based on the status string, which typically looks like:
      - 'FINAL', 'FINAL OT'
      - '8:42 4th', '2:15 2nd', 'Halftime'
      - '8:15 PM', '4:25 PM'
    """
    s = (status or "").strip().upper()

    if not s:
        return "upcoming"  # safest assumption

    # Finished games
    if s.startswith("FINAL"):
        return "ended"

    # Not started yet (kickoff time or scheduled)
    if "AM" in s or "PM" in s or s in {"POSTPONED", "TBA"}:
        return "upcoming"

    # Everything else is in progress: "1ST", "2ND", "3RD", "4TH", "OT", "HALFTIME", etc.
    return "live"


def parse_game_datetime_from_id(game: GameScore) -> Optional[datetime]:
    """
    Parse a datetime from game_id, which looks like 'YYYYMMDDNN' (e.g. '2025113001').

    Returns a datetime for the *date* only. We don't know exact kickoff time,
    but using the date is good enough for ordering within groups.
    """
    gid = game.game_id
    if not gid or len(gid) < 8:
        return None
    try:
        return datetime.strptime(gid[:8], "%Y%m%d")
    except ValueError:
        return None


def sort_games(games: List[GameScore]) -> List[GameScore]:
    """
    Sort games in-place and return them, using the following priority:

      1) live games (in progress)
      2) upcoming games (not yet started)
      3) ended games (finished), with newest first, oldest last

    Within each group, we use the game date (from game_id) as a tiebreaker.
    """

    def key(g: GameScore):
        cls = classify_game_status(g.status)
        rank_map = {"live": 0, "upcoming": 1, "ended": 2}
        rank = rank_map.get(cls, 3)

        dt = parse_game_datetime_from_id(g)
        # If we can't parse a date, push it to the far past
        ts = dt.timestamp() if dt is not None else 0.0

        # For ended games we want *newest first*, so use -ts
        if cls == "ended":
            ts_key = -ts
        else:
            ts_key = ts

        # Tie-breaker on game_id to make ordering stable
        gid = g.game_id or ""
        return (rank, ts_key, gid)

    games.sort(key=key)
    return games


# ------------------------------------------------------------
# Filtering, DataFrame, printing
# ------------------------------------------------------------
def filter_games_by_team(games: List[GameScore], team_query: str) -> List[GameScore]:
    """
    Return only games where the team_query (case-insensitive substring)
    appears in either the away or home team name.
    """
    if not team_query:
        return games

    q = team_query.lower()
    return [
        g
        for g in games
        if q in (g.away_team or "").lower() or q in (g.home_team or "").lower()
    ]


def scores_to_dataframe(games: List[GameScore]):
    """
    Convert a list of GameScore objects to a pandas DataFrame.

    Columns:
      game_id, date, status, away_team, away_score, home_team, home_score

    Requires pandas to be installed.
    """
    if pd is None:
        raise ImportError(
            "pandas is required for DataFrame/CSV operations.\n"
            "Install it with:  pip install pandas"
        )
    return pd.DataFrame([asdict(g) for g in games])


def format_game_line(g: GameScore, show_id: bool = True) -> str:
    """
    Format a single GameScore for display.
    Handles cases where team names are missing (API-only mode).
    """
    away_score = "--" if g.away_score is None else g.away_score
    home_score = "--" if g.home_score is None else g.home_score

    if g.away_team and g.home_team:
        # Full info (HTML or hybrid)
        core = f"{g.away_team} {away_score} @ {g.home_team} {home_score}"
    else:
        # API-only: no reliable team names
        core = f"Game {g.game_id}: {away_score} @ {home_score}"

    if show_id and g.game_id:
        suffix = f"{g.status} (id={g.game_id})"
    else:
        suffix = g.status

    return f"{g.date:<10} | {core} | {suffix}"


def print_scoreboard(games: List[GameScore], show_id: bool = True) -> None:
    if not games:
        print("No games found for the given filters.")
        return
    for g in games:
        print(format_game_line(g, show_id=show_id))


# ------------------------------------------------------------
# CLI
#-------------------------------------------------------------
def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="Fetch NFL scores from footballdb.com")

    p.add_argument("-l", "--league", default="NFL", help="League code (default: NFL)")
    p.add_argument(
        "-y",
        "--year",
        type=int,
        help="Season year (e.g. 2025). If omitted, homepage is used unless --use-homepage is set.",
    )
    p.add_argument(
        "-t",
        "--type",
        default="reg",
        help="Game type, e.g. reg, pst, pre (default: reg)",
    )
    p.add_argument(
        "-w",
        "--week",
        type=int,
        help="Week number (e.g. 13). If omitted, homepage is used unless --use-homepage is set.",
    )
    p.add_argument(
        "--use-homepage",
        action="store_true",
        help="Ignore year/week/type and just scrape the main homepage (HTML).",
    )

    p.add_argument(
        "--use-api",
        action="store_true",
        help="Use the XHR API endpoint (gamescores.php) instead of the HTML page.",
    )

    p.add_argument(
        "--hybrid",
        action="store_true",
        help="Hybrid mode: HTML once for team names + API for fast scores.",
    )

    p.add_argument(
        "--poll",
        action="store_true",
        help="In --hybrid mode, keep polling the API and updating scores until Ctrl+C.",
    )
    p.add_argument(
        "--interval",
        type=float,
        default=15.0,
        help="Polling interval in seconds for --poll (default: 15).",
    )

    p.add_argument(
        "-T",
        "--team",
        help="Filter to games involving this team (case-insensitive substring match).",
    )
    p.add_argument("--json", action="store_true", help="Output JSON snapshot instead of text.")
    p.add_argument(
        "--csv",
        metavar="OUTFILE",
        help="Save a snapshot of results to a CSV file (requires pandas).",
    )
    p.add_argument(
        "--debug-timing",
        action="store_true",
        help="Print timing info for network/parse/build.",
    )

    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)

    # If both --hybrid and --use-api are passed, prefer hybrid.
    if args.hybrid and args.use_api:
        print("Note: --hybrid implies API+HTML; ignoring --use-api.")
        args.use_api = False

    if args.poll and not args.hybrid:
        print("Warning: --poll is currently only supported in --hybrid mode. Ignoring --poll.")
        args.poll = False

    # ------------------------------
    # HYBRID MODE
    # ------------------------------
    if args.hybrid:
        # 1) HTML baseline for team names
        url = build_scores_url(
            league=args.league,
            year=args.year,
            gametype=args.type,
            week=args.week,
            use_homepage=args.use_homepage,
        )
        session_html = _get_session(HEADERS)
        base_games = fetch_live_scores(
            url=url,
            session=session_html,
            debug_timing=args.debug_timing,
        )

        # Apply team filter early (we only care about these games)
        if args.team:
            games = filter_games_by_team(base_games, args.team)
        else:
            games = base_games

        # 2) Initial API fetch to update scores/status
        session_api = _get_session(HEADERS_API)
        api_games = fetch_live_scores_api(
            session=session_api,
            debug_timing=args.debug_timing,
        )
        merge_html_and_api(games, api_games)

        # sort snapshot
        games = sort_games(games)

        # Snapshot outputs (before polling)
        if args.csv:
            df = scores_to_dataframe(games)
            df.to_csv(args.csv, index=False)
            print(f"Saved CSV snapshot → {args.csv}")

        if args.json:
            print(json.dumps([asdict(g) for g in games], indent=2))
            if not args.poll:
                return
            else:
                print("Note: JSON snapshot printed once; continuing polling with text output...")

        # Initial scoreboard print
        print_scoreboard(games)

        # Optional polling loop
        if args.poll:
            try:
                while True:
                    time.sleep(args.interval)
                    api_games = fetch_live_scores_api(
                        session=session_api,
                        debug_timing=args.debug_timing,
                    )
                    merge_html_and_api(games, api_games)

                    # keep list sorted each update
                    games = sort_games(games)

                    print("\n" + "-" * 60)
                    ts = time.strftime("[%Y-%m-%d %H:%M:%S]")
                    print(f"{ts} Poll update:")
                    print_scoreboard(games)
            except KeyboardInterrupt:
                print("\nStopped polling.")
        return

    # ------------------------------
    # PURE API MODE (no names, just scores/status)
    # ------------------------------
    if args.use_api:
        session = _get_session(HEADERS_API)
        games = fetch_live_scores_api(
            session=session,
            debug_timing=args.debug_timing,
        )

        if args.team:
            games = filter_games_by_team(games, args.team)

        # sort for API mode too
        games = sort_games(games)

        if args.csv:
            df = scores_to_dataframe(games)
            df.to_csv(args.csv, index=False)
            print(f"Saved CSV → {args.csv}")

        if args.json:
            print(json.dumps([asdict(g) for g in games], indent=2))
            return

        print_scoreboard(games)
        return

    # ------------------------------
    # PURE HTML MODE (original scraper)
    # ------------------------------
    url = build_scores_url(
        league=args.league,
        year=args.year,
        gametype=args.type,
        week=args.week,
        use_homepage=args.use_homepage,
    )
    session = _get_session(HEADERS)
    games = fetch_live_scores(
        url=url,
        session=session,
        debug_timing=args.debug_timing,
    )

    if args.team:
        games = filter_games_by_team(games, args.team)

    # apply unified sort
    games = sort_games(games)

    if args.csv:
        df = scores_to_dataframe(games)
        df.to_csv(args.csv, index=False)
        print(f"Saved CSV → {args.csv}")

    if args.json:
        print(json.dumps([asdict(g) for g in games], indent=2))
        return

    print_scoreboard(games)


if __name__ == "__main__":
    main()
