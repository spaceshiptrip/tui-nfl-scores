"""
query_scores: library for fetching NFL scores from footballdb.com
"""

from .fetch_nfl_scores import (
    GameScore,
    build_scores_url,
    fetch_live_scores,
    filter_games_by_team,
    scores_to_dataframe,
)
