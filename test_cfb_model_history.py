import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from cfb_model_history import (
    MARKETS,
    connect,
    init_db,
    insert_prediction,
    load_pending_cfb_snapshots,
    prediction_values,
    reconcile_cfb_history,
)


def snapshot_values(market, model_version, pick, baseline=52.0):
    config = MARKETS[market]
    row = {
        "Game ID": "401000001",
        "Season": 2026,
        "Week": 1,
        "Game": "Alpha @ Beta",
        "Away": "Alpha",
        "Home": "Beta",
        "Scheduled Kickoff": "2026-08-29T20:00:00+00:00",
        "Status": "Scheduled",
        config["pick"]: pick,
        config["segment"]: "Official" if pick != "Pass" else "Pass",
        config["confidence"]: "A" if pick != "Pass" else "Pass",
        config["score"]: 10.0,
        "League Total Baseline": baseline,
    }
    values = prediction_values(
        row,
        market,
        config,
        "2026-08-29",
        "0.1.0-test",
        model_version,
        "2026-08-29T12:00:00+00:00",
    )
    values.update({"result": "No Signal" if pick == "Pass" else "Pending"})
    return values


class CfbModelHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "cfb.sqlite3"
        self.environment = patch.dict("os.environ", {"HISTORY_BACKEND": "sqlite"})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def insert(self, *values):
        connection = connect(self.db_path)
        try:
            init_db(connection)
            for row in values:
                insert_prediction(connection, row)
            connection.commit()
        finally:
            connection.close()

    def test_reconciles_every_stored_version_without_changing_picks(self):
        self.insert(
            snapshot_values("Full Game", "0.1.0-test", "Alpha"),
            snapshot_values("Full Game", "0.2.0-test", "Beta"),
        )
        snapshots = load_pending_cfb_snapshots(
            through_date=pd.Timestamp("2026-08-29").date(),
            lookback_days=0,
            db_path=self.db_path,
        )
        results = pd.DataFrame(
            [{
                "game_id": "401000001",
                "completed": True,
                "status": "Final",
                "away_score": 31,
                "home_score": 20,
                "away_first_half": 17,
                "home_first_half": 10,
            }]
        )

        counts, _ = reconcile_cfb_history(
            results,
            snapshots,
            apply=True,
            db_path=self.db_path,
            now="2026-08-30T01:00:00+00:00",
        )

        connection = connect(self.db_path)
        try:
            rows = [dict(row) for row in connection.execute(
                "SELECT model_version, pick, result, snapshot_status "
                "FROM cfb_model_history ORDER BY model_version"
            ).fetchall()]
        finally:
            connection.close()
        self.assertEqual(counts["updated"], 2)
        self.assertEqual(
            [(row["model_version"], row["pick"], row["result"]) for row in rows],
            [
                ("0.1.0-test", "Alpha", "Correct"),
                ("0.2.0-test", "Beta", "Missed"),
            ],
        )
        self.assertTrue(all(row["snapshot_status"] == "Locked" for row in rows))

    def test_grades_stored_market_rules(self):
        self.insert(
            snapshot_values("Scoring Environment", "0.2.0-test", "High Scoring Environment", 50),
            snapshot_values("First Half", "0.2.0-test", "Alpha"),
        )
        snapshots = load_pending_cfb_snapshots(
            through_date=pd.Timestamp("2026-08-29").date(),
            lookback_days=0,
            db_path=self.db_path,
        )
        results = pd.DataFrame(
            [{
                "game_id": "401000001",
                "completed": True,
                "status": "Final",
                "away_score": 31,
                "home_score": 24,
                "away_first_half": 14,
                "home_first_half": 14,
            }]
        )
        reconcile_cfb_history(results, snapshots, True, self.db_path)

        connection = connect(self.db_path)
        try:
            rows = dict(connection.execute(
                "SELECT market, result FROM cfb_model_history"
            ).fetchall())
        finally:
            connection.close()
        self.assertEqual(rows["Scoring Environment"], "Correct")
        self.assertEqual(rows["First Half"], "Push")

    def test_does_not_insert_a_missing_post_kickoff_snapshot(self):
        results = pd.DataFrame(
            [{
                "game_id": "missing-game",
                "completed": True,
                "status": "Final",
                "away_score": 21,
                "home_score": 17,
            }]
        )
        counts, _ = reconcile_cfb_history(
            results,
            [],
            apply=True,
            db_path=self.db_path,
        )

        connection = connect(self.db_path)
        try:
            init_db(connection)
            row_count = connection.execute(
                "SELECT COUNT(*) FROM cfb_model_history"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(counts["updated"], 0)
        self.assertEqual(row_count, 0)


if __name__ == "__main__":
    unittest.main()
