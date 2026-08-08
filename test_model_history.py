import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model_history import (
    full_game_discovery,
    init_db,
    load_performance_summary,
    reconcile_mlb_history,
)


class ModelHistoryReconciliationTests(unittest.TestCase):
    def test_full_game_discovery_requires_a_directional_team(self):
        row = {
            "Full Game Pick": "No Edge",
            "Full Game Score": 6.7,
            "Starter Edge Winner": "Even",
            "Offensive Edge Winner": "Pass",
            "Bullpen Edge Winner": "No Edge",
        }

        self.assertIsNone(full_game_discovery(row, "Away Team", "Home Team"))

    def test_reconciliation_preserves_locked_model_selection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            connection = sqlite3.connect(db_path)
            connection.row_factory = sqlite3.Row
            init_db(connection)
            connection.execute(
                """
                INSERT INTO model_history (
                    model_version, slate_date, game, market, pick, confidence,
                    score, result, outcome, status, created_at, updated_at,
                    locked_at, snapshot_status, tracking_segment, base_market
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2.3.29", "2026-08-01", "Away Team @ Home Team",
                    "Full Game", "Away Team", "C", 8.4, "Pending", "Pending",
                    "In Progress", "created", "updated", "locked", "Locked",
                    "Official", "Full Game",
                ),
            )
            connection.commit()
            snapshot = dict(connection.execute("SELECT * FROM model_history").fetchone())
            connection.close()

            result_games = [
                {
                    "slate_date": "2026-08-01",
                    "game": "Away Team @ Home Team",
                    "status": "Final",
                    "is_final": True,
                    "first_inning_result": "NRFI",
                    "f5_result": "After 5: Away Team 2, Home Team 1",
                    "full_game_result": "Final: Away Team 4, Home Team 2",
                }
            ]
            with patch("model_history.history_backend", return_value="sqlite"):
                counts, _ = reconcile_mlb_history(
                    result_games,
                    [snapshot],
                    apply=True,
                    db_path=db_path,
                    now="reconciled",
                )

            connection = sqlite3.connect(db_path)
            connection.row_factory = sqlite3.Row
            stored = dict(connection.execute("SELECT * FROM model_history").fetchone())
            connection.close()

            self.assertEqual(counts["updated"], 1)
            self.assertEqual(stored["pick"], "Away Team")
            self.assertEqual(stored["confidence"], "C")
            self.assertEqual(stored["score"], 8.4)
            self.assertEqual(stored["model_version"], "2.3.29")
            self.assertEqual(stored["result"], "Final: Away Team 4, Home Team 2")
            self.assertEqual(stored["outcome"], "Hit")
            self.assertEqual(stored["updated_at"], "reconciled")
            self.assertEqual(stored["locked_at"], "locked")

    def test_legacy_even_discovery_is_excluded_from_performance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "history.sqlite3"
            connection = sqlite3.connect(db_path)
            connection.row_factory = sqlite3.Row
            init_db(connection)
            connection.execute(
                """
                INSERT INTO model_history (
                    model_version, slate_date, game, market, pick, confidence,
                    score, result, outcome, status, created_at, updated_at,
                    locked_at, snapshot_status, tracking_segment, base_market
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2.3.29", "2026-08-01", "Away Team @ Home Team",
                    "Full Game Lean", "Even", "Lean", 6.7,
                    "Final: Away Team 4, Home Team 2", "Miss", "Final",
                    "created", "updated", "locked", "Locked", "Lean",
                    "Full Game",
                ),
            )
            connection.commit()
            connection.close()

            with patch("model_history.history_backend", return_value="sqlite"):
                summary = load_performance_summary(
                    model_version="2.3.29",
                    tracking_segment="Lean",
                    db_path=db_path,
                )

            self.assertEqual(summary, [])


if __name__ == "__main__":
    unittest.main()
