import argparse
import json
from pathlib import Path

import pandas as pd


REQUIRED_GAME_COLUMNS = {
    "season",
    "game_date",
    "away_team",
    "home_team",
    "away_score",
    "home_score",
}
CONFIDENCE_ORDER = ["A", "B", "C"]
MIN_HOLDOUT_SIGNALS = 50
MIN_CONFIDENCE_SIGNALS = 20
MIN_SHADOW_DAYS = 28


def as_float(value, digits=4):
    if value is None or pd.isna(value):
        return 0.0
    return round(float(value), digits)


def accuracy(values):
    series = pd.Series(values).dropna()
    if series.empty:
        return 0.0
    return as_float(series.astype(bool).mean())


def validate_input_games(games):
    missing_columns = sorted(REQUIRED_GAME_COLUMNS - set(games.columns))
    if missing_columns:
        raise ValueError(
            f"missing required columns: {', '.join(missing_columns)}"
        )

    checked = games.copy()
    checked["season"] = pd.to_numeric(checked["season"], errors="coerce")
    checked["game_date"] = pd.to_datetime(
        checked["game_date"], errors="coerce"
    )
    for column in ["away_score", "home_score"]:
        checked[column] = pd.to_numeric(checked[column], errors="coerce")

    required_nulls = int(
        checked[
            [
                "season",
                "game_date",
                "away_team",
                "home_team",
                "away_score",
                "home_score",
            ]
        ]
        .isna()
        .any(axis=1)
        .sum()
    )
    if "game_id" in checked.columns:
        duplicate_games = int(
            (
                checked["game_id"].notna()
                & checked["game_id"].duplicated(keep=False)
            ).sum()
        )
    else:
        duplicate_games = int(
            checked.duplicated(
                ["season", "game_date", "away_team", "home_team"],
                keep=False,
            ).sum()
        )

    valid = checked.dropna(
        subset=[
            "season",
            "game_date",
            "away_team",
            "home_team",
            "away_score",
            "home_score",
        ]
    ).copy()
    valid["season"] = valid["season"].astype(int)
    return valid, {
        "rows": int(len(checked)),
        "usable_rows": int(len(valid)),
        "required_null_rows": required_nulls,
        "duplicate_game_rows": duplicate_games,
        "seasons": sorted(valid["season"].unique().tolist()),
    }


def run_backtests_by_season(market, games):
    if market == "nba":
        from nba_agent import backtest_schedule
    elif market == "nhl":
        from nhl_agent import backtest_schedule
    else:
        raise ValueError(f"unsupported market: {market}")

    results = []
    for season in sorted(games["season"].unique()):
        season_games = games[games["season"] == season].copy()
        season_results, _ = backtest_schedule(
            season_games,
            season=int(season),
        )
        if not season_results.empty:
            results.append(season_results)
    return pd.concat(results, ignore_index=True) if results else pd.DataFrame()


def side_signal_rows(results):
    return results[
        results["Confidence"].isin(CONFIDENCE_ORDER)
        & (results["Side Edge"] != "Pass")
    ].copy()


def scoring_signal_rows(results):
    if "Scoring Edge" not in results.columns:
        return pd.DataFrame()
    return results[
        results["Scoring Edge"]
        != "Neutral Scoring Environment"
    ].copy()


def side_baseline_accuracy(results):
    if results.empty:
        return 0.0
    return accuracy(results["Actual Winner"] == results["Home"])


def scoring_baseline_accuracy(results):
    if results.empty:
        return 0.0
    above = results["Actual Total"] > results["League Total Baseline"]
    return as_float(max(above.mean(), (~above).mean()))


def confidence_metrics(results):
    rows = []
    for confidence in CONFIDENCE_ORDER:
        group = side_signal_rows(results)
        group = group[group["Confidence"] == confidence]
        rows.append(
            {
                "confidence": confidence,
                "signals": int(len(group)),
                "accuracy": accuracy(
                    group["Predicted Winner"] == group["Actual Winner"]
                ),
                "baseline_accuracy": side_baseline_accuracy(group),
            }
        )
    return pd.DataFrame(rows)


def confidence_order_status(table):
    eligible = table[table["signals"] >= MIN_CONFIDENCE_SIGNALS]
    if len(eligible) < 2:
        return "insufficient_data"
    accuracies = eligible.set_index("confidence")["accuracy"]
    ordered = [
        accuracies[confidence]
        for confidence in CONFIDENCE_ORDER
        if confidence in accuracies
    ]
    return "pass" if ordered == sorted(ordered, reverse=True) else "review"


def season_metrics(results):
    rows = []
    for season, group in results.groupby("Season"):
        sides = side_signal_rows(group)
        scoring = scoring_signal_rows(group)
        rows.append(
            {
                "season": int(season),
                "games": int(len(group)),
                "side_signals": int(len(sides)),
                "side_accuracy": accuracy(
                    sides["Predicted Winner"] == sides["Actual Winner"]
                ),
                "side_baseline_accuracy": side_baseline_accuracy(sides),
                "scoring_signals": int(len(scoring)),
                "scoring_accuracy": accuracy(scoring["Scoring Correct"])
                if not scoring.empty
                else 0.0,
                "scoring_baseline_accuracy": scoring_baseline_accuracy(scoring),
                "margin_mae": as_float(group["Margin Error"].mean(), 2),
                "total_mae": as_float(group["Total Error"].mean(), 2),
            }
        )
    return pd.DataFrame(rows)


def historical_report(market, games, holdout_season=None):
    valid_games, input_diagnostics = validate_input_games(games)
    results = run_backtests_by_season(market, valid_games)
    if results.empty:
        raise ValueError("backtest produced no graded games")

    seasons = sorted(int(value) for value in results["Season"].unique())
    holdout_season = int(holdout_season or seasons[-1])
    holdout = results[results["Season"] == holdout_season].copy()
    if holdout.empty:
        raise ValueError(
            f"holdout season {holdout_season} produced no graded games"
        )

    holdout_sides = side_signal_rows(holdout)
    holdout_scoring = scoring_signal_rows(holdout)
    side_accuracy = accuracy(
        holdout_sides["Predicted Winner"]
        == holdout_sides["Actual Winner"]
    )
    side_baseline = side_baseline_accuracy(holdout_sides)
    scoring_accuracy = (
        accuracy(holdout_scoring["Scoring Correct"])
        if not holdout_scoring.empty
        else 0.0
    )
    scoring_baseline = scoring_baseline_accuracy(holdout_scoring)
    confidence = confidence_metrics(holdout)
    confidence_status = confidence_order_status(confidence)

    gates = {
        "input_complete": (
            input_diagnostics["required_null_rows"] == 0
            and input_diagnostics["duplicate_game_rows"] == 0
        ),
        "two_or_more_seasons": len(seasons) >= 2,
        "holdout_side_sample": len(holdout_sides)
        >= MIN_HOLDOUT_SIGNALS,
        "side_beats_home_baseline": side_accuracy > side_baseline,
        "confidence_order_ready": confidence_status == "pass",
    }
    if market == "nba":
        gates.update(
            {
                "holdout_scoring_sample": len(holdout_scoring)
                >= MIN_HOLDOUT_SIGNALS,
                "scoring_beats_majority_baseline": scoring_accuracy
                > scoring_baseline,
            }
        )

    boolean_gates = [
        value for value in gates.values() if isinstance(value, bool)
    ]
    report = {
        "market": market.upper(),
        "validation_type": "historical_holdout",
        "holdout_season": holdout_season,
        "input": input_diagnostics,
        "holdout": {
            "games": int(len(holdout)),
            "side_signals": int(len(holdout_sides)),
            "side_accuracy": side_accuracy,
            "side_home_baseline_accuracy": side_baseline,
            "scoring_signals": int(len(holdout_scoring)),
            "scoring_accuracy": scoring_accuracy,
            "scoring_majority_baseline_accuracy": scoring_baseline,
            "margin_mae": as_float(holdout["Margin Error"].mean(), 2),
            "total_mae": as_float(holdout["Total Error"].mean(), 2),
        },
        "gates": gates,
        "confidence_order_status": confidence_status,
        "historical_gate_pass": all(boolean_gates),
        "release_decision": "owner_review_required",
        "limitations": [
            "Historical injury/availability is not reconstructed."
            if market == "nba"
            else "Historical confirmed-goalie context is not reconstructed.",
            "Passing this report does not enable scheduling or promote the model.",
        ],
    }
    return report, season_metrics(results), confidence, results


def normalized_status(row):
    return str(row.get("status") or "").strip().lower()


def is_completed_history_row(row):
    return normalized_status(row) in {"final", "game over", "completed"}


def is_official_history_row(row):
    return (
        str(row.get("confidence") or "") in CONFIDENCE_ORDER
        and str(row.get("side_edge") or "") not in {"", "Pass"}
    )


def shadow_report(market, model_version=None, market_version=None):
    if market == "nba":
        from nba_model_history import load_nba_history

        rows = load_nba_history(model_version, market_version)
    elif market == "nhl":
        from nhl_model_history import load_nhl_history

        rows = load_nhl_history(model_version, market_version)
    else:
        raise ValueError(f"unsupported market: {market}")

    completed = [row for row in rows if is_completed_history_row(row)]
    official = [row for row in rows if is_official_history_row(row)]
    graded_official = [
        row
        for row in official
        if row.get("side_result") in {"Correct", "Missed"}
    ]
    final_missing_grade = [
        row
        for row in completed
        if is_official_history_row(row)
        and row.get("side_result") not in {"Correct", "Missed"}
    ]
    final_missing_scores = [
        row
        for row in completed
        if row.get("away_score") is None or row.get("home_score") is None
    ]
    locked_missing_timestamp = [
        row
        for row in rows
        if str(row.get("snapshot_status") or "").lower() == "locked"
        and not row.get("locked_at")
    ]
    completed_unlocked = [
        row
        for row in completed
        if str(row.get("snapshot_status") or "").lower() != "locked"
    ]
    dates = sorted(
        {
            pd.Timestamp(row["slate_date"]).date()
            for row in rows
            if row.get("slate_date")
        }
    )
    tracked_days = (dates[-1] - dates[0]).days + 1 if dates else 0
    gates = {
        "four_week_window": tracked_days >= MIN_SHADOW_DAYS,
        "fifty_graded_official": len(graded_official)
        >= MIN_HOLDOUT_SIGNALS,
        "all_completed_official_graded": len(final_missing_grade) == 0,
        "all_completed_have_scores": len(final_missing_scores) == 0,
        "locked_rows_have_timestamp": len(locked_missing_timestamp) == 0,
        "completed_rows_are_locked": len(completed_unlocked) == 0,
    }
    return {
        "market": market.upper(),
        "validation_type": "live_shadow_history",
        "model_version": model_version,
        "market_version": market_version,
        "snapshots": len(rows),
        "completed": len(completed),
        "official": len(official),
        "graded_official": len(graded_official),
        "tracked_days": tracked_days,
        "exceptions": {
            "completed_official_missing_grade": len(final_missing_grade),
            "completed_missing_scores": len(final_missing_scores),
            "locked_missing_timestamp": len(locked_missing_timestamp),
            "completed_unlocked": len(completed_unlocked),
        },
        "gates": gates,
        "shadow_gate_pass": all(gates.values()),
        "release_decision": "owner_review_required",
    }


def write_historical_outputs(output_dir, market, report, by_season, confidence, results):
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = output_dir / f"{market}_historical_validation"
    prefix.with_suffix(".json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    by_season.to_csv(f"{prefix}_by_season.csv", index=False)
    confidence.to_csv(f"{prefix}_by_confidence.csv", index=False)
    results.to_csv(f"{prefix}_graded_rows.csv", index=False)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate NBA or NHL historical and live-shadow model evidence."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    historical = subparsers.add_parser(
        "historical",
        help="Run a chronological, season-isolated historical holdout report.",
    )
    historical.add_argument("--market", choices=["nba", "nhl"], required=True)
    historical.add_argument("--input", required=True, help="Normalized completed-game CSV.")
    historical.add_argument("--holdout-season", type=int)
    historical.add_argument("--output-dir", default="validation_reports")

    shadow = subparsers.add_parser(
        "shadow",
        help="Audit stored live-shadow history and reconciliation gates.",
    )
    shadow.add_argument("--market", choices=["nba", "nhl"], required=True)
    shadow.add_argument("--model-version")
    shadow.add_argument("--market-version")
    shadow.add_argument("--output")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.command == "historical":
        games = pd.read_csv(args.input)
        report, by_season, confidence, results = historical_report(
            args.market,
            games,
            args.holdout_season,
        )
        write_historical_outputs(
            Path(args.output_dir),
            args.market,
            report,
            by_season,
            confidence,
            results,
        )
    else:
        report = shadow_report(
            args.market,
            args.model_version,
            args.market_version,
        )
        if args.output:
            Path(args.output).write_text(
                json.dumps(report, indent=2),
                encoding="utf-8",
            )

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
