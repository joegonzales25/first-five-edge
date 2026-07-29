import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from wnba_data import load_wnba_current_season
from wnba_model_history import (
    load_pending_wnba_snapshots,
    reconcile_wnba_history,
)


DEFAULT_TIMEZONE = "America/New_York"
DEFAULT_LOOKBACK_DAYS = 30


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Settle existing WNBA snapshots from final ESPN results without "
            "recomputing or inserting historical picks."
        )
    )
    parser.add_argument(
        "--date",
        help="Reconcile one slate date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--through-date",
        help=(
            "End of the reconciliation window in YYYY-MM-DD format. "
            "Defaults to today in the selected timezone."
        ),
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help=f"Pending-history window. Defaults to {DEFAULT_LOOKBACK_DAYS} days.",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help=f"Date-selection timezone. Defaults to {DEFAULT_TIMEZONE}.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write reconciled results. Without this flag the command is a dry run.",
    )
    return parser.parse_args()


def date_window(args):
    if args.date:
        target = datetime.strptime(args.date, "%Y-%m-%d").date()
        return target, 0

    through_date = (
        datetime.strptime(args.through_date, "%Y-%m-%d").date()
        if args.through_date
        else datetime.now(ZoneInfo(args.timezone)).date()
    )
    return through_date, max(0, args.lookback_days)


def group_snapshots_by_date(snapshots):
    grouped = defaultdict(list)
    for snapshot in snapshots:
        grouped[str(snapshot["slate_date"])].append(snapshot)
    return grouped


def result_slate(games):
    rows = []
    for _, game in games.iterrows():
        away_score = game.get("away_score")
        home_score = game.get("home_score")
        completed = bool(game.get("completed"))
        actual_winner = None
        actual_total = None
        if completed and pd.notna(away_score) and pd.notna(home_score):
            away_score = int(away_score)
            home_score = int(home_score)
            if home_score > away_score:
                actual_winner = game.get("home_team")
            elif away_score > home_score:
                actual_winner = game.get("away_team")
            actual_total = away_score + home_score

        rows.append(
            {
                "Game ID": game.get("game_id"),
                "Status": "Final" if completed else game.get("status"),
                "Away Score": away_score,
                "Home Score": home_score,
                "Actual Winner": actual_winner,
                "Actual Total": actual_total,
            }
        )
    return pd.DataFrame(rows)


def main():
    args = parse_args()
    through_date, lookback_days = date_window(args)
    snapshots = load_pending_wnba_snapshots(
        through_date=through_date,
        lookback_days=lookback_days,
    )
    mode = "APPLY" if args.apply else "DRY RUN"
    start_date = through_date - timedelta(days=lookback_days)
    print(
        f"WNBA reconciliation {mode}: {len(snapshots)} pending snapshots "
        f"from {start_date} through {through_date}."
    )

    totals = {
        "candidates": 0,
        "matched": 0,
        "final": 0,
        "still_pending": 0,
        "unmatched": 0,
        "updated": 0,
        "fetch_errors": 0,
    }
    if not snapshots:
        print(f"WNBA reconciliation totals: {totals}.")
        return 0

    try:
        games = load_wnba_current_season(
            season=through_date.year,
            today=through_date,
            days_ahead=0,
        )
        results = result_slate(games)
    except Exception as exc:
        totals["fetch_errors"] = 1
        print(f"WNBA result fetch failed: {exc}")
        print(f"WNBA reconciliation totals: {totals}.")
        return 1

    for slate_date, date_snapshots in group_snapshots_by_date(snapshots).items():
        versions = sorted(
            {
                (
                    snapshot.get("market_version"),
                    snapshot.get("model_version"),
                )
                for snapshot in date_snapshots
            }
        )
        print(
            f"{slate_date}: {len(date_snapshots)} candidates across "
            f"{len(versions)} stored release pair(s): {versions}."
        )
        counts, details = reconcile_wnba_history(
            results,
            date_snapshots,
            apply=args.apply,
        )
        for key in counts:
            totals[key] += counts[key]
        print(f"{slate_date}: {counts}.")
        for detail in details:
            if detail["status"] in ["Unmatched", "Still pending"]:
                print(
                    f"  {detail['status']}: {detail['game_id']} "
                    f"{detail.get('game') or ''}"
                )

    print(f"WNBA reconciliation totals: {totals}.")
    if not args.apply:
        print("Dry run only. Re-run with --apply to write these result updates.")
    return 1 if totals["fetch_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
