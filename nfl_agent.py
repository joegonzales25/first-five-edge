from datetime import date, datetime
from zoneinfo import ZoneInfo

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

NFL_SIDE_LEAN_MIN = 3.5
NFL_SIDE_WATCH_MIN = 2.0
NFL_SCORING_LEAN_MIN = 1.5
NFL_SCORING_WATCH_MIN = 0.75
NFL_SOURCE_TIMEZONE = ZoneInfo("America/New_York")


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


def parse_schedule_kickoff(game):
    gameday = game.get("gameday")
    gametime = game.get("gametime")
    if pd.isna(gameday):
        return None

    raw_value = f"{gameday}T{gametime}" if pd.notna(gametime) else str(gameday)
    try:
        kickoff = pd.Timestamp(raw_value)
        if kickoff.tzinfo is None:
            kickoff = kickoff.tz_localize(NFL_SOURCE_TIMEZONE)
        return kickoff.tz_convert("UTC")
    except Exception:
        return None


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
    kickoff = parse_schedule_kickoff(game)
    if kickoff is None:
        return format_game_time(game.get("gameday"))
    return kickoff.tz_convert(NFL_SOURCE_TIMEZONE).strftime(
        "%a %b %d, %I:%M %p ET"
    )


def discovery_tier(strength, official_minimum, lean_minimum, watch_minimum):
    strength = abs(float(strength))
    if strength >= official_minimum:
        return "Official"
    if strength >= lean_minimum:
        return "Lean"
    if strength >= watch_minimum:
        return "Watch"
    return "No Edge"


def side_release_values(side_edge, model_margin, predicted_winner, config):
    if side_edge != "Pass":
        return {
            "segment": "Official",
            "pick": predicted_winner,
            "label": None,
        }
    segment = discovery_tier(
        model_margin,
        config.side_c,
        NFL_SIDE_LEAN_MIN,
        NFL_SIDE_WATCH_MIN,
    )
    return {
        "segment": segment,
        "pick": predicted_winner if segment in ["Lean", "Watch"] else None,
        "label": (
            f"{predicted_winner} Side {segment}"
            if segment in ["Lean", "Watch"]
            else None
        ),
    }


def scoring_release_values(scoring_edge, projected_total, league_total, config):
    if scoring_edge != "Neutral Scoring Environment":
        return {
            "segment": "Official",
            "pick": scoring_edge,
            "label": None,
        }
    delta = projected_total - league_total
    segment = discovery_tier(
        delta,
        config.scoring_threshold,
        NFL_SCORING_LEAN_MIN,
        NFL_SCORING_WATCH_MIN,
    )
    direction = (
        "High Scoring Environment"
        if delta >= 0
        else "Low Scoring Environment"
    )
    return {
        "segment": segment,
        "pick": direction if segment in ["Lean", "Watch"] else None,
        "label": (
            f"{direction} {segment}"
            if segment in ["Lean", "Watch"]
            else None
        ),
    }


def grade_side(segment, pick, actual_winner, completed):
    if segment not in ["Official", "Lean", "Watch"] or not pick:
        return "No Signal"
    if not completed or actual_winner is None:
        return "Pending"
    if actual_winner == "Tie":
        return "Push"
    return "Correct" if pick == actual_winner else "Missed"


def grade_scoring(segment, pick, actual_total, baseline, completed):
    if segment not in ["Official", "Lean", "Watch"] or not pick:
        return "No Signal"
    if not completed or actual_total is None:
        return "Pending"
    if pick == "High Scoring Environment":
        return "Correct" if actual_total > baseline else "Missed"
    if pick == "Low Scoring Environment":
        return "Correct" if actual_total < baseline else "Missed"
    return "No Signal"


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


def build_current_slate(season=None, week=None, today=None, games=None):
    config = ModelConfig()
    games = games if games is not None else load_nfl_schedule()

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
        predicted_winner = home if model_margin > 0 else away
        side_edge = (
            f"{predicted_winner} Edge"
            if confidence != "Pass"
            else "Pass"
        )
        side_release = side_release_values(
            side_edge,
            model_margin,
            predicted_winner,
            config,
        )
        scoring_release = scoring_release_values(
            scoring_edge,
            projected_total,
            league_total,
            config,
        )

        away_score = int(game["away_score"]) if completed else None
        home_score = int(game["home_score"]) if completed else None
        actual_winner = None
        actual_total = None
        if completed:
            if home_score == away_score:
                actual_winner = "Tie"
            else:
                actual_winner = home if home_score > away_score else away
            actual_total = away_score + home_score
        side_result = grade_side(
            side_release["segment"],
            side_release["pick"],
            actual_winner,
            completed,
        )
        scoring_result = grade_scoring(
            scoring_release["segment"],
            scoring_release["pick"],
            actual_total,
            league_total,
            completed,
        )

        if int(game["season"]) == int(season) and int(game["week"]) == int(week):
            scheduled_kickoff = parse_schedule_kickoff(game)

            rows.append(
                {
                    "Sport": "NFL",
                    "Game ID": game.get("game_id"),
                    "Season": int(game["season"]),
                    "Week": int(game["week"]),
                    "Slate Date": str(game.get("gameday")),
                    "Scheduled Kickoff": (
                        scheduled_kickoff.isoformat()
                        if scheduled_kickoff is not None
                        else None
                    ),
                    "Game Time": format_schedule_time(game),
                    "Sort Date": scheduled_kickoff,
                    "Game": f"{away} @ {home}",
                    "Away": away,
                    "Home": home,
                    "Away Score": away_score,
                    "Home Score": home_score,
                    "Actual Winner": actual_winner,
                    "Actual Total": actual_total,
                    "Predicted Winner": predicted_winner,
                    "Model Signal": model_signal_display(side_edge, scoring_edge),
                    "Edge Score": edge_score,
                    "Confidence": confidence,
                    "Side Edge": side_edge,
                    "Side Tracking Segment": side_release["segment"],
                    "Side Discovery Pick": side_release["pick"],
                    "Side Discovery Label": side_release["label"],
                    "Side Result": side_result,
                    "Scoring Edge": scoring_edge,
                    "Scoring Tracking Segment": scoring_release["segment"],
                    "Scoring Discovery Pick": scoring_release["pick"],
                    "Scoring Discovery Label": scoring_release["label"],
                    "Scoring Result": scoring_result,
                    "Early Edge": "Model Pending",
                    "Model Margin": round(model_margin, 2),
                    "Projected Total": round(projected_total, 2),
                    "League Total Baseline": round(league_total, 2),
                    "Rest Edge": rest_edge,
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
