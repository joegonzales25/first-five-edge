import unittest

import pandas as pd

from mls_model_history import (
    db_value,
    insert_prediction,
    prediction_values,
    safe_float,
)


class RecordingConnection:
    def __init__(self):
        self.params = None

    def execute(self, _query, params):
        self.params = params


class MlsModelHistoryTests(unittest.TestCase):
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
                    "League Total Baseline": 2.75,
                    "Draw Risk": float("inf"),
                    "Rest Edge": 0.5,
                }
            ),
            "2026-07-24",
            "market-v0",
            "model-v0",
            "2026-07-24T12:00:00+00:00",
        )

        self.assertIsNone(values["edge_score"])
        self.assertIsNone(values["model_margin"])
        self.assertIsNone(values["projected_total"])
        self.assertEqual(values["league_total_baseline"], 2.75)
        self.assertIsNone(values["draw_risk"])
        self.assertEqual(values["rest_edge"], 0.5)


if __name__ == "__main__":
    unittest.main()
