import ast
from html import escape
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import requests

from cbb_game_history import attach_cbb_game_history, fetch_cbb_team_schedule, recent_team_results


def event(identifier, day, own_score=80, opponent_score=70, completed=True, neutral=False):
    return {"id": identifier, "date": f"2026-11-{day:02}T23:00:00Z", "competitions": [{
        "neutralSite": neutral, "status": {"type": {"completed": completed}},
        "competitors": [
            {"team": {"id": "1"}, "homeAway": "away", "score": {"value": own_score}},
            {"team": {"id": "2", "abbreviation": "OPP"}, "homeAway": "home", "score": str(opponent_score)},
        ],
    }]}


class CbbGameHistoryTests(unittest.TestCase):
    def test_last_five_are_newest_first_and_exclude_current_future_live(self):
        events = [event(str(day), day) for day in range(1, 9)]
        events += [event("live", 9, completed=False), event("current", 9), event("future", 12)]
        events += [event("8", 8)]
        results = recent_team_results(events, "1", "Team", "2026-11-10T23:00:00Z", "current")
        self.assertEqual([r["Date"] for r in results], ["11/08", "11/07", "11/06", "11/05", "11/04"])
        self.assertEqual(results[0]["Opponent"], "@ OPP")
        self.assertEqual(results[0]["Score"], "80-70")
        self.assertEqual(results[0]["Result"], "W")

    def test_partial_history_loss_neutral_and_home_perspective(self):
        events = [event("1", 1, 60, 75, neutral=True)]
        away = recent_team_results(events, "1", "Away", "2026-11-10T23:00Z", "target")
        home = recent_team_results(events, "2", "Home", "2026-11-10T23:00Z", "target")
        self.assertEqual(len(away), 1)
        self.assertEqual(away[0]["Result"], "L")
        self.assertEqual(away[0]["Opponent"], "vs (N) OPP")
        self.assertEqual(home[0]["Score"], "75-60")
        self.assertEqual(home[0]["Result"], "W")

    def test_missing_scores_are_not_fabricated(self):
        self.assertEqual(recent_team_results([event("1", 1, None)], "1", "Team", "2026-11-10T23:00Z", "target"), [])

    def test_opponent_uses_school_name_like_cfb_instead_of_abbreviation(self):
        game = event("1", 1)
        game["competitions"][0]["competitors"][1]["team"].update(
            location="Bowling Green", shortDisplayName="Bowling Green",
            displayName="Bowling Green Falcons", abbreviation="BGSU",
        )
        results = recent_team_results([game], "1", "Team", "2026-11-10T23:00Z", "target")
        self.assertEqual(results[0]["Opponent"], "@ Bowling Green")

    def test_shared_cfb_table_format_for_both_teams(self):
        tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "render_last_five_results")
        namespace = {"escape": escape, "get_row_value": lambda row, key, default: row.get(key, default)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
        game = event("1", 1)
        row = {
            "Away Last 5 Results": recent_team_results([game], "1", "Away Team", "2026-11-10T23:00Z", "target"),
            "Home Last 5 Results": recent_team_results([game], "2", "Home Team", "2026-11-10T23:00Z", "target"),
        }
        html = namespace["render_last_five_results"](row)
        self.assertEqual(html.count('<table class="last-five-table">'), 2)
        self.assertEqual(html.count('<th>Date</th><th>Opponent</th><th>Result</th><th>Score</th>'), 2)
        self.assertIn('class="result-badge result-win">W', html)
        self.assertIn('class="result-badge result-loss">L', html)
        self.assertIn('80-70', html)
        self.assertIn('70-80', html)

    def test_attach_uses_ending_year_and_keeps_picks_unchanged(self):
        slate = pd.DataFrame([{"Game ID": "target", "Sort Date": "2026-11-10T23:00Z",
                               "Away": "Away", "Home": "Home", "Side Edge": "Away"}])
        metadata = pd.DataFrame([{"game_id": "target", "away_team_id": "1", "home_team_id": "2"}])
        loader = Mock(return_value=[event("1", 1)])
        result = attach_cbb_game_history(slate, metadata, loader)
        self.assertEqual(loader.call_args_list[0].args, ("1", 2027))
        self.assertEqual(result.iloc[0]["Side Edge"], "Away")
        self.assertEqual(len(result.iloc[0]["Away Last 5 Results"]), 1)
        self.assertNotIn("Away Last 5 Results", slate)
        unavailable = attach_cbb_game_history(slate, metadata, Mock(side_effect=requests.HTTPError("offline")))
        self.assertEqual(unavailable.iloc[0]["Away Last 5 Results"], [])

    @patch("cbb_game_history.requests.get")
    def test_wrong_season_rejected(self, get):
        get.return_value = Mock()
        get.return_value.json.return_value = {"season": {"year": 2026}, "events": []}
        with self.assertRaisesRegex(ValueError, "different season"):
            fetch_cbb_team_schedule("1", 2027)


if __name__ == "__main__":
    unittest.main()
