import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from cbb_agent import build_current_slate
from cbb_model_history import record_cbb_history


DEFAULT_TIMEZONE = "America/New_York"
DEFAULT_MARKET_VERSION = "0.1.0-test"
DEFAULT_MODEL_VERSION = "0.1.0-test"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Record the current CBB slate snapshot for Edge Detector."
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
        "--market-version",
        default=DEFAULT_MARKET_VERSION,
        help=f"CBB market release. Defaults to {DEFAULT_MARKET_VERSION}.",
    )
    parser.add_argument(
        "--model-version",
        default=DEFAULT_MODEL_VERSION,
        help=f"CBB model baseline. Defaults to {DEFAULT_MODEL_VERSION}.",
    )
    return parser.parse_args()


def slate_date_for_args(date_value, timezone_name):
    if date_value:
        return datetime.strptime(date_value, "%Y-%m-%d").date()

    return datetime.now(ZoneInfo(timezone_name)).date()


def main():
    args = parse_args()
    slate_date = slate_date_for_args(args.date, args.timezone)
    slate, _ = build_current_slate(slate_date=slate_date)

    if slate is None or slate.empty:
        print(f"No CBB games found for {slate_date}.")
        return 0

    counts = record_cbb_history(
        slate,
        slate_date,
        args.market_version,
        args.model_version,
    )
    print(
        f"Recorded CBB snapshot for {slate_date}: "
        f"{len(slate)} games, market {args.market_version}, "
        f"model {args.model_version}, counts {counts}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
