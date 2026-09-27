import unittest
import ast
import json
from pathlib import Path

import pandas as pd

from nfl_pregame_analysis import build_analysis, attach_pregame_analysis


class PregameAnalysisTests(unittest.TestCase):
    def fixture(self):
        games, stats = [], []
        for i in range(6):
            games.append({"game_id": str(i), "season": 2026, "game_type": "REG",
                          "gameday": f"2026-09-{i + 1:02d}", "gametime": "13:00",
                          "away_team": "IND", "home_team": "KC", "away_score": 10, "home_score": 20})
            for team, passing, rushing in (("IND", 100, 50), ("KC", 300, 150)):
                stats.append({"game_id": str(i), "team": team, "season": 2026,
                              "season_type": "REG", "passing_yards": passing, "rushing_yards": rushing})
        return pd.DataFrame(games), pd.DataFrame(stats)

    def test_offense_defense_league_and_last_five(self):
        games, stats = self.fixture()
        result = build_analysis(games, stats, 2026, "IND", "KC", "2026-09-20T12:00Z")
        self.assertEqual(result["teams"]["KC"]["passing"], 300)
        self.assertEqual(result["teams"]["KC"]["passing_allowed"], 100)
        self.assertEqual(result["league"]["passing"], 200)
        self.assertEqual(result["league"]["points"], 15)
        self.assertEqual(result["league"]["games"], 12)
        self.assertEqual(len(result["teams"]["KC"]["last_five"]), 5)
        self.assertEqual(result["teams"]["KC"]["last_five"][0]["date"], "2026-09-06")

    def test_future_and_prior_season_excluded(self):
        games, stats = self.fixture()
        games.loc[5, "gameday"] = "2026-09-21"
        games.loc[4, "season"] = 2025
        result = build_analysis(games, stats, 2026, "IND", "KC", "2026-09-20T12:00Z")
        self.assertEqual(result["teams"]["KC"]["games"], 4)

    def test_missing_yardage_not_zero(self):
        games, stats = self.fixture()
        stats = stats[stats.team != "IND"]
        result = build_analysis(games, stats, 2026, "IND", "KC", "2026-09-20T12:00Z")
        self.assertIsNone(result["teams"]["IND"]["passing"])
        self.assertIsNone(result["teams"]["KC"]["passing_allowed"])
        self.assertEqual(result["teams"]["IND"]["points"], 10)
        self.assertEqual(result["league"]["passing_games"], 6)

    def test_no_analysis_created_after_kickoff(self):
        games, stats = self.fixture()
        slate = pd.DataFrame([{"Season": 2026, "Away": "IND", "Home": "KC", "Status": "Scheduled",
                               "Scheduled Kickoff": "2026-09-20T17:00Z"}])
        pregame = attach_pregame_analysis(slate, games, stats, now="2026-09-20T16:00Z")
        self.assertIsInstance(pregame.iloc[0]["Pregame Analysis"], str)
        started = attach_pregame_analysis(slate, games, stats, now="2026-09-20T17:00Z")
        self.assertIsNone(started.iloc[0]["Pregame Analysis"])

    def test_streamlit_comparison_renders(self):
        from streamlit.testing.v1 import AppTest
        games, stats = self.fixture()
        analysis = build_analysis(games, stats, 2026, "IND", "KC", "2026-09-20T12:00Z")
        tree = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8-sig"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "render_nfl_pregame_comparison")
        source = "import streamlit as st\nimport json\nformat_snapshot_time = str\n" + ast.unparse(function)
        row = {"Away": "IND", "Home": "KC", "Snapshot Status": "Locked", "Pregame Analysis": json.dumps(analysis)}
        rendered = AppTest.from_string(source + "\nrender_nfl_pregame_comparison(" + repr(row) + ")").run()
        self.assertEqual(len(rendered.exception), 0)
        text = "\n".join(item.value for item in rendered.markdown)
        self.assertIn("Pass yards allowed/game", text)
        self.assertIn("300.0 (+100.0)", text)
        self.assertIn("Last Five Games", text)
        self.assertIn("Frozen pregame analysis", "\n".join(item.value for item in rendered.caption))
        missing = AppTest.from_string(source + "\nrender_nfl_pregame_comparison({})").run()
        self.assertEqual(len(missing.exception), 0)
        self.assertIn("unavailable", missing.caption[0].value)


if __name__ == "__main__":
    unittest.main()
