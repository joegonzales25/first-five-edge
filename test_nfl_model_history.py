import math
import unittest
import sqlite3
from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np
import pandas as pd

from nfl_model_history import (
    db_values, insert_values, safe_float, record_nfl_history,
)


class CapturingConnection:
    def __init__(self):
        self.params = None

    def execute(self, _query, params):
        self.params = params


class NflModelHistoryTests(unittest.TestCase):
    def test_pregame_tier_changes_refresh_results_and_locked_pick_is_preserved(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        from contextlib import nullcontext

        row = {
            "Game ID": "2026_02_IND_KC", "Game": "IND @ KC",
            "Scheduled Kickoff": "2026-09-20T20:00:00+00:00",
            "Slate Date": "2026-09-20", "Status": "Scheduled",
            "Predicted Winner": "KC", "Side Edge": "Pass",
            "Side Tracking Segment": "No Edge", "Confidence": "Pass",
            "Scoring Tracking Segment": "No Edge",
            "Scoring Edge": "Neutral Scoring Environment",
        }
        now = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)
        try:
            with patch("nfl_model_history.connect", return_value=nullcontext(connection)):
                record_nfl_history(pd.DataFrame([row]), "test", "test", now=now)
                row.update({
                    "Side Edge": "KC Edge", "Side Tracking Segment": "Official", "Confidence": "C",
                    "Scoring Edge": "High Scoring Environment", "Scoring Tracking Segment": "Official",
                    "League Total Baseline": 44,
                })
                record_nfl_history(pd.DataFrame([row]), "test", "test", now=now)
                stored = dict(connection.execute("SELECT * FROM nfl_model_history").fetchone())
                self.assertEqual(stored["side_result"], "Pending")
                self.assertEqual(stored["scoring_result"], "Pending")
                self.assertEqual(stored["side_tracking_segment"], "Official")
                row.update({"Side Edge": "Pass", "Side Tracking Segment": "No Edge"})
                record_nfl_history(pd.DataFrame([row]), "test", "test", now=now)
                self.assertEqual(connection.execute("SELECT side_result FROM nfl_model_history").fetchone()[0], "No Signal")
                row.update({"Side Edge": "KC Edge", "Side Tracking Segment": "Official"})
                record_nfl_history(pd.DataFrame([row]), "test", "test", now=now)
                connection.execute("UPDATE nfl_model_history SET snapshot_status = 'Locked'")
                row.update({"Predicted Winner": "IND", "Status": "Final", "Actual Winner": "KC", "Away Score": 10, "Home Score": 20, "Actual Total": 30})
                record_nfl_history(pd.DataFrame([row]), "test", "test", now=now)
                stored = dict(connection.execute("SELECT * FROM nfl_model_history").fetchone())
                self.assertEqual(stored["predicted_winner"], "KC")
                self.assertEqual(stored["side_result"], "Correct")
        finally:
            connection.close()

    def test_safe_float_rejects_missing_and_non_finite_values(self):
        for value in [pd.NA, np.nan, math.inf, -math.inf]:
            with self.subTest(value=value):
                self.assertIsNone(safe_float(value))

    def test_db_values_normalize_pandas_and_numpy_scalars(self):
        self.assertEqual(
            db_values([pd.NA, np.nan, np.float64(math.inf), np.int64(3)]),
            [None, None, None, 3],
        )

    def test_insert_sanitizes_all_columns_at_database_boundary(self):
        connection = CapturingConnection()

        insert_values(
            connection,
            {
                "game_id": "2026_01_AWY_HME",
                "challenger_coverage": np.nan,
                "challenger_model_margin": np.float64(math.inf),
            },
        )

        self.assertEqual(
            connection.params,
            ["2026_01_AWY_HME", None, None],
        )


if __name__ == "__main__":
    unittest.main()
