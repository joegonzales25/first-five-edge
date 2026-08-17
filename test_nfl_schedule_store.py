import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from nfl_schedule_store import (
    load_latest_nfl_features,
    load_nfl_schedule_inventory,
    record_nfl_pregame_features,
    sync_nfl_schedule,
)


class NflScheduleStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "nfl.sqlite3"
        self.backend = patch.dict(
            "os.environ",
            {
                "HISTORY_BACKEND": "sqlite",
                "ALLOW_SQLITE_HISTORY_FALLBACK": "true",
            },
        )
        self.backend.start()

    def tearDown(self):
        self.backend.stop()
        self.temp_dir.cleanup()

    def schedule_frame(self):
        return pd.DataFrame(
            [
                {
                    "game_id": "2026_01_AWY_HME",
                    "season": 2026,
                    "week": 1,
                    "game_type": "REG",
                    "gameday": pd.Timestamp("2026-09-10"),
                    "gametime": "20:20",
                    "weekday": "Thursday",
                    "away_team": "AWY",
                    "home_team": "HME",
                    "location": "Home",
                    "stadium": "Example Stadium",
                    "roof": "outdoors",
                    "surface": "grass",
                    "away_rest": 7,
                    "home_rest": 7,
                    "away_score": None,
                    "home_score": None,
                },
                {
                    "game_id": "2025_01_OLD_HME",
                    "season": 2025,
                    "week": 1,
                    "game_type": "REG",
                    "gameday": "2025-09-04",
                    "away_team": "OLD",
                    "home_team": "HME",
                },
            ]
        )

    def test_syncs_requested_regular_season_and_updates_in_place(self):
        now = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)
        counts = sync_nfl_schedule(
            self.schedule_frame(),
            season=2026,
            db_path=self.db_path,
            now=now,
        )

        self.assertEqual(counts["inserted"], 1)
        rows = load_nfl_schedule_inventory(
            season=2026,
            db_path=self.db_path,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "Scheduled")
        self.assertEqual(rows[0]["stadium"], "Example Stadium")
        self.assertEqual(rows[0]["slate_date"], "2026-09-10")
        self.assertEqual(rows[0]["neutral_site"], 0)

        updated = self.schedule_frame().iloc[[0]].copy()
        updated.loc[:, "gametime"] = "20:30"
        updated.loc[:, "away_score"] = 17
        updated.loc[:, "home_score"] = 24
        counts = sync_nfl_schedule(
            updated,
            season=2026,
            db_path=self.db_path,
            now=now,
        )
        rows = load_nfl_schedule_inventory(
            season=2026,
            db_path=self.db_path,
        )

        self.assertEqual(counts["updated"], 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "Final")
        self.assertEqual(rows[0]["game_time"], "20:30")

    def test_records_timestamped_feature_readiness(self):
        partial = pd.DataFrame(
            [{"game_id": "2026_01_AWY_HME", "net_epa_diff": 0.10}]
        )
        complete = pd.DataFrame(
            [
                {
                    "game_id": "2026_01_AWY_HME",
                    "net_epa_diff": 0.12,
                    "early_down_success_diff": 0.03,
                    "qb_epa_diff": 0.08,
                    "sack_rate_diff": 0.01,
                    "explosive_play_diff": 0.02,
                }
            ]
        )

        record_nfl_pregame_features(
            partial,
            as_of="2026-09-08T12:00:00+00:00",
            db_path=self.db_path,
        )
        record_nfl_pregame_features(
            complete,
            as_of="2026-09-09T12:00:00+00:00",
            db_path=self.db_path,
        )
        rows = load_latest_nfl_features(
            ["2026_01_AWY_HME"],
            db_path=self.db_path,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["readiness"], "Model Ready")
        self.assertEqual(rows[0]["core_available"], 5)
        self.assertEqual(rows[0]["as_of"], "2026-09-09T12:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
