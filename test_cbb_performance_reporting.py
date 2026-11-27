import ast
from datetime import datetime, timedelta
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

import pandas as pd

from performance_reporting import cbb_report_details, performance_cards_html
from test_performance_reporting import market_row


def prediction(**changes):
    return {"game_id": "1", "slate_date": datetime.now(ZoneInfo("America/New_York")).date().isoformat(),
            "game": "A @ H", "side_edge": "H Edge", "predicted_winner": "H", "confidence": "C",
            "scoring_edge": "High Scoring Environment", "side_result": "Correct", "scoring_result": "Missed",
            "status": "Final", "snapshot_status": "Locked", "model_version": "1", "market_version": "2",
            "margin_error": 2, "total_error": 3, "projected_total": 150, "updated_at": "2026-11-27T12:00Z",
            **changes}


class CbbPerformanceReportingTests(unittest.TestCase):
    def test_side_confidence_does_not_filter_scoring_or_fabricate_segments(self):
        details = cbb_report_details([prediction()], confidence="A")
        self.assertEqual(details.Signal.tolist(), ["Scoring"])
        self.assertEqual(details.Confidence.tolist(), ["Uncalibrated"])
        self.assertNotIn("Segment", details.columns)
        html = performance_cards_html(details, "model")
        self.assertIn("Scoring vs Internal Baseline", html)
        self.assertNotIn("<th>Segment</th>", html)
        self.assertTrue(cbb_report_details([prediction(snapshot_status="Not Tracked")]).empty)
        no_signals = prediction(side_edge="Pass", scoring_edge="Neutral Scoring Environment")
        self.assertTrue(cbb_report_details([no_signals]).empty)

    def app(self):
        from streamlit.testing.v1 import AppTest
        tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
        names = {"render_cbb_performance_section", "render_cbb_model_performance", "render_market_performance"}
        today = datetime.now(ZoneInfo("America/New_York")).date()
        rows = [prediction(), prediction(game_id="old", slate_date="2000-01-01"),
                prediction(game_id="future", slate_date=(today + timedelta(days=1)).isoformat())]
        source = '''import streamlit as st
import pandas as pd
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from performance_reporting import *
from cfb_market import decode_context
FALLBACK_TIMEZONE="America/New_York"
MODEL_BASELINES={"CBB":"1"}
MARKET_RELEASES={"CBB":"2"}
format_snapshot_caption=lambda rows:"Snapshot as of: 11/27/2026, 7:00 AM ET" if rows else "Snapshot as of: N/A"
format_snapshot_time=str
wnba_rows_to_csv=lambda rows:pd.DataFrame(rows).to_csv(index=False)
load_cbb_performance_tables=lambda **kwargs:{k:[] for k in ["core","confidence","side_location","scoring","history","rest"]}
load_cbb_performance_summary=lambda **kwargs:dict(snapshots=3,completed=2,side_signal_games=3,scoring_signal_games=3,storage_backend="SQLite",db_path="test")
load_sport_market_history=lambda *args:[]
'''
        source += "load_cbb_history=lambda **kwargs:" + repr(rows) + "\n"
        source += "market_report=lambda _:" + repr([market_row(Sport="CBB", Slate=today.isoformat())]) + "\n"
        source += "\n".join(ast.unparse(n) for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names)
        source += "\nrender_cbb_performance_section()"
        return AppTest.from_string(source).run()

    def test_date_presets_use_current_eastern_day_and_custom(self):
        app = self.app()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.selectbox[1].value, "Last 30")
        details = next(d.value for d in app.dataframe if "Pick" in d.value.columns)
        self.assertEqual(len(details), 2)
        app.selectbox[1].select("Yesterday").run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("No CBB tracked results" in x.value for x in app.info))
        app.selectbox[1].select("Today").run()
        details = next(d.value for d in app.dataframe if "Pick" in d.value.columns)
        self.assertEqual(len(details), 2)
        app.selectbox[1].select("All").run()
        details = next(d.value for d in app.dataframe if "Pick" in d.value.columns)
        self.assertEqual(len(details), 6)
        app.selectbox[1].select("Custom").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.date_input), 1)
        self.assertEqual(app.expander[-1].label, "Exports")

    def test_market_view_has_no_challenger_or_halftime_controls(self):
        app = self.app()
        app.segmented_control[0].set_value("Model vs Market").run()
        self.assertEqual(len(app.exception), 0)
        self.assertNotIn("Model Track", [s.label for s in app.selectbox])
        self.assertEqual(app.selectbox[1].value, "Last 30")
        self.assertNotIn("Challenger", " ".join(e.label for e in app.expander))
        self.assertEqual(app.expander[-1].label, "Exports")
        app.selectbox[1].select("All").run()
        self.assertEqual(len(app.exception), 0)
        app.selectbox[1].select("Custom").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.date_input), 1)


if __name__ == "__main__":
    unittest.main()
