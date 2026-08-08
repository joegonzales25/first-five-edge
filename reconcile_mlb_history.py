import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from mlb_agent import (
    build_f5_result,
    build_first_inning_result,
    build_full_game_result,
)
from model_history import load_pending_mlb_history, reconcile_mlb_history


DEFAULT_TIMEZONE = "America/New_York"
DEFAULT_LOOKBACK_DAYS = 30


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Settle existing MLB history from final MLB results without "
            "recomputing or replacing stored model selections."
        )
    )
    parser.add_argument("--date", help="Reconcile one slate date in YYYY-MM-DD format.")
    parser.add_argument(
        "--through-date",
        help="End of the reconciliation window in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help=f"Pending-history window. Defaults to {DEFAULT_LOOKBACK_DAYS} days.",
    )
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
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


def load_mlb_results(start_date, end_date):
    response = requests.get(
        "https://statsapi.mlb.com/api/v1/schedule",
        params={
            "sportId": 1,
            "startDate": str(start_date),
            "endDate": str(end_date),
            "hydrate": "linescore",
        },
        timeout=30,
    )
    response.raise_for_status()

    results = []
    for day in response.json().get("dates", []):
        slate_date = day.get("date")
        for game in day.get("games", []):
            away_team = game["teams"]["away"]["team"]["name"]
            home_team = game["teams"]["home"]["team"]["name"]
            status_data = game.get("status") or {}
            status = status_data.get("detailedState") or ""
            linescore = game.get("linescore") or {}
            results.append(
                {
                    "slate_date": slate_date,
                    "game": f"{away_team} @ {home_team}",
                    "game_id": game.get("gamePk"),
                    "status": status,
                    "is_final": status_data.get("abstractGameState") == "Final",
                    "first_inning_result": build_first_inning_result(linescore, status),
                    "f5_result": build_f5_result(
                        linescore, status, away_team, home_team
                    ),
                    "full_game_result": build_full_game_result(
                        linescore, status, away_team, home_team
                    ),
                }
            )
    return results


def main():
    args = parse_args()
    through_date, lookback_days = date_window(args)
    start_date = through_date - timedelta(days=lookback_days)
    snapshots = load_pending_mlb_history(
        through_date=through_date,
        lookback_days=lookback_days,
    )
    mode = "APPLY" if args.apply else "DRY RUN"
    print(
        f"MLB reconciliation {mode}: {len(snapshots)} candidate rows "
        f"from {start_date} through {through_date}."
    )
    if not snapshots:
        return 0

    try:
        results = load_mlb_results(start_date, through_date)
    except Exception as exc:
        print(f"MLB result fetch failed: {exc}")
        return 1

    counts, details = reconcile_mlb_history(
        results,
        snapshots,
        apply=args.apply,
    )
    print(f"MLB reconciliation totals: {counts}.")
    for detail in details:
        if detail["status"] == "Ambiguous":
            print(
                f"Ambiguous result skipped: {detail['slate_date']} "
                f"{detail['game']} {detail['market']}"
            )
    if not args.apply:
        print("Dry run only. Re-run with --apply to write result updates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
