from datetime import datetime, timezone
import ast
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from cfb_pregame_analysis import attach_pregame_analysis, build_analysis, load_analysis_season
from cfb_model_history import MARKETS, init_db, insert_prediction, prediction_values, update_open_prediction


def game(game_id, kickoff, away="Alpha", home="Beta", completed=True, away_class="FBS"):
    return {
        "game_id": game_id, "season": 2026, "season_type": "regular",
        "game_date_dt": pd.Timestamp(kickoff), "completed": completed,
        "away_team": away, "home_team": home, "away_team_id": "1", "home_team_id": "2",
        "away_classification": away_class, "home_classification": "FBS",
        "away_score": 20, "home_score": 30, "neutral_site": False,
    }


class CfbPregameAnalysisTests(unittest.TestCase):
    @patch("cfb_pregame_analysis.requests.get")
    @patch("cfb_pregame_analysis.fetch_espn_fbs_teams", return_value={"1": "SEC", "2": "ACC"})
    def test_combines_team_schedules_and_rejects_wrong_season(self, teams, get):
        from test_cfb_data import event
        response = Mock()
        payload = event()
        for competitor in payload["competitions"][0]["competitors"]:
            competitor["score"] = {"value": float(competitor["score"])}
        response.json.return_value = {"season": {"year": 2026}, "events": [payload]}
        get.return_value = response
        games = load_analysis_season(2026)
        self.assertEqual(len(games), 1)
        self.assertEqual(games.iloc[0]["home_score"], 24)
        self.assertEqual(get.call_count, 2)
        response.json.return_value = {"season": {"year": 2025}, "events": [event()]}
        with self.assertRaisesRegex(ValueError, "different season"):
            load_analysis_season(2026)

    def test_cfb_comparison_renders_compact_tables_and_last_five(self):
        from streamlit.testing.v1 import AppTest
        games = pd.DataFrame([game("1", "2026-09-01T20:00:00Z")])
        analysis = build_analysis(games, {}, 2026, "Alpha", "Beta", "2026-10-03T19:00:00Z")
        tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        source = "import streamlit as st\nimport json\nimport pandas as pd\nfrom html import escape\nformat_snapshot_time = str\nget_row_value = lambda row, key, default: row.get(key, default)\n"
        source += ast.unparse(functions["render_last_five_results"]) + "\n"
        source += ast.unparse(functions["render_nfl_pregame_comparison"]) + "\n"
        row = {"Sport": "CFB", "Away": "Alpha", "Home": "Beta", "Snapshot Status": "Locked", "Pregame Analysis": json.dumps(analysis)}
        rendered = AppTest.from_string(source + "render_nfl_pregame_comparison(" + repr(row) + ")").run()
        self.assertEqual(len(rendered.exception), 0)
        text = "\n".join(item.value for item in rendered.markdown)
        captions = "\n".join(item.value for item in rendered.caption)
        self.assertEqual(text.count("| Metric | Alpha | Beta |"), 2)
        self.assertIn("Net pass yards allowed/game", text)
        self.assertIn("Last 5 Game Results", text)
        self.assertIn("FBS average", captions)
        self.assertIn("Source: ESPN", captions)
        self.assertIn("Frozen pregame analysis", captions)
        self.assertNotIn("n=", text)

    def test_prior_results_opponent_defense_fbs_reference_and_missing_yards(self):
        games = pd.DataFrame([
            game("1", "2026-09-01T20:00:00Z"),
            game("2", "2026-09-08T20:00:00Z", away_class="FCS"),
            game("3", "2026-10-03T18:00:00Z"),
            game("4", "2026-09-20T20:00:00Z", completed=False),
        ])
        stats = {"1": {"1": {"passing": 100, "rushing": 50}, "2": {"passing": 200, "rushing": 150}}}
        analysis = build_analysis(games, stats, 2026, "Alpha", "Beta", "2026-10-03T19:00:00Z")
        self.assertEqual(analysis["teams"]["Alpha"]["games"], 2)
        self.assertEqual(analysis["teams"]["Alpha"]["passing"], 100)
        self.assertEqual(analysis["teams"]["Alpha"]["passing_allowed"], 200)
        self.assertEqual(analysis["league"]["games"], 3)
        self.assertAlmostEqual(analysis["league"]["points"], 26.67)
        self.assertEqual(analysis["teams"]["Alpha"]["last_five"][0]["date"], "2026-09-08")
        self.assertEqual(analysis["teams"]["Alpha"]["last_five"][0]["result"], "L")
        self.assertEqual(analysis["teams"]["Beta"]["last_five"][0]["points"], 30)
        json.dumps(analysis, allow_nan=False)

    @patch("cfb_pregame_analysis.load_game_stats")
    @patch("cfb_pregame_analysis.load_analysis_season")
    def test_captures_only_before_kickoff(self, load_season, load_stats):
        load_season.return_value = pd.DataFrame([game("1", "2026-09-01T20:00:00Z")])
        load_stats.return_value = {}
        slate = pd.DataFrame({
            "Season": [2026, 2026], "Away": ["Alpha", "Alpha"], "Home": ["Beta", "Beta"],
            "Scheduled Kickoff": ["2026-10-03T20:00:00Z", "2026-10-03T18:00:00Z"],
            "Status": ["Scheduled", "In Progress"],
        })
        result = attach_pregame_analysis(slate, datetime(2026, 10, 3, 19, tzinfo=timezone.utc))
        self.assertIsInstance(result.loc[0, "Pregame Analysis"], str)
        self.assertIsNone(result.loc[1, "Pregame Analysis"])
        self.assertIsNone(json.loads(result.loc[0, "Pregame Analysis"])["teams"]["Alpha"]["passing"])
        load_stats.assert_called_once_with("1")

    def test_preserves_saved_comparison_on_outage_and_after_lock(self):
        with sqlite3.connect(":memory:") as connection:
            init_db(connection)
            values = prediction_values({"Game ID": "1", "Game": "Alpha @ Beta", "Pregame Analysis": '{"saved":true}'},
                                       "Full Game", MARKETS["Full Game"], "2026-10-03", "test", "test", "now")
            insert_prediction(connection, values)
            missing = dict(values, pregame_analysis=None)
            update_open_prediction(connection, 1, missing)
            self.assertEqual(connection.execute("SELECT pregame_analysis FROM cfb_model_history").fetchone()[0], '{"saved":true}')
            connection.execute("UPDATE cfb_model_history SET snapshot_status = 'Locked'")
            update_open_prediction(connection, 1, dict(values, pregame_analysis='{"changed":true}'))
            self.assertEqual(connection.execute("SELECT pregame_analysis FROM cfb_model_history").fetchone()[0], '{"saved":true}')


if __name__ == "__main__":
    unittest.main()
