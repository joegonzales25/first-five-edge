import pandas as pd
from zoneinfo import ZoneInfo

from basketball_model import (
    CBB_CONFIG,
    TeamState,
    agent_notes,
    backtest_csv,
    backtest_games,
    calculate_edge_score,
    confidence_from_margin,
    rating_for,
    scoring_reasons,
    side_reasons,
    total_edge_label,
    update_team,
)
from cbb_data import load_cbb_current_season
from nba_agent import key_factors_summary, split_notes


def build_historical_lab(games_csv, season=None):
    results, summary = backtest_csv(games_csv, league="CBB", season=season)
    return prepare_basketball_lab(results), summary


def backtest_schedule(games: pd.DataFrame, season=None):
    results, summary = backtest_games(games, league="CBB", season=season)
    return prepare_basketball_lab(results), summary


def format_game_time(raw_value):
    if pd.isna(raw_value) or not raw_value:
        return "TBD"
    try:
        game_dt = pd.to_datetime(raw_value)
        if game_dt.tzinfo is not None:
            game_dt = game_dt.tz_convert(ZoneInfo("America/New_York"))
        return game_dt.strftime("%a %b %d, %I:%M %p")
    except Exception:
        return str(raw_value)


def eastern_game_date(raw_value):
    game_dt = pd.to_datetime(raw_value)
    if game_dt.tzinfo is not None:
        game_dt = game_dt.tz_convert(ZoneInfo("America/New_York"))
    return game_dt.date()


def status_for_game(game):
    if bool(game.get("completed")):
        return "Final"
    return game.get("status") or "Scheduled"


def completed_games_for_lab(games: pd.DataFrame) -> pd.DataFrame:
    if games.empty:
        return games
    return games[
        games["completed"]
        & games["away_score"].notna()
        & games["home_score"].notna()
    ].copy()


def build_current_season_lab(season=None, today=None):
    games = load_cbb_current_season(season=season, today=today)
    completed = completed_games_for_lab(games)
    return backtest_schedule(completed, season=season)


def side_result_for_game(side_edge, predicted_winner, actual_winner, completed):
    if side_edge == "Pass":
        return "No Signal"
    if not completed or actual_winner is None:
        return "Pending"
    if predicted_winner == actual_winner:
        return "Correct"
    return "Missed"


def scoring_result_for_game(scoring_edge, actual_total, league_total, completed):
    if scoring_edge == "Neutral Scoring Environment":
        return "No Signal"
    if not completed or actual_total is None:
        return "Pending"
    if scoring_edge == "High Scoring Environment":
        return "Correct" if actual_total > league_total else "Missed"
    if scoring_edge == "Low Scoring Environment":
        return "Correct" if actual_total < league_total else "Missed"
    return "No Signal"


def apply_uncertainty_cap(confidence, neutral_site=False):
    if neutral_site and confidence == "A":
        return "B"
    return confidence


def side_edge_label(model_margin, away, home, confidence):
    if confidence == "Pass":
        return "Pass"
    team = home if model_margin > 0 else away
    return f"{team} Edge"


def model_signal_display(side_edge, scoring_edge):
    signals = []
    if side_edge != "Pass":
        signals.append(side_edge)
    if scoring_edge != "Neutral Scoring Environment":
        signals.append(scoring_edge)
    return " / ".join(signals) if signals else "Pass"


def cbb_side_reasons(
    away,
    home,
    away_rating,
    home_rating,
    home_court,
    rest_edge,
    model_margin,
    away_games,
    home_games,
    neutral_site,
):
    reasons = side_reasons(
        away,
        home,
        away_rating,
        home_rating,
        0.0 if neutral_site else home_court,
        rest_edge,
        model_margin,
        CBB_CONFIG,
        away_games,
        home_games,
    )
    if neutral_site:
        reasons.append("Neutral-site context caps confidence until tested")
    if min(away_games, home_games) < CBB_CONFIG.min_c_games:
        reasons.append("Schedule-strength gate blocks official pick")
    return reasons


def build_current_slate(season=None, today=None, days_ahead=14, slate_date=None):
    config = CBB_CONFIG
    target_date = slate_date or today or pd.Timestamp.today().date()
    games = load_cbb_current_season(
        season=season,
        today=target_date,
        days_ahead=days_ahead,
    )
    if games.empty:
        return pd.DataFrame(), {"empty_reason": "no_games"}

    states: dict[str, TeamState] = {}
    league_totals = []
    rows = []
    target_date = pd.Timestamp(target_date).date()

    for _, game in games.sort_values(["game_date_dt", "game_id"]).iterrows():
        away = game["away_team"]
        home = game["home_team"]
        completed = bool(game.get("completed"))
        away_score = game.get("away_score")
        home_score = game.get("home_score")
        neutral_site = bool(game.get("neutral_site"))

        league_total = (
            sum(league_totals) / len(league_totals)
            if league_totals
            else config.default_total
        )
        league_points = league_total / 2
        away_state = states.setdefault(away, TeamState())
        home_state = states.setdefault(home, TeamState())
        away_rating = rating_for(away_state, league_points, config)
        home_rating = rating_for(home_state, league_points, config)
        rest_edge = float(game.get("home_rest", 0) or 0) - float(
            game.get("away_rest", 0) or 0
        )
        home_court = 0.0 if neutral_site else config.home_court
        model_margin = (
            home_rating
            - away_rating
            + home_court
            + (rest_edge * config.rest_weight)
        )

        away_total_base = (
            away_state.points_for_avg(league_points)
            + home_state.points_against_avg(league_points)
        ) / 2
        home_total_base = (
            home_state.points_for_avg(league_points)
            + away_state.points_against_avg(league_points)
        ) / 2
        recent_total_context = (
            away_state.total_avg(league_total) + home_state.total_avg(league_total)
        ) / 2
        matchup_total_weight = 0.78 - config.pace_weight
        projected_total = (
            (away_total_base + home_total_base) * matchup_total_weight
            + league_total * 0.22
            + recent_total_context * config.pace_weight
        )
        confidence = confidence_from_margin(
            model_margin,
            config,
            away_state.games,
            home_state.games,
        )
        confidence = apply_uncertainty_cap(confidence, neutral_site=neutral_site)
        side_edge = side_edge_label(model_margin, away, home, confidence)
        scoring_edge = total_edge_label(projected_total, league_total, config)
        edge_score = calculate_edge_score(
            model_margin,
            projected_total,
            league_total,
            confidence,
        )
        side_notes = cbb_side_reasons(
            away,
            home,
            away_rating,
            home_rating,
            config.home_court,
            rest_edge,
            model_margin,
            away_state.games,
            home_state.games,
            neutral_site,
        )
        scoring_notes = scoring_reasons(
            away,
            home,
            projected_total,
            league_total,
            scoring_edge,
            away_state.total_avg(league_total),
            home_state.total_avg(league_total),
        )
        notes = agent_notes(side_notes, scoring_notes)
        predicted_winner = home if model_margin > 0 else away
        actual_winner = None
        actual_total = None
        side_result = side_result_for_game(
            side_edge,
            predicted_winner,
            actual_winner,
            completed,
        )
        scoring_result = scoring_result_for_game(
            scoring_edge,
            actual_total,
            league_total,
            completed,
        )

        if completed and pd.notna(away_score) and pd.notna(home_score):
            away_score_int = int(away_score)
            home_score_int = int(home_score)
            actual_winner = home if home_score_int > away_score_int else away
            actual_total = away_score_int + home_score_int
            side_result = side_result_for_game(
                side_edge,
                predicted_winner,
                actual_winner,
                completed,
            )
            scoring_result = scoring_result_for_game(
                scoring_edge,
                actual_total,
                league_total,
                completed,
            )

        game_day = eastern_game_date(game["game_date_dt"])
        if game_day == target_date:
            rows.append(
                {
                    "Sport": "CBB",
                    "Game ID": game.get("game_id"),
                    "Season": int(game["season"]) if pd.notna(game["season"]) else None,
                    "Game Time": format_game_time(game["game_date_dt"]),
                    "Sort Date": game["game_date_dt"],
                    "Game": f"{away} @ {home}",
                    "Away": away,
                    "Home": home,
                    "Away Score": int(away_score)
                    if completed and pd.notna(away_score)
                    else None,
                    "Home Score": int(home_score)
                    if completed and pd.notna(home_score)
                    else None,
                    "Actual Winner": actual_winner,
                    "Predicted Winner": predicted_winner,
                    "Actual Total": actual_total,
                    "Model Signal": model_signal_display(side_edge, scoring_edge),
                    "Edge Score": edge_score,
                    "Confidence": confidence,
                    "Side Edge": side_edge,
                    "Scoring Edge": scoring_edge,
                    "Early Edge": "First Half Pending",
                    "Side Result": side_result,
                    "Winner Result": side_result,
                    "Scoring Result": scoring_result,
                    "Model Margin": round(model_margin, 2),
                    "Projected Total": round(projected_total, 2),
                    "League Total Baseline": round(league_total, 2),
                    "Away Prior Games": away_state.games,
                    "Home Prior Games": home_state.games,
                    "Rest Edge": round(rest_edge, 2),
                    "Neutral Site": neutral_site,
                    "Key Factors Summary": key_factors_summary(notes),
                    "Key Factors List": split_notes(notes),
                    "Agent Notes": notes,
                    "Status": status_for_game(game),
                }
            )

        if completed and pd.notna(away_score) and pd.notna(home_score):
            update_team(states, away, int(away_score), int(home_score))
            update_team(states, home, int(home_score), int(away_score))
            league_totals.append(int(away_score) + int(home_score))

    slate = pd.DataFrame(rows)
    if not slate.empty:
        slate = slate.sort_values(["Sort Date", "Game"])
    return slate, {"season": season or target_date.year, "slate_date": target_date}


def prepare_basketball_lab(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return results

    prepared = results.copy()
    prepared["Status"] = "Final"
    prepared["Game Time"] = prepared["Game Date"]
    prepared["Early Edge"] = "First Half Pending"
    prepared["Key Factors Summary"] = prepared["Agent Notes"].apply(
        key_factors_summary
    )
    prepared["Key Factors List"] = prepared["Agent Notes"].apply(split_notes)
    prepared["Winner Result"] = prepared["Winner Correct"].apply(
        lambda value: "Correct" if bool(value) else "Missed"
    )
    prepared["Scoring Result"] = prepared["Scoring Correct"].apply(
        lambda value: "Correct" if bool(value) else "Missed"
    )
    return prepared


def historical_summary_tables(results: pd.DataFrame) -> dict[str, pd.DataFrame]:
    from nba_agent import historical_summary_tables as nba_historical_summary_tables

    return nba_historical_summary_tables(results)
