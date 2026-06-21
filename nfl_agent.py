from datetime import date, datetime

import pandas as pd

from nfl_backtest import (
    NFLVERSE_GAMES_URL,
    ModelConfig,
    TeamState,
    agent_notes,
    calculate_edge_score,
    confidence_from_margin,
    rating_for,
    scoring_reasons,
    side_reasons,
    total_edge_label,
    update_team,
)


def load_nfl_schedule() -> pd.DataFrame:
    games = pd.read_csv(NFLVERSE_GAMES_URL)
    games = games[games["game_type"] == "REG"].copy()
    games["week"] = games["week"].astype(int)
    games["gameday_dt"] = pd.to_datetime(games["gameday"], errors="coerce")
    return games.sort_values(["season", "week", "gameday", "game_id"])


def split_notes(notes):
    if not notes:
        return []
    return [note.strip() for note in str(notes).split(";") if note.strip()]


def key_factors_summary(notes):
    factors = split_notes(notes)
    if not factors:
        return "Neutral model profile"
    return "; ".join(factors[:2])


def side_edge_display(row):
    if row["Confidence"] == "Pass":
        return "Pass"
    team = row["Home"] if float(row["Model Margin"]) > 0 else row["Away"]
    return f"{team} Edge"


def model_signal_display(side_edge, scoring_edge):
    signals = []
    if side_edge != "Pass":
        signals.append(side_edge)
    if scoring_edge != "Neutral Scoring Environment":
        signals.append(scoring_edge)
    return " / ".join(signals) if signals else "Pass"


def status_for_game(row):
    if pd.notna(row.get("home_score")) and pd.notna(row.get("away_score")):
        return "Final"
    return "Scheduled"


def format_game_time(raw_value):
    if pd.isna(raw_value) or not raw_value:
        return "TBD"

    try:
        game_dt = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00"))
        return game_dt.astimezone().strftime("%a %b %d, %I:%M %p")
    except Exception:
        try:
            return pd.to_datetime(raw_value).strftime("%a %b %d")
        except Exception:
            return str(raw_value)


def format_schedule_time(game):
    gameday = game.get("gameday")
    gametime = game.get("gametime")

    if pd.notna(gameday) and pd.notna(gametime):
        return format_game_time(f"{gameday}T{gametime}")
    return format_game_time(gameday)


def build_historical_lab(season=2025):
    from nfl_backtest import backtest_season

    results, summary = backtest_season(season)
    if results.empty:
        return results, summary

    results = results.copy()
    results["Sport"] = "NFL"
    results["Status"] = "Final"
    results["Game Time"] = "Final"
    results["Side Edge"] = results.apply(side_edge_display, axis=1)
    results["Early Edge"] = "Model Pending"
    results["Model Signal"] = results.apply(
        lambda row: model_signal_display(row["Side Edge"], row["Scoring Edge"]),
        axis=1,
    )
    results["Key Factors Summary"] = results["Agent Notes"].apply(
        key_factors_summary
    )
    results["Key Factors List"] = results["Agent Notes"].apply(split_notes)
    results["Winner Result"] = results["Winner Correct"].apply(
        lambda value: "Correct" if bool(value) else "Missed"
    )
    results["Scoring Result"] = results["Scoring Correct"].apply(
        lambda value: "Correct" if bool(value) else "Missed"
    )

    return results, summary


def latest_upcoming_week(games, today=None):
    today = pd.Timestamp(today or date.today())
    upcoming = games[
        games["away_score"].isna()
        & games["home_score"].isna()
        & games["gameday_dt"].notna()
        & (games["gameday_dt"] >= today)
    ].copy()

    if upcoming.empty:
        return None

    first = upcoming.sort_values(["gameday_dt", "season", "week"]).iloc[0]
    return int(first["season"]), int(first["week"])


def build_current_slate(season=None, week=None, today=None):
    config = ModelConfig()
    games = load_nfl_schedule()

    if season is None or week is None:
        upcoming = latest_upcoming_week(games, today)
        if upcoming is None:
            return pd.DataFrame(), {"empty_reason": "no_upcoming_games"}
        season, week = upcoming

    seasons = [season - 1, season]
    model_games = games[games["season"].isin(seasons)].copy()
    states = {}
    rows = []
    league_totals = []

    for _, game in model_games.iterrows():
        away = game["away_team"]
        home = game["home_team"]
        away_done = pd.notna(game.get("away_score"))
        home_done = pd.notna(game.get("home_score"))
        completed = away_done and home_done

        league_total = (
            sum(league_totals) / len(league_totals) if league_totals else 44.0
        )
        league_points = league_total / 2

        away_state = states.setdefault(away, TeamState())
        home_state = states.setdefault(home, TeamState())
        away_rating = rating_for(away_state, league_points)
        home_rating = rating_for(home_state, league_points)

        rest_edge = float(game.get("home_rest", 7) or 7) - float(
            game.get("away_rest", 7) or 7
        )
        home_field = config.home_field if game.get("location") == "Home" else 0.0
        model_margin = (
            home_rating
            - away_rating
            + home_field
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
        projected_total = (away_total_base + home_total_base) * 0.72 + (
            league_total * 0.28
        )

        confidence = confidence_from_margin(model_margin, config)
        scoring_edge = total_edge_label(projected_total, league_total, config)
        edge_score = calculate_edge_score(
            model_margin,
            projected_total,
            league_total,
            confidence,
        )
        side_notes = side_reasons(
            away,
            home,
            away_rating,
            home_rating,
            home_field,
            rest_edge,
            model_margin,
            config,
        )
        scoring_notes = scoring_reasons(
            away,
            home,
            projected_total,
            league_total,
            scoring_edge,
            away_state.points_for_avg(league_points),
            home_state.points_for_avg(league_points),
            away_state.points_against_avg(league_points),
            home_state.points_against_avg(league_points),
        )
        notes = agent_notes(side_notes, scoring_notes)

        if int(game["season"]) == int(season) and int(game["week"]) == int(week):
            side_edge = "Pass"
            if confidence != "Pass":
                side_edge = f"{home if model_margin > 0 else away} Edge"

            rows.append(
                {
                    "Sport": "NFL",
                    "Season": int(game["season"]),
                    "Week": int(game["week"]),
                    "Game Time": format_schedule_time(game),
                    "Sort Date": game.get("gameday_dt"),
                    "Game": f"{away} @ {home}",
                    "Away": away,
                    "Home": home,
                    "Model Signal": model_signal_display(side_edge, scoring_edge),
                    "Edge Score": edge_score,
                    "Confidence": confidence,
                    "Side Edge": side_edge,
                    "Scoring Edge": scoring_edge,
                    "Early Edge": "Model Pending",
                    "Model Margin": round(model_margin, 2),
                    "Projected Total": round(projected_total, 2),
                    "League Total Baseline": round(league_total, 2),
                    "Key Factors Summary": key_factors_summary(notes),
                    "Key Factors List": split_notes(notes),
                    "Agent Notes": notes,
                    "Status": status_for_game(game),
                }
            )

        if completed:
            away_score = int(game["away_score"])
            home_score = int(game["home_score"])
            update_team(states, away, away_score, home_score)
            update_team(states, home, home_score, away_score)
            league_totals.append(away_score + home_score)

    slate = pd.DataFrame(rows)
    if not slate.empty:
        slate = slate.sort_values(["Sort Date", "Game"])
    return slate, {"season": season, "week": week}


def historical_summary_tables(results):
    if results.empty:
        return pd.DataFrame(), pd.DataFrame()

    confidence_rows = []
    for confidence, group in results.groupby("Confidence"):
        confidence_rows.append(
            {
                "Confidence": confidence,
                "Games": len(group),
                "Winner Accuracy": round(group["Winner Correct"].mean(), 4),
            }
        )

    scoring = results[results["Scoring Edge"] != "Neutral Scoring Environment"]
    scoring_rows = []
    for edge, group in scoring.groupby("Scoring Edge"):
        scoring_rows.append(
            {
                "Scoring Environment": edge,
                "Games": len(group),
                "Accuracy": round(group["Scoring Correct"].mean(), 4),
            }
        )

    return pd.DataFrame(confidence_rows), pd.DataFrame(scoring_rows)
