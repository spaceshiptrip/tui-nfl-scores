#!/usr/bin/env python3
"""
Fetch NFL scores from footballdb.com.

Provides:
  - Library functions
  - CLI with options for:
      * year / week / type / league
      * team filter
      * JSON output
      * CSV output
      * optional timing debug
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, asdict
from typing import List, Optional

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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.footballdb.com/",
    "Connection": "keep-alive",
}


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
# URL builder
# ------------------------------------------------------------
def build_scores_url(
    league: str = "NFL",
    year: Optional[int] = None,
    gametype: str = "reg",
    week: Optional[int] = None,
    use_homepage: bool = False,
) -> str:
    """
    Build the URL to fetch scores from.

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


def _get_session() -> requests.Session:
    """
    Create a requests.Session with browser-like headers.
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


# ------------------------------------------------------------
# Core scraper with timing
# ------------------------------------------------------------
def fetch_live_scores(
    url: Optional[str] = None,
    session: Optional[requests.Session] = None,
    debug_timing: bool = False,
) -> List[GameScore]:
    """
    Fetch scores from the given URL and return a list of GameScore objects.

    If debug_timing=True, prints timing for:
      - network
      - parse
      - build
      - total
    """
    if url is None:
        url = BASE_URL

    if session is None:
        session = _get_session()

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

    live_div = soup.find("div", id="divLiveScores")
    if not live_div:
        raise RuntimeError(
            f"Could not find divLiveScores on the page at {url!r}. "
            "The page layout may have changed."
        )

    games: List[GameScore] = []

    # Directly select all score tables inside the live scores div
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
            "timing: "
            f"network={t1 - t0:.3f}s, "
            f"parse={t2 - t1:.3f}s, "
            f"build={t3 - t2:.3f}s, "
            f"total={t3 - t0:.3f}s"
        )

    return games


# ------------------------------------------------------------
# Filtering & DataFrame
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


# ------------------------------------------------------------
# CLI
# ------------------------------------------------------------
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
        help="Ignore year/week/type and just scrape the main homepage.",
    )

    p.add_argument(
        "-T",
        "--team",
        help="Filter to games involving this team (case-insensitive substring match).",
    )
    p.add_argument("--json", action="store_true", help="Output JSON instead of text.")
    p.add_argument(
        "--csv",
        metavar="OUTFILE",
        help="Save results to a CSV file (requires pandas).",
    )
    p.add_argument(
        "--debug-timing",
        action="store_true",
        help="Print timing info for network/parse/build.",
    )

    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)

    url = build_scores_url(
        league=args.league,
        year=args.year,
        gametype=args.type,
        week=args.week,
        use_homepage=args.use_homepage,
    )

    session = _get_session()
    games = fetch_live_scores(
        url=url,
        session=session,
        debug_timing=args.debug_timing,
    )

    if args.team:
        games = filter_games_by_team(games, args.team)

    # CSV output (if requested)
    if args.csv:
        df = scores_to_dataframe(games)
        df.to_csv(args.csv, index=False)
        print(f"Saved CSV → {args.csv}")

    # JSON output (if requested)
    if args.json:
        print(json.dumps([asdict(g) for g in games], indent=2))
        return

    # Human-readable output
    if not games:
        print("No games found for the given filters.")
        return

    for g in games:
        away = "--" if g.away_score is None else g.away_score
        home = "--" if g.home_score is None else g.home_score
        print(
            f"{g.date:<10} | "
            f"{g.away_team} {away} @ {g.home_team} {home} | "
            f"{g.status} (id={g.game_id})"
        )


if __name__ == "__main__":
    main()
