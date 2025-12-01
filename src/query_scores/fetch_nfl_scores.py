#!/usr/bin/env python3
"""
Fetch NFL scores from footballdb.com.

Provides:
  - Library API (import functions)
  - CLI with optional CSV output:  --csv out.csv
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

# Optional pandas import for CSV & DataFrame
try:
    import pandas as pd
except ImportError:
    pd = None


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


# ---------------------------
# URL builder
# ---------------------------
def build_scores_url(
    league: str = "NFL",
    year: Optional[int] = None,
    gametype: str = "reg",
    week: Optional[int] = None,
    use_homepage: bool = False,
) -> str:
    if use_homepage or year is None or week is None:
        return BASE_URL

    league = league.upper()
    return (
        f"{BASE_URL.rstrip('/')}/scores/index.html"
        f"?lg={league}&yr={year}&type={gametype}&wk={week}"
    )


def _get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


# ---------------------------
# Score scraper
# ---------------------------
def fetch_live_scores(
    url: Optional[str] = None,
    session: Optional[requests.Session] = None,
) -> List[GameScore]:

    if url is None:
        url = BASE_URL

    if session is None:
        session = _get_session()

    resp = session.get(url, timeout=10)
    if resp.status_code == 403:
        raise RuntimeError(
            f"Got 403 Forbidden from Footballdb for URL {url!r}. "
            "They may be blocking this client/user agent."
        )

    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    live_div = soup.find("div", id="divLiveScores")
    if not live_div:
        raise RuntimeError("Could not find scores on the page.")

    games: List[GameScore] = []

    for game_div in live_div.find_all("div", recursive=False):
        table = game_div.find("table", class_="scoreboard_hp_tbl")
        if not table:
            continue

        header_row = table.find("tr", class_="header")
        if not header_row:
            continue

        date_cell = header_row.find("td", class_="left")
        status_cell = header_row.find("td", class_="center")

        date_text = date_cell.get_text(strip=True) if date_cell else ""
        status_text = status_cell.get_text(strip=True) if status_cell else ""

        game_id = None
        if status_cell and status_cell.has_attr("id"):
            sid = status_cell["id"]
            if sid.startswith("gstatus_"):
                game_id = sid[len("gstatus_"):]

        tbody = table.find("tbody")
        rows = tbody.find_all("tr", class_="rowall", recursive=False)
        if len(rows) != 2:
            continue

        away_row, home_row = rows

        def parse_team_row(row):
            tds = row.find_all("td")
            team_name = tds[0].get_text(strip=True)
            score_text = tds[1].get_text(strip=True)
            try:
                score_val = int(score_text)
            except ValueError:
                score_val = None
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

    return games


# ---------------------------
# Filtering & DataFrame
# ---------------------------
def filter_games_by_team(games: List[GameScore], team_query: str):
    q = team_query.lower()
    return [
        g for g in games
        if q in (g.away_team or "").lower()
        or q in (g.home_team or "").lower()
    ]


def scores_to_dataframe(games: List[GameScore]):
    if pd is None:
        raise ImportError(
            "pandas is required for DataFrame/CSV operations.\n"
            "Install it with:  pip install pandas"
        )
    return pd.DataFrame([asdict(g) for g in games])


# ---------------------------
# CLI
# ---------------------------
def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="Fetch NFL scores from footballdb.com")

    p.add_argument("-l", "--league", default="NFL")
    p.add_argument("-y", "--year", type=int)
    p.add_argument("-t", "--type", default="reg")
    p.add_argument("-w", "--week", type=int)
    p.add_argument("--use-homepage", action="store_true")

    p.add_argument("-T", "--team", help="Filter to only games with this team")
    p.add_argument("--json", action="store_true", help="Output JSON")

    # NEW OPTION:
    p.add_argument("--csv", metavar="OUTFILE", help="Save results to a CSV file")

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
    games = fetch_live_scores(url=url, session=session)

    if args.team:
        games = filter_games_by_team(games, args.team)

    # CSV OUTPUT (NEW)
    if args.csv:
        df = scores_to_dataframe(games)
        df.to_csv(args.csv, index=False)
        print(f"Saved CSV → {args.csv}")

    # JSON OUTPUT
    if args.json:
        print(json.dumps([asdict(g) for g in games], indent=2))
        return

    # Human-readable printout
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
