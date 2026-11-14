import json
import sqlite3
import unittest

import numpy as np
import pandas as pd

from cbb_model_history import (
    db_values, init_db, insert_prediction, prediction_values,
    result_values, safe_float, update_result,
)


class StrictConnection:
    """Reject non-JSON SQL arguments before SQLite can silently accept NaN."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params=()):
        json.dumps(list(params), allow_nan=False)
        return self.connection.execute(query, params)


class CbbHistoryTests(unittest.TestCase):
    def test_missing_and_nonfinite_database_values(self):
        values = db_values([np.nan, pd.NA, pd.NaT, np.inf, -np.inf,
                            np.int64(3), np.float64(2.5), "Pending", None])
        self.assertEqual(values, [None] * 5 + [3, 2.5, "Pending", None])
        json.dumps(values, allow_nan=False)
        for value in [np.nan, np.inf, -np.inf, "inf", "nan"]:
            self.assertIsNone(safe_float(value))

    def test_insert_and_result_updates_use_json_safe_parameters(self):
        with sqlite3.connect(":memory:") as connection:
            connection.row_factory = sqlite3.Row
            init_db(connection)
            strict = StrictConnection(connection)
            now = "2026-11-14T20:00:00Z"
            row = pd.Series({
                "Game ID": "123", "Game": "Away @ Home",
                "Away": "Away", "Home": "Home", "Status": "Scheduled",
                "Game Time": np.nan, "Model Signal": np.nan,
                "Model Margin": 4.5, "Projected Total": 150,
                "Edge Score": np.inf, "Actual Winner": np.nan,
                "Side Result": pd.NA, "Scoring Result": np.nan,
            })
            insert_prediction(strict, prediction_values(row, "2026-11-14", "m", "v", now))
            update_result(strict, "123", "m", "v", result_values(row, now))
            saved = dict(connection.execute("SELECT * FROM cbb_model_history").fetchone())
            self.assertIsNone(saved["actual_winner"])
            self.assertIsNone(saved["side_result"])
            self.assertIsNone(saved["edge_score"])
            self.assertEqual(saved["snapshot_status"], "Pregame")
            row = pd.Series({**row.to_dict(), "Status": "Final", "Away Score": 70,
                                  "Home Score": 80, "Actual Total": 150,
                                  "Actual Winner": "Home", "Side Result": "Correct",
                                  "Scoring Result": "Missed"})
            update_result(strict, "123", "m", "v", result_values(row, now))
            saved = dict(connection.execute("SELECT * FROM cbb_model_history").fetchone())
            self.assertEqual(saved["actual_winner"], "Home")
            self.assertEqual(saved["margin_error"], 5.5)
            self.assertEqual(saved["total_error"], 0)
            self.assertEqual(saved["snapshot_status"], "Locked")
            self.assertEqual(saved["model_margin"], 4.5)


if __name__ == "__main__":
    unittest.main()
