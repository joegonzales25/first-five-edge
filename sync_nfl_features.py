import argparse
from pathlib import Path

import pandas as pd

from nfl_schedule_store import FEATURE_VERSION, record_nfl_pregame_features


def parse_args():
    parser = argparse.ArgumentParser(
        description="Store normalized NFL pregame features without creating predictions."
    )
    parser.add_argument("feature_file", type=Path)
    parser.add_argument("--feature-version", default=FEATURE_VERSION)
    parser.add_argument("--source", default="normalized-pregame")
    parser.add_argument(
        "--as-of",
        help="ISO-8601 source timestamp. Defaults to the ingestion time.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    frame = pd.read_csv(args.feature_file)
    if "game_id" not in frame.columns:
        raise ValueError("NFL feature file must contain game_id.")
    counts = record_nfl_pregame_features(
        frame,
        feature_version=args.feature_version,
        source=args.source,
        as_of=args.as_of,
    )
    print(
        f"NFL feature sync: {counts['inserted']} inserted, "
        f"{counts['skipped']} skipped."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
