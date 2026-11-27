import ast
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch
import sqlite3

import pandas as pd

from market_forward import init_market_db, load_market_snapshots
from performance_reporting import (
    filter_market_report, market_statistics, market_summary, paired_market_summary,
    difference_summary, nfl_report_projection_error,
    model_result_summary, paired_model_summary,
    performance_cards_html,
)


def market_row(track="Baseline", **changes):
    return {"Sport": "NFL", "Slate": date.today().isoformat(), "Game": "A @ H",
            "Model Track": track, "Model": "1" if track == "Baseline" else "test",
            "Baseline Version": "1", "Market Version": "2", "Market": "Spread",
            "Book": "Draft Kings", "Captured At": "2026-11-25T12:00Z", "Rule": "v1",
            "Market Line": -3, "Comparison": "H -3", "Projection Difference": 4,
            "Result": "Cover", "Hypothetical Units": 100 / 110, "American Odds": -110,
            **changes}


class ReportingTests(unittest.TestCase):
    def test_nfl_details_and_exports_follow_primary_results(self):
        tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
        for name in ["render_nfl_market_performance", "render_nfl_model_performance"]:
            with self.subTest(view=name):
                function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
                expanders = [n for n in ast.walk(function) if isinstance(n, ast.With)
                             and isinstance(n.items[0].context_expr, ast.Call)
                             and isinstance(n.items[0].context_expr.func, ast.Attribute)
                             and n.items[0].context_expr.func.attr == "expander"]
                primary = next(n for n in ast.walk(function) if isinstance(n, ast.Call)
                               and isinstance(n.func, ast.Attribute)
                               and n.func.attr == "html")
                for expander in expanders:
                    self.assertGreater(expander.lineno, primary.lineno)
                    call = expander.items[0].context_expr
                    self.assertTrue(any(k.arg == "expanded" and k.value.value is False for k in call.keywords))
                exports = next(n for n in expanders if n.items[0].context_expr.args[0].value == "Exports")
                self.assertEqual(exports.lineno, max(n.lineno for n in expanders))
                for node in ast.walk(function):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "download_button":
                        self.assertGreater(node.lineno, exports.lineno)
                        self.assertLessEqual(node.end_lineno, exports.end_lineno)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "dataframe":
                        self.assertTrue(any(expander.lineno < node.lineno <= expander.end_lineno
                                            for expander in expanders))

    def test_returns_exclude_missing_odds_and_pending_not_push_risk(self):
        frame = pd.DataFrame([
            market_row(), market_row(Result="Miss", **{"Hypothetical Units": -1}),
            market_row(Result="Push", **{"Hypothetical Units": 0}),
            market_row(Result="Cover", **{"American Odds": None, "Hypothetical Units": None}),
            market_row(Result="Pending", **{"Hypothetical Units": None}),
            market_row(Result="No Difference", **{"Hypothetical Units": None}),
        ])
        stats = market_statistics(frame)
        self.assertEqual(stats["Record"], "2-1-1")
        self.assertEqual(stats["Priced Settled"], 3)
        self.assertEqual(stats["Pending"], 1)
        self.assertEqual(stats["No Difference"], 1)
        self.assertEqual(stats["Missing Odds"], 1)
        self.assertAlmostEqual(stats["Return %"], -3.03, places=2)
        self.assertEqual(stats["Win Rate %"], 66.67)
        no_odds = market_statistics(frame.iloc[[3]])
        self.assertIsNone(no_odds["Net Units"])
        self.assertIsNone(no_odds["Return %"])

    def test_model_cards_combine_segments_and_order_tracks(self):
        row = {"Slate": "2026-11-25", "Game": "A @ H", "Model Track": "Baseline",
               "Model": "1", "Baseline Version": "1", "Market Version": "2", "Signal": "Side",
               "Segment": "Official", "Result": "Correct", "Margin Error": 2, "Total Error": None}
        frame = pd.DataFrame([row, {**row, "Segment": "Lean", "Result": "Missed"},
                              {**row, "Segment": "Watch", "Result": "Pending"},
                              {**row, "Model Track": "Challenger", "Model": "test"}])
        html = performance_cards_html(frame, "model")
        self.assertEqual(html.count("<article"), 2)
        self.assertIn("50.0%", html)
        self.assertIn("1 pending", html)
        self.assertIn("Official", html)
        self.assertIn("Lean", html)
        self.assertIn("Watch", html)
        self.assertLess(html.index("Baseline | Full-Game Winner"), html.index("Challenger | Full-Game Winner"))
        self.assertIn("@media(max-width:700px)", html)
        self.assertEqual(performance_cards_html(frame.iloc[:0], "model"), "")

    def test_market_cards_highlight_record_and_hide_financial_values(self):
        frame = pd.DataFrame([market_row(Result="Pending", **{"Hypothetical Units": None}),
                              market_row("Challenger", Result="Cover", **{"American Odds": None, "Hypothetical Units": None})])
        html = performance_cards_html(frame, "market")
        self.assertEqual(html.count("<article"), 2)
        self.assertIn('<div class="nfl-report-value">0-0-0</div>', html)
        self.assertIn('<div class="nfl-report-value">1-0-0</div>', html)
        self.assertNotIn("Units", html)
        self.assertNotIn("<dt>Return</dt>", html)
        self.assertIn("1 pending", html)
        self.assertIn("1 missing odds", html)
        self.assertIn("Priced Results", html)
        self.assertIn("Net Units", market_summary(frame).columns)
        self.assertIn("Return %", market_summary(frame).columns)

    def test_filters_and_bands_do_not_mutate_original(self):
        frame = pd.DataFrame([market_row(), market_row("Challenger"),
                              market_row(**{"Projection Difference": .5}),
                              market_row(Slate="2020-01-01")])
        original = frame.copy(deep=True)
        selected = filter_market_report(frame, date(2026, 1, 1), date(2027, 1, 1),
                                        track="Baseline", band="3 to under 5 points", version="1")
        self.assertEqual(len(selected), 1)
        pd.testing.assert_frame_equal(frame, original)
        self.assertEqual(len(market_summary(selected)), 1)
        self.assertEqual(len(difference_summary(selected)), 1)

    def test_matched_comparison_requires_same_quote_and_both_settled(self):
        rows = [market_row(), market_row("Challenger", Book="DraftKings"),
                market_row(Game="B @ H", Result="Miss", **{"Hypothetical Units": -1}),
                market_row("Challenger", Game="B @ H", Comparison="B +3"),
                market_row("Challenger", Game="Unmatched"),
                market_row(Game="Pending", Result="Pending"),
                market_row("Challenger", Game="Pending"),
                market_row(Game="Different time"),
                market_row("Challenger", Game="Different time", **{"Captured At": "other"})]
        result = paired_market_summary(pd.DataFrame(rows)).set_index("Selections")
        self.assertEqual(result.loc["Same side", "Paired Games"], 1)
        self.assertEqual(result.loc["Opposite sides", "Paired Games"], 1)
        self.assertEqual(result.loc["Opposite sides", "Baseline Record"], "0-1-0")
        self.assertEqual(result.loc["Opposite sides", "Challenger Record"], "1-0-0")

    def test_projection_errors_use_track_and_final_scores(self):
        row = {"status": "Final", "home_score": 24, "away_score": 20,
               "model_margin": 6, "projected_total": 46, "challenger_model_margin": -2}
        self.assertEqual(nfl_report_projection_error(row, "Baseline", "Side"), 2)
        self.assertEqual(nfl_report_projection_error(row, "Challenger", "Side"), 6)
        self.assertIsNone(nfl_report_projection_error(row, "Challenger", "Scoring"))
        self.assertIsNone(nfl_report_projection_error({**row, "status": "Scheduled"}, "Baseline", "Side"))

    def test_model_summary_and_pairs_exclude_unmatched_and_pending(self):
        def row(track, game, result):
            return {"Slate": "2026-11-25", "Game": game, "Signal": "Side",
                    "Baseline Version": "1", "Market Version": "2", "Model Track": track,
                    "Model": "1" if track == "Baseline" else "test", "Result": result,
                    "Margin Error": 2 if result == "Correct" else None, "Total Error": None}
        frame = pd.DataFrame([row("Baseline", "A", "Correct"), row("Challenger", "A", "Missed"),
                              row("Baseline", "B", "Correct"), row("Baseline", "C", "Pending"),
                              row("Challenger", "C", "Pending")])
        summary = model_result_summary(frame).set_index("Track")
        self.assertEqual(summary.loc["Baseline", "Correct"], 2)
        self.assertEqual(summary.loc["Baseline", "Pending"], 1)
        self.assertEqual(summary.loc["Baseline", "Margin MAE"], 2)
        paired = paired_model_summary(frame).set_index("Track")
        self.assertEqual(paired.loc["Baseline", "Paired Games"], 1)
        self.assertEqual(paired.loc["Baseline", "Accuracy %"], 100)
        self.assertEqual(paired.loc["Challenger", "Accuracy %"], 0)

    def test_market_loader_supports_all_versions_without_writes(self):
        import cbb_model_history
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        init_market_db(connection)
        for version in ("1", "2"):
            connection.execute("""INSERT INTO market_forward_snapshots
                (sport,game_id,model_version,market_version,track,track_version,market_context,snapshot_status)
                VALUES (?,?,?,?,?,?,?,?)""", ("CBB", "game", version, "market", "Baseline", version, "{}", "Locked"))
        statements = []
        connection.set_trace_callback(statements.append)
        # Keep the test connection open while the production loader closes its handle.
        class Handle:
            def execute(self, *args):
                return connection.execute(*args)
            def close(self):
                pass
        with patch.object(cbb_model_history, "connect", return_value=Handle()):
            self.assertEqual(len(load_market_snapshots("CBB", None, None)), 2)
            selected = load_market_snapshots("CBB", "1", "market")
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0]["model_version"], "1")
        self.assertTrue(all(query.lstrip().startswith("SELECT") for query in statements))
        connection.close()

    def test_market_gui_controls_and_filtered_download(self):
        from streamlit.testing.v1 import AppTest
        tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "render_nfl_market_performance")
        source = '''import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from performance_reporting import *
from cfb_market import decode_context
FALLBACK_TIMEZONE="America/New_York"
MODEL_BASELINES={"NFL":"1"}
format_snapshot_time=str
safe_load_nfl_history=lambda:[]
load_sport_market_history=lambda *args:[]
'''
        source += "market_report=lambda _:" + repr([market_row(), market_row("Challenger"), market_row(Slate="2000-01-01")]) + "\n"
        source += ast.unparse(function) + "\nrender_nfl_market_performance()"
        app = AppTest.from_string(source).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.selectbox[0].value, "Both")
        self.assertEqual(app.selectbox[2].value, "Last 30")
        self.assertEqual(app.selectbox[2].options, ["Today", "Yesterday", "Last 7", "Last 30", "All", "Custom"])
        self.assertEqual(len(app.date_input), 0)
        self.assertTrue(any("Net Units" in d.value.columns for d in app.dataframe))
        app.selectbox[2].select("Yesterday").run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("No locked market comparisons" in i.value for i in app.info))
        app.selectbox[2].select("All").run()
        self.assertEqual(len(app.exception), 0)
        detail = next(d.value for d in app.dataframe if "Model Track" in d.value.columns)
        self.assertEqual(len(detail), 3)
        self.assertEqual(len(app.date_input), 0)
        app.selectbox[2].select("Custom").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.date_input), 1)
        app.selectbox[2].select("Today").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.date_input), 0)
        app.selectbox[0].select("Challenger").run()
        self.assertEqual(len(app.exception), 0)
        detail = next(d.value for d in app.dataframe if "Model Track" in d.value.columns)
        self.assertEqual(detail["Model Track"].tolist(), ["Challenger"])
        app.selectbox[1].select("Total").run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("No locked market comparisons" in i.value for i in app.info))

    def test_model_gui_preserves_exports_and_signal_specific_confidence(self):
        from streamlit.testing.v1 import AppTest
        tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
        names = {"render_nfl_model_performance", "nfl_signal_segment", "nfl_signal_result",
                 "nfl_signal_pick", "nfl_track_segment", "nfl_track_result", "nfl_track_pick"}
        row = {"slate_date": date.today().isoformat(), "game": "A @ H", "model_version": "1",
               "market_version": "2", "snapshot_status": "Locked", "status": "Final",
               "home_score": 24, "away_score": 20, "predicted_winner": "H", "confidence": "A",
               "side_tracking_segment": "Official", "side_result": "Correct", "model_margin": 8,
               "scoring_tracking_segment": "Official", "scoring_result": "Correct",
               "scoring_edge": "High Scoring Environment", "projected_total": 46,
               "league_total_baseline": 42, "edge_score": 80, "challenger_status": "Tracked",
               "challenger_side_edge": "H Edge", "challenger_predicted_winner": "H",
               "challenger_confidence": "B", "challenger_model_version": "test",
               "challenger_model_margin": 6, "challenger_side_result": "Correct",
               "first_half_segment": "Watch", "first_half_pick": "H", "first_half_result": "Correct"}
        source = '''import streamlit as st
import pandas as pd
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from html import escape
from performance_reporting import *
FALLBACK_TIMEZONE="America/New_York"
MODEL_BASELINES={"NFL":"1"}
MARKET_RELEASES={"NFL":"2"}
performance_hit_rate=lambda _:"50%"
load_nfl_performance_summary=lambda **kwargs:dict(snapshots=1,completed=1,side_signal_games=1,scoring_signal_games=1,storage_backend="SQLite")
'''
        source += "safe_load_nfl_history=lambda:[" + repr(row) + "]\n"
        source += "\n".join(ast.unparse(n) for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names)
        source += "\nrender_nfl_model_performance()"
        app = AppTest.from_string(source).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.selectbox[4].value, "All")
        details = next(d.value for d in app.dataframe if "Pick" in d.value.columns)
        scoring = details.loc[details["Signal"] == "Scoring"].iloc[0]
        self.assertEqual(scoring["Confidence"], "Uncalibrated")
        self.assertTrue(pd.isna(scoring["Side Confidence"]))
        self.assertTrue(pd.isna(scoring["Score"]))
        self.assertEqual(scoring["Evaluation Basis"], "Internal scoring baseline")
        app.selectbox[1].select("Custom").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.date_input), 1)

    def test_versions_are_not_merged_in_market_summaries(self):
        frame = pd.DataFrame([market_row("Challenger"),
                              market_row("Challenger", **{"Baseline Version": "2"})])
        self.assertEqual(len(market_summary(frame)), 2)

    def test_report_view_switch_is_available_without_model_history(self):
        from streamlit.testing.v1 import AppTest
        tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "render_nfl_performance")
        source = "import streamlit as st\nrender_nfl_model_performance=lambda:st.info('model')\nrender_nfl_market_performance=lambda:st.info('market')\n"
        source += ast.unparse(function) + "\nrender_nfl_performance()"
        app = AppTest.from_string(source).run()
        self.assertEqual(app.info[0].value, "model")
        app.segmented_control[0].set_value("Model vs Market").run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.info[0].value, "market")


if __name__ == "__main__":
    unittest.main()
