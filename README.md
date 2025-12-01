# Query Scores

This project fetches NFL scores from FootballDB using three modes:

## Modes

### 1. HTML Mode (Default)
Parses the scoreboard HTML and returns full team names, scores, dates, and status.

### 2. API Mode (`--use-api`)
Uses the lightweight `gamescores.php` JSON endpoint for fast score/status polling.
Note: Team names cannot be trusted from this endpoint.

### 3. Hybrid Mode (`--hybrid`)
Loads HTML once to get correct team names, then polls the JSON API on an interval to update scores and statuses.

### Polling Mode
Use:
```
--poll N   # poll every N seconds
--hybrid   # use hybrid mode (recommended for live updates)
```

Example:
```
python src/query_scores/fetch_nfl_scores.py --hybrid --poll 10
```

This prints updated scores every 10 seconds.

## Installation with uv

```
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install .
```

Or install directly from your working directory:

```
uv pip install -e .
```

## CLI Examples

Fetch current week:
```
python src/query_scores/fetch_nfl_scores.py
```

Fetch specific week/season:
```
python src/query_scores/fetch_nfl_scores.py --season 2025 --week 13
```

Use API mode:
```
python src/query_scores/fetch_nfl_scores.py --use-api
```

Use hybrid + polling:
```
python src/query_scores/fetch_nfl_scores.py --hybrid --poll 5
```
