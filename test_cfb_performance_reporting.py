import ast
from datetime import datetime, timedelta
import json
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

import pandas as pd

from cfb_market import forward_rows
from performance_reporting import cfb_report_details, cfb_market_report_data, performance_cards_html
from test_cfb_market import context


def saved_row(**changes):
    return {"game_id": "1", "slate_date": datetime.now(ZoneInfo("America/New_York")).date().isoformat(),
            "game": "Away @ Home", "home_team": "Home", "away_team": "Away",
            "market": "Full Game", "decision_tier": "Watch", "confidence": "C", "pick": "Home",
            "result": "Correct", "stored_outcome": "Hit", "status": "Final", "snapshot_status": "Locked",
            "model_version": "1", "market_version": "2", "model_margin": 2, "projected_total": 49,
            "home_score": 24, "away_score": 21, "updated_at": "2026-11-27T12:00Z",
            "scheduled_kickoff": "2026-11-15T00:30Z", "market_context": json.dumps(context()), **changes}


class CfbReportingTests(unittest.TestCase):
    def test_adapter_preserves_original_market_grades_and_history(self):
        rows = [saved_row(), saved_row(market="Scoring Environment"), saved_row(market="First Half")]
        original = json.dumps(rows)
        snapshots, report = cfb_market_report_data(rows)
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(len(report), 2)
        legacy = forward_rows(rows)
        for old, new in zip(legacy, report):
            self.assertEqual(new["Sport"], "CFB")
            self.assertEqual(new["Model Track"], "Baseline")
            self.assertEqual(new["Baseline Version"], old["Model"])
            for column in old:
                self.assertEqual(new[column], old[column])
        self.assertEqual(json.dumps(rows), original)
        self.assertEqual(cfb_market_report_data([saved_row(market_context=None)]), ([], []))

    def test_model_adapts_tiers_and_halftime_without_changing_results(self):
        rows = [saved_row(), saved_row(market="Scoring Environment", decision_tier="Lean", result="Missed"),
                saved_row(market="First Half", result="Push"), saved_row(snapshot_status="Pregame")]
        details = cfb_report_details(rows)
        self.assertEqual(details.Signal.tolist(), ["Side", "Scoring", "First Half"])
        self.assertEqual(details.Result.tolist(), ["Correct", "Missed", "Push"])
        self.assertEqual(details.Segment.tolist(), ["Watch", "Lean", "Watch"])
        html = performance_cards_html(details, "model")
        self.assertEqual(html.count("<article"), 3)
        self.assertIn("Halftime Leader", html)
        self.assertIn("Watch", html)

    def app(self):
        from streamlit.testing.v1 import AppTest
        tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
        names = {"render_cfb_performance_section", "render_cfb_model_performance",
                 "cfb_filtered_history", "render_market_performance"}
        today = datetime.now(ZoneInfo("America/New_York")).date()
        rows = [saved_row(), saved_row(market="Scoring Environment", decision_tier="Lean"),
                saved_row(market="First Half"), saved_row(game_id="old", slate_date="2000-01-01"),
                saved_row(game_id="future", slate_date=(today + timedelta(days=1)).isoformat())]
        source = '''import streamlit as st
import pandas as pd
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from performance_reporting import *
from cfb_market import decode_context,forward_rows
FALLBACK_TIMEZONE="America/New_York"
MODEL_BASELINES={"CFB":"1"}
MARKET_RELEASES={"CFB":"2"}
format_snapshot_caption=lambda _:"Snapshot as of: 11/27/2026, 7:00 AM ET"
format_snapshot_time=str
load_cfb_performance_summary=lambda **kwargs:dict(snapshots=5,completed=5,leans=1,watches=4,storage_backend="SQLite",db_path="test")
load_cfb_performance_tables=lambda **kwargs:dict(tier=[],market=[])
'''
        source += "load_cfb_history=lambda **kwargs:" + repr(rows) + "\n"
        source += "\n".join(ast.unparse(n) for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names)
        source += "\nrender_cfb_performance_section()"
        return AppTest.from_string(source).run()

    def test_model_dates_decision_filters_and_bottom_exports(self):
        app = self.app()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.selectbox[1].value, "Last 30")
        details = next(d.value for d in app.dataframe if "Pick" in d.value.columns)
        self.assertEqual(len(details), 3)
        app.selectbox[2].select("Lean").run()
        self.assertEqual(len(app.exception), 0)
        details = next(d.value for d in app.dataframe if "Pick" in d.value.columns)
        self.assertEqual(details.Signal.tolist(), ["Scoring"])
        app.selectbox[1].select("Yesterday").run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("No locked CFB decisions" in x.value for x in app.info))
        app.selectbox[2].select("All").run()
        app.selectbox[1].select("All").run()
        details = next(d.value for d in app.dataframe if "Pick" in d.value.columns)
        self.assertEqual(len(details), 5)
        app.selectbox[1].select("Custom").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.date_input), 1)
        self.assertEqual(app.expander[-1].label, "Exports")

    def test_market_report_uses_existing_cfb_quotes_without_challenger(self):
        app = self.app()
        app.segmented_control[0].set_value("Model vs Market").run()
        self.assertEqual(len(app.exception), 0)
        self.assertNotIn("Model Track", [x.label for x in app.selectbox])
        detail = next(d.value for d in app.dataframe if "Comparison" in d.value.columns)
        self.assertEqual(set(detail["Market"]), {"Spread", "Total"})
        self.assertTrue(all(detail["Model Track"] == "Baseline"))
        self.assertNotIn("Challenger", " ".join(e.label for e in app.expander))
        app.selectbox[1].select("All").run()
        self.assertEqual(len(app.exception), 0)
        app.selectbox[1].select("Custom").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.expander[-1].label, "Exports")


if __name__ == "__main__":
    unittest.main()
