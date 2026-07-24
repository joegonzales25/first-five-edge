import unittest

import pandas as pd

from season_model_validation import (
    confidence_order_status,
    side_baseline_accuracy,
    validate_input_games,
)


class SeasonModelValidationTests(unittest.TestCase):
    def test_input_diagnostics_find_duplicate_games(self):
        games = pd.DataFrame(
            [
                {
                    "game_id": "1",
                    "season": 2025,
                    "game_date": "2025-10-01",
                    "away_team": "Away",
                    "home_team": "Home",
                    "away_score": 90,
                    "home_score": 100,
                },
                {
                    "game_id": "1",
                    "season": 2025,
                    "game_date": "2025-10-01",
                    "away_team": "Away",
                    "home_team": "Home",
                    "away_score": 90,
                    "home_score": 100,
                },
            ]
        )

        _, diagnostics = validate_input_games(games)

        self.assertEqual(diagnostics["duplicate_game_rows"], 2)
        self.assertEqual(diagnostics["required_null_rows"], 0)

    def test_home_baseline_uses_same_signal_rows(self):
        results = pd.DataFrame(
            [
                {"Actual Winner": "Home A", "Home": "Home A"},
                {"Actual Winner": "Away B", "Home": "Home B"},
                {"Actual Winner": "Home C", "Home": "Home C"},
            ]
        )

        self.assertEqual(side_baseline_accuracy(results), 0.6667)

    def test_confidence_order_requires_enough_rows(self):
        table = pd.DataFrame(
            [
                {"confidence": "A", "signals": 10, "accuracy": 0.8},
                {"confidence": "B", "signals": 10, "accuracy": 0.7},
                {"confidence": "C", "signals": 10, "accuracy": 0.6},
            ]
        )

        self.assertEqual(confidence_order_status(table), "insufficient_data")

    def test_confidence_order_flags_inversion(self):
        table = pd.DataFrame(
            [
                {"confidence": "A", "signals": 25, "accuracy": 0.6},
                {"confidence": "B", "signals": 25, "accuracy": 0.7},
                {"confidence": "C", "signals": 25, "accuracy": 0.5},
            ]
        )

        self.assertEqual(confidence_order_status(table), "review")


if __name__ == "__main__":
    unittest.main()
