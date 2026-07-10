import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from mlb_agent import get_today_games
from model_history import record_model_history


DEFAULT_MODEL_VERSION = "2.3.29"
DEFAULT_TIMEZONE = "America/New_York"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Record the current MLB slate snapshot for Edge Detector."
    )
    parser.add_argument(
        "--date",
        help="Slate date in YYYY-MM-DD format. Defaults to today in the selected timezone.",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help=f"Timezone for slate selection and display. Defaults to {DEFAULT_TIMEZONE}.",
    )
    parser.add_argument(
        "--model-version",
        default=DEFAULT_MODEL_VERSION,
        help=f"Performance tracking version. Defaults to {DEFAULT_MODEL_VERSION}.",
    )
    return parser.parse_args()


def slate_date_for_args(date_value, timezone_name):
    if date_value:
        return datetime.strptime(date_value, "%Y-%m-%d").date()

    return datetime.now(ZoneInfo(timezone_name)).date()


def main():
    args = parse_args()
    slate_date = slate_date_for_args(args.date, args.timezone)
    games = get_today_games(slate_date.isoformat(), args.timezone)

    if games is None or games.empty:
        print(f"No MLB games found for {slate_date}.")
        return 0

    record_model_history(games, slate_date, args.model_version)
    print(
        f"Recorded MLB snapshot for {slate_date}: "
        f"{len(games)} games, model {args.model_version}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
