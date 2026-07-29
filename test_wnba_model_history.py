import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from wnba_model_history import (
    connect,
    db_value,
    init_db,
    insert_prediction,
    load_wnba_history,
    prediction_values,
    reconcile_wnba_history,
    result_values,
    safe_float,
)


class RecordingConnection:
    def __init__(self):
        self.params = None

    def execute(self, _query, params):
        self.params = params


class WnbaModelHistoryTests(unittest.TestCase):
    def test_safe_float_preserves_finite_values(self):
        self.assertEqual(safe_float("3.25"), 3.25)
        self.assertEqual(safe_float(-1), -1.0)

    def test_safe_float_rejects_non_finite_values(self):
        for value in [float("nan"), float("inf"), float("-inf"), pd.NA]:
            with self.subTest(value=value):
                self.assertIsNone(safe_float(value))

    def test_db_value_rejects_all_missing_and_non_finite_values(self):
        for value in [None, float("nan"), float("inf"), float("-inf"), pd.NA]:
            with self.subTest(value=value):
                self.assertIsNone(db_value(value))

    def test_insert_normalizes_optional_nan_fields(self):
        connection = RecordingConnection()

        insert_prediction(
            connection,
            {
                "game_id": "game-1",
                "model_signal": float("nan"),
                "edge_score": float("inf"),
                "away_prior_games": 4,
            },
        )

        self.assertEqual(connection.params, ["game-1", None, None, 4])

    def test_prediction_values_normalizes_non_finite_numeric_fields(self):
        values = prediction_values(
            pd.Series(
                {
                    "Game ID": "game-1",
                    "Game": "Away @ Home",
                    "Edge Score": float("inf"),
                    "Model Margin": float("-inf"),
                    "Projected Total": float("nan"),
                    "League Total Baseline": 173.5,
                    "Rest Edge": 0.5,
                }
            ),
            "2026-07-29",
            "market-v0",
            "model-v0",
            "2026-07-29T12:00:00+00:00",
        )

        self.assertIsNone(values["edge_score"])
        self.assertIsNone(values["model_margin"])
        self.assertIsNone(values["projected_total"])
        self.assertEqual(values["league_total_baseline"], 173.5)
        self.assertEqual(values["rest_edge"], 0.5)

    def test_result_values_uses_original_snapshot_diagnostics(self):
        values = result_values(
            pd.Series(
                {
                    "Status": "Final",
                    "Away Score": 90,
                    "Home Score": 100,
                    "Actual Winner": "Home",
                    "Actual Total": 190,
                    "Model Margin": 999,
                    "Projected Total": 999,
                }
            ),
            "2026-07-29T12:00:00+00:00",
            {
                "side_edge": "Home Edge",
                "predicted_winner": "Home",
                "scoring_edge": "High Scoring Environment",
                "league_total_baseline": 175,
                "model_margin": 2,
                "projected_total": 170,
            },
        )

        self.assertEqual(values["side_result"], "Correct")
        self.assertEqual(values["scoring_result"], "Correct")
        self.assertEqual(values["margin_error"], 8)
        self.assertEqual(values["total_error"], 20)

    def test_reconciliation_updates_only_existing_versioned_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "wnba.sqlite3"
            snapshot = prediction_values(
                pd.Series(
                    {
                        "Game ID": "game-1",
                        "Season": 2026,
                        "Game": "Away @ Home",
                        "Away": "Away",
                        "Home": "Home",
                        "Status": "Scheduled",
                        "Side Edge": "Home Edge",
                        "Predicted Winner": "Home",
                        "Scoring Edge": "High Scoring Environment",
                        "Model Margin": 4,
                        "Projected Total": 180,
                        "League Total Baseline": 175,
                    }
                ),
                "2026-07-29",
                "market-v1",
                "model-v1",
                "2026-07-29T10:00:00+00:00",
            )
            with patch("wnba_model_history.history_backend", return_value="sqlite"):
                with connect(db_path) as connection:
                    init_db(connection)
                    insert_prediction(connection, snapshot)
                    connection.commit()

                stored = load_wnba_history(db_path=db_path)
                final_slate = pd.DataFrame(
                    [
                        {
                            "Game ID": "game-1",
                            "Status": "Final",
                            "Away Score": 80,
                            "Home Score": 90,
                            "Actual Winner": "Home",
                            "Actual Total": 170,
                            "Model Margin": -100,
                            "Projected Total": 100,
                        },
                        {
                            "Game ID": "game-without-snapshot",
                            "Status": "Final",
                            "Away Score": 70,
                            "Home Score": 75,
                            "Actual Winner": "Home",
                            "Actual Total": 145,
                        },
                    ]
                )

                dry_counts, _ = reconcile_wnba_history(
                    final_slate,
                    stored,
                    apply=False,
                    db_path=db_path,
                    now="2026-07-30T01:00:00+00:00",
                )
                self.assertEqual(dry_counts["final"], 1)
                self.assertEqual(dry_counts["updated"], 0)
                self.assertEqual(load_wnba_history(db_path=db_path)[0]["status"], "Scheduled")

                apply_counts, _ = reconcile_wnba_history(
                    final_slate,
                    stored,
                    apply=True,
                    db_path=db_path,
                    now="2026-07-30T01:00:00+00:00",
                )
                rows = load_wnba_history(db_path=db_path)

            self.assertEqual(apply_counts["updated"], 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["market_version"], "market-v1")
            self.assertEqual(rows[0]["model_version"], "model-v1")
            self.assertEqual(rows[0]["side_result"], "Correct")
            self.assertEqual(rows[0]["scoring_result"], "Missed")
            self.assertEqual(rows[0]["margin_error"], 6)
            self.assertEqual(rows[0]["total_error"], 10)
            self.assertEqual(rows[0]["snapshot_status"], "Locked")


if __name__ == "__main__":
    unittest.main()
