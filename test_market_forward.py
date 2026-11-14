import ast
import importlib
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from cfb_market import attach_market_context, decode_context
from market_forward import init_market_db, market_report, persist_market_row, reconcile_market_results
from test_cfb_market import context, game, quote


class MarketForwardTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        init_market_db(self.connection)
        self.row = game()
        self.stored = {"model_margin": 2, "projected_total": 49, "snapshot_status": "Pregame",
                       "created_at": "2026-11-14T10:00:00Z", "slate_date": "2026-11-14"}

    def tearDown(self):
        self.connection.close()

    def save(self, sport="NBA", row=None, stored=None, now="2026-11-14T13:00Z"):
        persist_market_row(self.connection, sport, row or self.row, stored or self.stored, "baseline", "market", now)

    def records(self):
        return [dict(row) for row in self.connection.execute("SELECT * FROM market_forward_snapshots")]

    def test_basketball_quote_pairs_with_stored_not_recalculated_model(self):
        self.row["Model Margin"] = 100
        self.save()
        saved = self.records()[0]
        paired = decode_context(saved["market_context"])
        self.assertEqual(paired["model_margin"], 2)
        self.assertEqual(paired["prediction_as_of"], self.stored["created_at"])
        self.assertEqual(self.stored["model_margin"], 2)

    def test_observations_append_and_lock_cannot_reopen(self):
        self.save()
        updated = context()
        updated["captured_at"] = "2026-11-14T14:00:00Z"
        updated["quotes"][0]["home_spread"] = -3.5
        changed = {**self.row, "Market Context": json.dumps(updated)}
        self.save(row=changed, now="2026-11-14T14:30Z")
        final = {**self.row, "Status": "Final", "Home Score": 24, "Away Score": 21}
        self.save(row=final, now="2026-11-15T04:00Z")
        saved = self.records()[0]
        self.assertEqual(saved["snapshot_status"], "Locked")
        self.assertEqual(decode_context(saved["market_context"])["quotes"][0]["home_spread"], -3.5)
        report = market_report(self.records())
        self.assertEqual(report[0]["Result"], "Cover")
        self.assertEqual(report[0]["Model Track"], "Baseline")
        self.save(row={**changed, "Scheduled Kickoff": "2026-11-16T00:30Z"}, now="2026-11-15T05:00Z")
        self.assertEqual(self.records()[0]["snapshot_status"], "Locked")
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM market_forward_observations").fetchone()[0], 2)

    def test_no_poststart_backfill_or_empty_quote_insertion(self):
        self.save(now="2026-11-15T04:00Z")
        self.assertEqual(self.records(), [])
        self.save(row={**self.row, "Market Context": None})
        self.assertEqual(self.records(), [])

    def test_nfl_tracks_and_versions_separate_and_challenger_has_no_total(self):
        tracked = {**self.stored, "challenger_status": "Tracked", "challenger_model_version": "v1",
                   "challenger_model_margin": -7, "challenger_projected_total": 44}
        self.save(sport="NFL", stored=tracked)
        self.save(sport="NFL", stored={**tracked, "challenger_model_version": "v2"})
        records = self.records()
        self.assertEqual(len(records), 3)
        challenger = [r for r in records if r["track"] == "Challenger"]
        self.assertEqual({r["track_version"] for r in challenger}, {"v1", "v2"})
        self.assertTrue(all(decode_context(r["market_context"])["projected_total"] is None for r in challenger))
        self.save(sport="NFL", row={**self.row, "Status": "Final", "Home Score": 24, "Away Score": 21},
                  stored=self.stored, now="2026-11-15T04:00Z")
        report = market_report(self.records())
        self.assertEqual(len([r for r in report if r["Model Track"] == "Baseline"]), 2)
        self.assertEqual({r["Market"] for r in report if r["Model Track"] == "Challenger"}, {"Spread"})

    @patch("market_forward.requests.get")
    def test_result_only_reconciliation_settles_prior_day_without_replacing_quote(self, get):
        saved_context = {**context(), "event_id": "espn-result"}
        self.save(row={**self.row, "Market Context": json.dumps(saved_context)})
        original = self.records()[0]["market_context"]
        get.return_value = Mock()
        get.return_value.json.return_value = {"header": {"id": "espn-result", "competitions": [{
            "status": {"type": {"completed": True}}, "competitors": [
                {"homeAway": "home", "score": "24"}, {"homeAway": "away", "score": "21"},
            ],
        }]}, "pickcenter": [{"spread": -99}]}
        reconcile_market_results(self.connection, "NBA", "2026-11-16T12:00Z")
        saved = self.records()[0]
        self.assertEqual(saved["market_context"], original)
        self.assertEqual(saved["snapshot_status"], "Locked")
        self.assertEqual(saved["status"], "Final")
        self.assertEqual(market_report(self.records())[0]["Result"], "Cover")
        get.assert_called_once()

    def test_nfl_record_hook_tracks_without_changing_baseline(self):
        import nfl_model_history as module
        from contextlib import nullcontext
        from datetime import datetime, timezone
        row = {**self.row, "Slate Date": "2026-11-14", "Predicted Winner": "LSU", "Side Edge": "LSU Edge",
               "Side Tracking Segment": "Official", "Challenger Status": "Tracked", "Challenger Model Version": "v1",
               "Challenger Model Margin": -7, "Challenger Projected Total": 44}
        with patch.object(module, "connect", return_value=nullcontext(self.connection)):
            module.record_nfl_history(pd.DataFrame([row]), "market", "baseline",
                                      now=datetime(2026, 11, 14, 13, tzinfo=timezone.utc))
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(self.connection.execute("SELECT model_margin FROM nfl_model_history").fetchone()[0], 2)

    @patch("cfb_market.requests.get")
    def test_nfl_schedule_id_resolves_to_espn_event(self, get):
        contest = {"competitors": [
            {"homeAway": "away", "team": {"abbreviation": "NE"}},
            {"homeAway": "home", "team": {"abbreviation": "DET"}},
        ]}
        scoreboard = Mock()
        scoreboard.json.return_value = {"events": [{"id": "espn-id", "competitions": [contest]}]}
        summary = Mock()
        summary.json.return_value = {"header": {"id": "espn-id", "competitions": [
            {"date": self.row["Scheduled Kickoff"], "status": {"type": {"state": "pre"}}}
        ]}, "pickcenter": [quote()]}
        get.side_effect = [scoreboard, summary]
        frame = pd.DataFrame([{**self.row, "Game ID": "2026_11_NE_DET", "Away": "NE", "Home": "DET"}])
        result = attach_market_context(frame, now="2026-11-14T13:00Z", sport="NFL")
        self.assertEqual(decode_context(result.iloc[0]["Market Context"])["event_id"], "espn-id")
        self.assertEqual(get.call_args.kwargs["params"]["event"], "espn-id")

    @patch("cfb_market.requests.get")
    def test_basketball_uses_sort_date_and_sport_specific_endpoint(self, get):
        row = {**self.row, "Sort Date": self.row["Scheduled Kickoff"]}
        del row["Scheduled Kickoff"]
        get.return_value = Mock()
        get.return_value.json.return_value = {"header": {"id": "1", "competitions": [
            {"date": row["Sort Date"], "status": {"type": {"state": "pre"}}}
        ]}, "pickcenter": [quote()]}
        for sport, path in (("NBA", "basketball/nba"), ("CBB", "basketball/mens-college-basketball")):
            result = attach_market_context(pd.DataFrame([row]), now="2026-11-14T13:00Z", sport=sport)
            self.assertIsNotNone(result.iloc[0]["Market Context"])
            self.assertIn(path, get.call_args.args[0])

    def test_basketball_snapshot_hooks_preserve_initial_forecast(self):
        for sport in ("NBA", "CBB"):
            module = importlib.import_module(f"{sport.lower()}_model_history")
            row = {**self.row, "Sort Date": self.row["Scheduled Kickoff"], "Model Signal": "LSU",
                   "Side Edge": "LSU", "Predicted Winner": "LSU", "Confidence": "C"}
            with patch.object(module, "connect", return_value=self.connection), \
                    patch.object(module, "utc_now", return_value="2026-11-14T13:00:00Z"):
                record = getattr(module, f"record_{sport.lower()}_history")
                record(pd.DataFrame([row]), "2026-11-14", "market", "baseline")
                record(pd.DataFrame([{**row, "Model Margin": 50}]), "2026-11-14", "market", "baseline")
            saved = self.connection.execute(f"SELECT model_margin FROM {sport.lower()}_model_history").fetchone()
            self.assertEqual(saved[0], 2)
            comparison = next(r for r in self.records() if r["sport"] == sport)
            self.assertEqual(decode_context(comparison["market_context"])["model_margin"], 2)

    def test_nfl_panels_label_tracks_and_reuse_metric_value_tables(self):
        from streamlit.testing.v1 import AppTest
        tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
        functions = {"render_sport_market_comparison", "render_cfb_market_comparison"}
        source = "import streamlit as st\nimport pandas as pd\nfrom cfb_market import decode_context,comparison_rows\nformat_snapshot_time=str\n"
        source += "\n".join(ast.unparse(n) for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in functions)
        source += "\nMODEL_BASELINES={'NFL':'baseline'}\nMARKET_RELEASES={'NFL':'market'}\n"
        source += "saved=" + repr([{"game_id": "1", "track": track, "market_context": json.dumps({**context(), "model_margin": 2, "projected_total": 49 if track == "Baseline" else None})} for track in ("Baseline", "Challenger")]) + "\n"
        source += "load_sport_market_history=lambda *args:saved\nrender_sport_market_comparison(" + repr(self.row) + ", 'NFL')\n"
        app = AppTest.from_string(source).run()
        self.assertEqual(len(app.exception), 0)
        text = "\n".join(m.value for m in app.markdown)
        self.assertIn("Model vs Market: Baseline", text)
        self.assertIn("Model vs Market: Challenger", text)
        self.assertEqual(text.count("| Metric | Value |"), 3)


if __name__ == "__main__":
    unittest.main()
