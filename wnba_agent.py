import argparse
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from basketball_model import (
    WNBA_CONFIG,
    TeamState,
    agent_notes,
    backtest_csv,
    backtest_games,
    calculate_edge_score,
    confidence_from_margin,
    rating_for,
    scoring_reasons,
    side_edge_label,
    side_reasons,
    total_edge_label,
    update_team,
)
from nba_agent import key_factors_summary, split_notes
from wnba_data import load_wnba_current_season


def build_historical_lab(games_csv, season=None):
    results, summary = backtest_csv(games_csv, league="WNBA", season=season)
    return prepare_basketball_lab(results), summary


def backtest_schedule(games: pd.DataFrame, season=None):
    results, summary = backtest_games(games, league="WNBA", season=season)
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


def model_signal_display(side_edge, scoring_edge):
    signals = []
    if side_edge != "Pass":
        signals.append(side_edge)
    if scoring_edge != "Neutral Scoring Environment":
        signals.append(scoring_edge)
    return " / ".join(signals) if signals else "Pass"


def status_for_game(game):
    if bool(game.get("completed")):
        return "Final"
    return game.get("status") or "Scheduled"


def side_result_for_game(side_edge, predicted_winner, actual_winner, completed):
    if side_edge == "Pass":
        return "No Signal"
    if not completed or actual_winner is None:
        return "Pending"
    return "Correct" if predicted_winner == actual_winner else "Missed"


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


def completed_games_for_lab(games: pd.DataFrame) -> pd.DataFrame:
    if games.empty:
        return games
    completed = games[
        games["completed"]
        & games["away_score"].notna()
        & games["home_score"].notna()
    ].copy()
    return completed


def build_current_season_lab(season=None, today=None):
    games = load_wnba_current_season(season=season, today=today)
    completed = completed_games_for_lab(games)
    return backtest_schedule(completed, season=season)


def eastern_game_date(raw_value):
    game_dt = pd.to_datetime(raw_value)
    if game_dt.tzinfo is not None:
        game_dt = game_dt.tz_convert(ZoneInfo("America/New_York"))
    return game_dt.date()


def build_current_slate(season=None, today=None, days_ahead=14, slate_date=None):
    config = WNBA_CONFIG
    target_date = slate_date or today or pd.Timestamp.today().date()
    games = load_wnba_current_season(
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
        model_margin = (
            home_rating
            - away_rating
            + config.home_court
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
        side_edge = side_edge_label(
            model_margin,
            away,
            home,
            config,
            away_state.games,
            home_state.games,
        )
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
            config.home_court,
            rest_edge,
            model_margin,
            config,
            away_state.games,
            home_state.games,
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
                    "Sport": "WNBA",
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
                    "Early Edge": "Model Pending",
                    "Side Result": side_result,
                    "Winner Result": side_result,
                    "Scoring Result": scoring_result,
                    "Model Margin": round(model_margin, 2),
                    "Projected Total": round(projected_total, 2),
                    "League Total Baseline": round(league_total, 2),
                    "Away Prior Games": away_state.games,
                    "Home Prior Games": home_state.games,
                    "Rest Edge": round(rest_edge, 2),
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


def no_rest_config():
    from basketball_model import WNBA_CONFIG, BasketballModelConfig

    return BasketballModelConfig(
        league=WNBA_CONFIG.league,
        side_a=WNBA_CONFIG.side_a,
        side_b=WNBA_CONFIG.side_b,
        side_c=WNBA_CONFIG.side_c,
        min_a_games=WNBA_CONFIG.min_a_games,
        min_b_games=WNBA_CONFIG.min_b_games,
        min_c_games=WNBA_CONFIG.min_c_games,
        total_threshold=WNBA_CONFIG.total_threshold,
        home_court=WNBA_CONFIG.home_court,
        rest_weight=0.0,
        recent_margin_weight=WNBA_CONFIG.recent_margin_weight,
        pace_weight=WNBA_CONFIG.pace_weight,
        default_total=WNBA_CONFIG.default_total,
    )


def build_no_rest_lab(games_csv, season=None):
    config = no_rest_config()
    games = pd.read_csv(games_csv)
    results, summary = backtest_games(
        games,
        league="WNBA",
        season=season,
        config=config,
    )
    return prepare_basketball_lab(results), summary


def backtest_no_rest_schedule(games: pd.DataFrame, season=None):
    results, summary = backtest_games(
        games,
        league="WNBA",
        season=season,
        config=no_rest_config(),
    )
    return prepare_basketball_lab(results), summary


def build_report(games_csv, season=None, compare_no_rest=False):
    results, summary = build_historical_lab(games_csv, season)
    report = {
        "results": results,
        "summary": summary,
        "tables": historical_summary_tables(results),
    }

    if compare_no_rest:
        no_rest_results, no_rest_summary = build_no_rest_lab(games_csv, season)
        report["no_rest"] = {
            "results": no_rest_results,
            "summary": no_rest_summary,
            "tables": historical_summary_tables(no_rest_results),
        }

    return report


def accuracy(value):
    if value.empty:
        return 0.0
    return float(round(value.mean(), 4))


def average_error(value):
    if value.empty:
        return 0.0
    return float(round(value.mean(), 2))


def metric_row(label, group):
    side_signals = group[group["Confidence"] != "Pass"]
    scoring_signals = group[
        group["Scoring Edge"] != "Neutral Scoring Environment"
    ]
    return {
        "Segment": label,
        "Games": len(group),
        "Winner Accuracy": accuracy(group["Winner Correct"]),
        "Side Signal Games": len(side_signals),
        "Side Signal Accuracy": accuracy(side_signals["Winner Correct"]),
        "Margin MAE": average_error(group["Margin Error"]),
        "Total MAE": average_error(group["Total Error"]),
        "Scoring Signal Games": len(scoring_signals),
        "Scoring Signal Accuracy": accuracy(scoring_signals["Scoring Correct"]),
    }


def confidence_summary(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()

    order = ["A", "B", "C", "Pass"]
    rows = []
    for confidence in order:
        group = results[results["Confidence"] == confidence]
        if group.empty:
            continue
        rows.append(
            {
                "Confidence": confidence,
                "Games": len(group),
                "Winner Accuracy": accuracy(group["Winner Correct"]),
                "Margin MAE": average_error(group["Margin Error"]),
            }
        )
    return pd.DataFrame(rows)


def scoring_summary(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()

    scoring = results[
        results["Scoring Edge"] != "Neutral Scoring Environment"
    ].copy()
    rows = []
    for edge, group in scoring.groupby("Scoring Edge"):
        rows.append(
            {
                "Scoring Environment": edge,
                "Games": len(group),
                "Accuracy": accuracy(group["Scoring Correct"]),
                "Total MAE": average_error(group["Total Error"]),
            }
        )
    return pd.DataFrame(rows)


def side_location_summary(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()

    signals = results[results["Confidence"] != "Pass"].copy()
    if signals.empty:
        return pd.DataFrame()

    signals["Side Location"] = signals.apply(
        lambda row: "Home Edge"
        if str(row["Side Edge"]).startswith(f"{row['Home']} ")
        else "Road Edge",
        axis=1,
    )
    rows = []
    for label, group in signals.groupby("Side Location"):
        rows.append(metric_row(label, group))
    return pd.DataFrame(rows)


def history_summary(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty or "Min Prior Games" not in results.columns:
        return pd.DataFrame()

    early = results[results["Min Prior Games"] < 5]
    established = results[results["Min Prior Games"] >= 5]
    return pd.DataFrame(
        [
            metric_row("Early Season / Limited History", early),
            metric_row("Both Teams 5+ Prior Games", established),
        ]
    )


def rest_summary(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty or "Rest Edge" not in results.columns:
        return pd.DataFrame()

    rest_games = results[results["Rest Edge"].abs() >= 1]
    neutral_rest = results[results["Rest Edge"].abs() < 1]
    return pd.DataFrame(
        [
            metric_row("Rest Advantage Present", rest_games),
            metric_row("Neutral Rest", neutral_rest),
        ]
    )


def historical_summary_tables(results: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if results.empty:
        return {
            "core": pd.DataFrame(),
            "confidence": pd.DataFrame(),
            "scoring": pd.DataFrame(),
            "side_location": pd.DataFrame(),
            "history": pd.DataFrame(),
            "rest": pd.DataFrame(),
        }

    return {
        "core": pd.DataFrame([metric_row("All Games", results)]),
        "confidence": confidence_summary(results),
        "scoring": scoring_summary(results),
        "side_location": side_location_summary(results),
        "history": history_summary(results),
        "rest": rest_summary(results),
    }


def prepare_basketball_lab(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return results

    prepared = results.copy()
    prepared["Status"] = "Final"
    prepared["Game Time"] = prepared["Game Date"]
    prepared["Early Edge"] = "Model Pending"
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


def print_report(report):
    print("WNBA Test Model Backtest")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))

    for name, table in report["tables"].items():
        print(f"\n{name.replace('_', ' ').title()}")
        if table.empty:
            print("No rows")
        else:
            print(table.to_string(index=False))

    if "no_rest" not in report:
        return

    print("\nWNBA No-Rest Ablation")
    print(json.dumps(report["no_rest"]["summary"], indent=2, sort_keys=True))

    for name, table in report["no_rest"]["tables"].items():
        print(f"\nNo-Rest {name.replace('_', ' ').title()}")
        if table.empty:
            print("No rows")
        else:
            print(table.to_string(index=False))


def write_report(report, output_dir):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    report["results"].to_csv(output_path / "wnba_backtest_results.csv", index=False)
    (output_path / "wnba_backtest_summary.json").write_text(
        json.dumps(report["summary"], indent=2, sort_keys=True),
        encoding="utf-8",
    )

    for name, table in report["tables"].items():
        table.to_csv(output_path / f"wnba_{name}_summary.csv", index=False)

    if "no_rest" not in report:
        return

    report["no_rest"]["results"].to_csv(
        output_path / "wnba_no_rest_backtest_results.csv",
        index=False,
    )
    (output_path / "wnba_no_rest_backtest_summary.json").write_text(
        json.dumps(report["no_rest"]["summary"], indent=2, sort_keys=True),
        encoding="utf-8",
    )

    for name, table in report["no_rest"]["tables"].items():
        table.to_csv(output_path / f"wnba_no_rest_{name}_summary.csv", index=False)


def main():
    parser = argparse.ArgumentParser(
        description="Run the WNBA v1.0 historical model report."
    )
    parser.add_argument("--games-csv", required=True)
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--compare-no-rest", action="store_true")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    report = build_report(
        args.games_csv,
        season=args.season,
        compare_no_rest=args.compare_no_rest,
    )
    print_report(report)

    if args.output_dir:
        write_report(report, args.output_dir)
        print(f"\nsaved: {args.output_dir}")


if __name__ == "__main__":
    main()
