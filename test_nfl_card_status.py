"""Exercise the UI status merge without starting the Streamlit application."""

import ast
from pathlib import Path
import unittest

import pandas as pd


tree = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8-sig"))
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name == "nfl_card_status")
namespace = {"pd": pd}
exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
card_status = namespace["nfl_card_status"]
sort_function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == "sort_nfl_game_cards")
exec(compile(ast.Module(body=[sort_function], type_ignores=[]), "app.py", "exec"), namespace)
sort_cards = namespace["sort_nfl_game_cards"]


class NflCardStatusTests(unittest.TestCase):
    def test_nba_current_uses_shared_sort_before_rendering(self):
        render = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                      and node.name == "render_nba_current")
        sorting = next(node for node in render.body if isinstance(node, ast.Assign)
                       and isinstance(node.value, ast.Call)
                       and isinstance(node.value.func, ast.Name)
                       and node.value.func.id == "sort_nfl_game_cards")
        cards = next(node for node in render.body if isinstance(node, ast.For)
                     and any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                             and call.func.id == "render_wnba_card" for call in ast.walk(node)))
        self.assertLess(sorting.lineno, cards.lineno)
        self.assertEqual(ast.unparse(sorting), "filtered = sort_nfl_game_cards(filtered)")

    def test_nba_tipoff_order_groups_upcoming_live_and_finished(self):
        games = pd.DataFrame([
            {"Game": "LAL @ BOS", "Status": "Final", "Sort Date": "2026-11-22T18:00Z"},
            {"Game": "CHI @ NY", "Status": "Halftime", "Sort Date": "2026-11-22T20:00Z"},
            {"Game": "DEN @ SAC", "Status": "Scheduled", "Sort Date": "2026-11-23T03:00Z"},
            {"Game": "MIA @ ORL", "Status": "Scheduled", "Sort Date": "2026-11-23T00:00Z"},
            {"Game": "ATL @ CLE", "Status": "Scheduled", "Sort Date": "2026-11-22T21:00Z"},
        ])
        self.assertEqual(sort_cards(games, now="2026-11-22T22:00Z").Game.tolist(),
                         ["MIA @ ORL", "DEN @ SAC", "CHI @ NY", "ATL @ CLE", "LAL @ BOS"])

    def test_upcoming_before_live_and_stale_scheduled_games(self):
        games = pd.DataFrame([
            {"Game": "Final", "Status": "Final", "Sort Date": "2026-09-24T17:00Z"},
            {"Game": "Stale scheduled", "Status": "Scheduled", "Sort Date": "2026-09-27T17:00Z"},
            {"Game": "Live", "Status": "In Progress", "Sort Date": "2026-09-27T17:00Z"},
            {"Game": "Late", "Status": "Scheduled", "Sort Date": "2026-09-28T00:20Z"},
            {"Game": "Next", "Status": "Scheduled", "Sort Date": "2026-09-27T20:05Z"},
            {"Game": "TBD", "Status": "Scheduled", "Sort Date": None},
        ])
        result = sort_cards(games, now="2026-09-27T18:00Z")
        self.assertEqual(result.Game.tolist(), ["Next", "Late", "TBD", "Live", "Stale scheduled", "Final"])
        self.assertEqual(result.loc[result.Game == "Stale scheduled", "Status"].iloc[0], "Scheduled")
        self.assertNotIn("Status Sort", games.columns)

    def test_halftime_and_exact_kickoff_move_below_upcoming(self):
        games = pd.DataFrame([
            {"Game": "Halftime", "Status": "Halftime", "Sort Date": None},
            {"Game": "Kickoff", "Status": "Pre-Game", "Sort Date": "2026-09-27T17:00Z"},
            {"Game": "Upcoming", "Status": "Scheduled", "Sort Date": "2026-09-27T20:00Z"},
        ])
        self.assertEqual(sort_cards(games, "2026-09-27T17:00Z").Game.tolist(),
                         ["Upcoming", "Kickoff", "Halftime"])

    def test_newer_snapshot_overrides_old_schedule(self):
        for status in ("In Progress", "Final", "Delayed"):
            self.assertEqual(card_status(
                {"status": "Scheduled", "updated_at": "2026-09-19T12:00:00Z"},
                {"Status": status, "Snapshot Updated At": "2026-09-20T18:00:00Z"},
            ), status)

    def test_newer_schedule_wins(self):
        self.assertEqual(card_status(
            {"status": "Postponed", "updated_at": "2026-09-20T19:00:00Z"},
            {"Status": "Scheduled", "Snapshot Updated At": "2026-09-20T18:00:00Z"},
        ), "Postponed")

    def test_missing_times_and_statuses(self):
        self.assertEqual(card_status({"status": "Scheduled"}, {"Status": "Final"}), "Final")
        self.assertEqual(card_status({}, {}), "Scheduled")
        self.assertEqual(card_status({"status": "Scheduled"}, {}), "Scheduled")


if __name__ == "__main__":
    unittest.main()
