import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from nfl_challenger import (
    attach_features,
    challenger_row_values,
    load_feature_file,
)
from nfl_model_history import connect, init_db, prediction_values, result_values


class NflChallengerTests(unittest.TestCase):
    def test_incomplete_features_are_not_tracked(self):
        values = challenger_row_values(
            {"Away": "AWY", "Home": "HME", "League Total Baseline": 44},
            {"net_epa_diff": 0.1},
        )

        self.assertEqual(values["Challenger Status"], "Awaiting features")
        self.assertEqual(values["Challenger Model Signal"], "Not Tracked")

    def test_complete_features_create_isolated_challenger_decision(self):
        values = challenger_row_values(
            {"Away": "AWY", "Home": "HME", "League Total Baseline": 44},
            {
                "net_epa_diff": 0.20,
                "early_down_success_diff": 0.06,
                "qb_epa_diff": 0.12,
                "sack_rate_diff": 0.03,
                "explosive_play_diff": 0.04,
                "dvoa_diff": 0.10,
            },
        )

        self.assertEqual(values["Challenger Status"], "Tracked")
        self.assertEqual(values["Challenger Predicted Winner"], "HME")
        self.assertNotEqual(values["Challenger Side Edge"], "Not Tracked")
        self.assertEqual(values["Challenger Features"]["dvoa_diff"], 0.10)

    def test_feature_file_contract_and_attachment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "features.csv"
            pd.DataFrame(
                [
                    {
                        "game_id": "game-1",
                        "net_epa_diff": 0.1,
                        "early_down_success_diff": 0.02,
                        "qb_epa_diff": 0.03,
                        "sack_rate_diff": 0.01,
                        "explosive_play_diff": 0.02,
                    }
                ]
            ).to_csv(path, index=False)

            features = load_feature_file(path)
            games = attach_features(
                pd.DataFrame([{"game_id": "game-1"}]), features
            )

        self.assertEqual(
            games.iloc[0]["challenger_features"]["net_epa_diff"], 0.1
        )

    def test_history_schema_and_grading_keep_tracks_separate(self):
        row = pd.Series(
            {
                "Game ID": "game-1",
                "Slate Date": "2026-09-10",
                "Game": "AWY @ HME",
                "Away": "AWY",
                "Home": "HME",
                "Predicted Winner": "AWY",
                "Side Tracking Segment": "Official",
                "Scoring Tracking Segment": "No Edge",
                "League Total Baseline": 44,
                "Challenger Status": "Tracked",
                "Challenger Predicted Winner": "HME",
                "Challenger Side Edge": "HME Edge",
                "Challenger Scoring Edge": "Neutral Scoring Environment",
                "Challenger Features": {
                    "net_epa_diff": 0.1,
                },
                "Challenger Factors": ["net EPA/play favors HME"],
            }
        )
        stored = prediction_values(
            row, "market-v1", "baseline-v1", "2026-09-10T12:00:00+00:00"
        )
        settled = result_values(
            pd.Series(
                {
                    "Status": "Final",
                    "Away Score": 17,
                    "Home Score": 24,
                    "Actual Winner": "HME",
                    "Actual Total": 41,
                }
            ),
            stored,
            "2026-09-11T03:00:00+00:00",
        )

        self.assertEqual(settled["side_result"], "Missed")
        self.assertEqual(settled["challenger_side_result"], "Correct")

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "nfl.sqlite3"
            with patch.dict("os.environ", {"HISTORY_BACKEND": "sqlite"}):
                with connect(db_path) as connection:
                    init_db(connection)
                    columns = {
                        item["name"]
                        for item in connection.execute(
                            "PRAGMA table_info(nfl_model_history)"
                        ).fetchall()
                    }
        self.assertIn("challenger_features", columns)
        self.assertIn("challenger_side_result", columns)


if __name__ == "__main__":
    unittest.main()
