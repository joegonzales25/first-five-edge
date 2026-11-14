from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from cfb_market import attach_market_context, comparison_rows, forward_rows, normalize_quotes, valid_context
from cfb_model_history import MARKETS, init_db, prediction_values, record_cfb_history


def quote():
    return {"provider": {"id": "100", "name": "Example Book"}, "spread": -4.5,
            "overUnder": 46.5, "overOdds": -110, "underOdds": -110,
            "homeTeamOdds": {"favorite": True, "spreadOdds": -115, "moneyLine": -200},
            "awayTeamOdds": {"favorite": False, "spreadOdds": -105, "moneyLine": 170}}


def context():
    return {"version": "projection-direction-v1", "source": "ESPN summary",
            "captured_at": "2026-11-14T12:00:00+00:00", "quotes": normalize_quotes({"pickcenter": [quote()]})}


def game():
    return {"Game ID": "1", "Game": "Texas @ LSU", "Home": "LSU", "Away": "Texas",
            "Scheduled Kickoff": "2026-11-15T00:30:00Z", "Status": "Scheduled",
            "Model Margin": 2, "Projected Total": 49, "Market Context": json.dumps(context())}


class CfbMarketTests(unittest.TestCase):
    def test_home_favorite_away_favorite_pickem_and_ambiguous(self):
        self.assertEqual(normalize_quotes({"pickcenter": [quote()]})[0]["home_spread"], -4.5)
        item = quote()
        item["homeTeamOdds"]["favorite"] = False
        item["awayTeamOdds"]["favorite"] = True
        self.assertEqual(normalize_quotes({"pickcenter": [item]})[0]["home_spread"], 4.5)
        item["spread"] = 0
        self.assertEqual(normalize_quotes({"pickcenter": [item]})[0]["home_spread"], 0)
        item["spread"] = -3
        item["homeTeamOdds"]["favorite"] = True
        self.assertIsNone(normalize_quotes({"pickcenter": [item]})[0]["home_spread"])

    def test_winner_differs_from_cover_and_total_differs_from_baseline(self):
        result = comparison_rows(game(), context())
        self.assertEqual(result[0]["Comparison"], "Texas +4.5")
        self.assertEqual(result[0]["Model Read"], "LSU by 2")
        self.assertEqual(result[0]["Projection Difference"], 2.5)
        self.assertEqual(result[1]["Comparison"], "Over 46.5")
        self.assertAlmostEqual(result[0]["Break-even %"], 51.22)
        self.assertEqual(game()["Model Margin"], 2)

    def test_missing_prices_not_defaulted_and_no_difference_not_graded(self):
        saved = context()
        saved["quotes"][0]["away_spread_odds"] = None
        result = comparison_rows(game(), saved)[0]
        self.assertIsNone(result["American Odds"])
        self.assertIsNone(result["Break-even %"])
        row = {**game(), "Model Margin": 4.5}
        self.assertEqual(comparison_rows(row, saved)[0]["Result"], "No Difference")

    def test_quote_preserves_its_paired_projection_during_later_feed_outage(self):
        saved = {**context(), "model_margin": 2, "projected_total": 49}
        updated_baseline = {**game(), "Model Margin": 10, "Projected Total": 40}
        comparisons = comparison_rows(updated_baseline, saved)
        self.assertEqual(comparisons[0]["Comparison"], "Texas +4.5")
        self.assertEqual(comparisons[1]["Comparison"], "Over 46.5")

    def test_market_panel_has_team_named_comparisons_and_no_missing_price_assumptions(self):
        import ast
        from streamlit.testing.v1 import AppTest
        tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "render_cfb_market_comparison")
        source = "import streamlit as st\nimport pandas as pd\nfrom cfb_market import decode_context, comparison_rows\nformat_snapshot_time = str\n"
        source += ast.unparse(function) + "\n"
        source += "render_cfb_market_comparison(" + repr(game()) + ")\n"
        app = AppTest.from_string(source).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.dataframe), 0)
        tables = [m.value for m in app.markdown if m.value.startswith("| Metric | Value |")]
        self.assertEqual(len(tables), 2)
        self.assertIn("| Model | LSU by 2 |", tables[0])
        self.assertIn("| Market Line | LSU -4.5 |", tables[0])
        self.assertIn("| Comparison | Texas +4.5 |", tables[0])
        self.assertIn("| Projection Difference | 2.5 points |", tables[0])
        self.assertIn("| American Odds | -105 |", tables[0])
        self.assertIn("| Break-even Rate | 51.22% |", tables[0])
        self.assertIn("| Comparison | Over 46.5 |", tables[1])
        self.assertTrue(any("Book update time unavailable" in c.value for c in app.caption))

    def test_grade_frozen_spread_total_push_and_hypothetical_returns(self):
        row = {**game(), "Status": "Final", "Snapshot Status": "Locked", "Home Score": 24, "Away Score": 21}
        result = comparison_rows(row, context())
        self.assertEqual(result[0]["Result"], "Cover")
        self.assertAlmostEqual(result[0]["Hypothetical Units"], 100 / 105)
        self.assertEqual(result[1]["Result"], "Miss")
        self.assertEqual(result[1]["Hypothetical Units"], -1)
        saved = context()
        saved["quotes"][0]["total"] = 45
        self.assertEqual(comparison_rows(row, saved)[1]["Result"], "Push")
        self.assertEqual(comparison_rows({**row, "Snapshot Status": "Pregame"}, saved)[0]["Result"], "Pending")

    def test_postkickoff_and_future_context_rejected(self):
        self.assertTrue(valid_context(context(), game()["Scheduled Kickoff"], "2026-11-14T13:00Z"))
        self.assertFalse(valid_context(context(), game()["Scheduled Kickoff"], "2026-11-14T11:00Z"))
        self.assertFalse(valid_context(context(), "2026-11-14T12:00Z", "2026-11-14T13:00Z"))
        self.assertFalse(valid_context(float("nan"), None, "2026-11-14T13:00Z"))

    @patch("cfb_market.requests.get")
    def test_capture_is_pregame_only_and_missing_feed_does_not_change_model(self, get):
        get.return_value = Mock()
        payload = {"header": {"id": "1", "competitions": [{"date": game()["Scheduled Kickoff"],
                    "status": {"type": {"state": "pre"}}}]}, "pickcenter": [quote()]}
        get.return_value.json.return_value = payload
        frame = pd.DataFrame([game()])
        result = attach_market_context(frame, now="2026-11-14T13:00Z")
        self.assertIsNotNone(result.iloc[0]["Market Context"])
        self.assertEqual(result.iloc[0]["Model Margin"], 2)
        get.reset_mock()
        self.assertIsNone(attach_market_context(frame, now=game()["Scheduled Kickoff"]).iloc[0]["Market Context"])
        get.assert_not_called()
        payload["header"]["competitions"][0]["status"]["type"]["state"] = "in"
        self.assertIsNone(attach_market_context(frame, now="2026-11-14T13:00Z").iloc[0]["Market Context"])

    def test_database_archives_observations_and_freezes_locked_quote(self):
        import gc
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"HISTORY_BACKEND": "sqlite"}):
            path = Path(directory) / "history.sqlite3"
            row = game()
            row.update({"Side Pick": "LSU", "Side Tracking Segment": "Watch", "Side Confidence": "C",
                        "Scoring Pick": "High Scoring Environment", "First Half Pick": "Pass"})
            with patch("cfb_model_history.datetime") as clock:
                clock.now.return_value = datetime(2026, 11, 14, 13, tzinfo=timezone.utc)
                record_cfb_history(pd.DataFrame([row]), "2026-11-14", "market", "baseline", db_path=path)
                newer = context()
                newer["captured_at"] = "2026-11-14T13:30:00Z"
                newer["quotes"][0]["home_spread"] = -3.5
                row["Market Context"] = json.dumps(newer)
                clock.now.return_value = datetime(2026, 11, 14, 14, tzinfo=timezone.utc)
                record_cfb_history(pd.DataFrame([row]), "2026-11-14", "market", "baseline", db_path=path)
                with sqlite3.connect(path) as connection:
                    connection.execute("UPDATE cfb_model_history SET snapshot_status = 'Locked'")
                connection.close()
                row["Market Context"] = json.dumps(context())
                record_cfb_history(pd.DataFrame([row]), "2026-11-14", "market", "baseline", db_path=path)
            with sqlite3.connect(path) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM cfb_market_observations").fetchone()[0], 2)
                stored = connection.execute("SELECT market_context, pick FROM cfb_model_history WHERE market='Full Game'").fetchone()
                self.assertEqual(json.loads(stored[0])["quotes"][0]["home_spread"], -3.5)
                self.assertEqual(stored[1], "LSU")
            connection.close()
            gc.collect()

    def test_forward_export_separates_markets_and_ignores_legacy_history(self):
        saved = {"game": "Texas @ LSU", "home_team": "LSU", "away_team": "Texas",
                 "model_margin": 2, "projected_total": 49, "scheduled_kickoff": game()["Scheduled Kickoff"],
                 "market_context": json.dumps(context()), "snapshot_status": "Locked", "market": "Full Game"}
        # Use a later audit date without changing the stored pregame timestamp.
        with patch("cfb_market.datetime") as clock:
            clock.now.return_value = datetime(2026, 11, 16, tzinfo=timezone.utc)
            result = forward_rows([saved, {**saved, "market": "Scoring Environment"}, {**saved, "market_context": None}])
        self.assertEqual([r["Market"] for r in result], ["Spread", "Total"])


if __name__ == "__main__":
    unittest.main()
