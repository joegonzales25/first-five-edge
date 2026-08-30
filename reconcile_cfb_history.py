import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from cfb_data import fetch_espn_scoreboard, normalize_espn_games
from cfb_model_history import (
    load_pending_cfb_snapshots,
    reconcile_cfb_history,
)


DEFAULT_TIMEZONE = "America/New_York"
DEFAULT_LOOKBACK_DAYS = 14


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Settle existing CFB snapshots from ESPN results without "
            "recomputing or inserting historical picks."
        )
    )
    parser.add_argument("--date", help="Reconcile one slate date in YYYY-MM-DD format.")
    parser.add_argument("--through-date", help="End date in YYYY-MM-DD format.")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def date_window(args):
    if args.date:
        return datetime.strptime(args.date, "%Y-%m-%d").date(), 0
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


def fetch_results(target_date):
    payload = fetch_espn_scoreboard(target_date)
    return normalize_espn_games(payload.get("events", []), fbs_teams=None)


def main():
    args = parse_args()
    through_date, lookback_days = date_window(args)
    snapshots = load_pending_cfb_snapshots(
        through_date=through_date,
        lookback_days=lookback_days,
    )
    mode = "APPLY" if args.apply else "DRY RUN"
    start_date = through_date - timedelta(days=lookback_days)
    print(
        f"CFB reconciliation {mode}: {len(snapshots)} pending snapshots "
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
    for slate_date, date_snapshots in group_snapshots_by_date(snapshots).items():
        versions = sorted(
            {
                (row.get("market_version"), row.get("model_version"))
                for row in date_snapshots
            }
        )
        print(
            f"{slate_date}: {len(date_snapshots)} candidates across "
            f"{len(versions)} stored release pair(s): {versions}."
        )
        try:
            results = fetch_results(datetime.strptime(slate_date, "%Y-%m-%d").date())
        except Exception as exc:
            totals["fetch_errors"] += 1
            print(f"{slate_date}: ESPN result fetch failed: {exc}")
            continue
        counts, details = reconcile_cfb_history(
            results,
            date_snapshots,
            apply=args.apply,
        )
        for key in counts:
            totals[key] += counts[key]
        print(f"{slate_date}: {counts}.")
        for detail in details:
            if detail["status"] == "Unmatched":
                print(
                    f"  Unmatched: {detail['game_id']} "
                    f"{detail.get('game') or ''}"
                )

    print(f"CFB reconciliation totals: {totals}.")
    if not args.apply:
        print("Dry run only. Re-run with --apply to write these result updates.")
    return 1 if totals["fetch_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
