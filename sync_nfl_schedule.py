import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from nfl_agent import load_nfl_schedule
from nfl_schedule_store import sync_nfl_schedule


DEFAULT_TIMEZONE = "America/New_York"


def default_season():
    today = datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).date()
    return today.year if today.month >= 3 else today.year - 1


def parse_args():
    parser = argparse.ArgumentParser(
        description="Synchronize a full NFL regular-season schedule into history storage."
    )
    parser.add_argument(
        "--season",
        type=int,
        default=default_season(),
        help="NFL season year. Defaults to the active schedule year.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    games = load_nfl_schedule()
    counts = sync_nfl_schedule(games, season=args.season)
    total = counts["inserted"] + counts["updated"]
    print(
        f"NFL {args.season} schedule sync: {total} games "
        f"({counts['inserted']} inserted, {counts['updated']} updated, "
        f"{counts['skipped']} skipped)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
