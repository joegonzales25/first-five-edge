import json
import sqlite3
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from cbb_model_history import (
    db_values, init_db, insert_prediction, prediction_values,
    result_values, safe_float, update_result,
    record_cbb_history,
)


class StrictConnection:
    """Reject non-JSON SQL arguments before SQLite can silently accept NaN."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params=()):
        json.dumps(list(params), allow_nan=False)
        return self.connection.execute(query, params)


class CbbHistoryTests(unittest.TestCase):
    def frozen_prediction(self, **changes):
        return {"home_team": "Home", "away_team": "Away", "side_edge": "Home Edge",
                "predicted_winner": "Home", "scoring_edge": "High Scoring Environment",
                "model_margin": 8, "projected_total": 155, "league_total_baseline": 150,
                **changes}

    def test_grading_uses_stored_forecast_not_rebuilt_labels_or_totals(self):
        row = {"Status": "Final", "Away Score": 70, "Home Score": 82,
               "Actual Winner": "Away", "Actual Total": 999,
               "Side Result": "Missed", "Scoring Result": "Missed",
               "Model Margin": -20, "Projected Total": 200}
        values = result_values(row, "now", self.frozen_prediction())
        self.assertEqual(values["actual_winner"], "Home")
        self.assertEqual(values["actual_total"], 152)
        self.assertEqual(values["side_result"], "Correct")
        self.assertEqual(values["scoring_result"], "Correct")
        self.assertEqual(values["margin_error"], 4)
        self.assertEqual(values["total_error"], 3)

    def test_no_signals_pending_and_baseline_equality_keep_existing_rules(self):
        final = {"Status": "Final", "Away Score": 70, "Home Score": 80}
        for scoring in ("High Scoring Environment", "Low Scoring Environment"):
            values = result_values(final, "now", self.frozen_prediction(scoring_edge=scoring))
            self.assertEqual(values["scoring_result"], "Missed")
        values = result_values(final, "now", self.frozen_prediction(
            side_edge="Pass", scoring_edge="Neutral Scoring Environment"))
        self.assertEqual(values["side_result"], "No Signal")
        self.assertEqual(values["scoring_result"], "No Signal")
        for row in ({"Status": "Scheduled"}, {**final, "Status": "In Progress"},
                    {"Status": "Final", "Away Score": None, "Home Score": 80}):
            values = result_values(row, "now", self.frozen_prediction())
            self.assertEqual(values["side_result"], "Pending")
            self.assertEqual(values["scoring_result"], "Pending")

    def test_missing_stored_forecasts_do_not_use_new_projection(self):
        row = {"Status": "Final", "Away Score": 70, "Home Score": 80,
               "Model Margin": 100, "Projected Total": 200}
        values = result_values(row, "now", self.frozen_prediction(
            model_margin=None, projected_total=None, league_total_baseline=None,
            predicted_winner=None))
        self.assertEqual(values["side_result"], "Pending")
        self.assertEqual(values["scoring_result"], "Pending")
        self.assertIsNone(values["margin_error"])
        self.assertIsNone(values["total_error"])

    def test_record_history_grades_original_pick_and_preserves_forecast(self):
        with sqlite3.connect(":memory:") as connection:
            connection.row_factory = sqlite3.Row
            row = {"Game ID": "1", "Game": "Away @ Home", "Away": "Away", "Home": "Home",
                   "Status": "Scheduled", "Model Margin": 8, "Projected Total": 155,
                   "League Total Baseline": 150, "Predicted Winner": "Home",
                   "Side Edge": "Home Edge", "Scoring Edge": "High Scoring Environment"}
            with patch("cbb_model_history.connect", return_value=connection), \
                    patch("cbb_model_history.reconcile_market_results"):
                record_cbb_history(pd.DataFrame([row]), "2026-11-24", "m", "v")
                changed = {**row, "Status": "Final", "Home Score": 82, "Away Score": 70,
                           "Model Margin": -20, "Projected Total": 200,
                           "Predicted Winner": "Away", "Side Result": "Missed",
                           "Scoring Result": "Missed"}
                record_cbb_history(pd.DataFrame([changed]), "2026-11-24", "m", "v")
            saved = dict(connection.execute("SELECT * FROM cbb_model_history").fetchone())
            self.assertEqual(saved["predicted_winner"], "Home")
            self.assertEqual(saved["model_margin"], 8)
            self.assertEqual(saved["projected_total"], 155)
            self.assertEqual(saved["side_result"], "Correct")
            self.assertEqual(saved["scoring_result"], "Correct")
            self.assertEqual(saved["margin_error"], 4)
            self.assertEqual(saved["total_error"], 3)

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
