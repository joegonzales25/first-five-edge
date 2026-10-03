import ast
from pathlib import Path
import sqlite3
import unittest

import pandas as pd

from cfb_model_history import MARKETS, init_db, insert_prediction, prediction_values


class CfbTeamFilterTests(unittest.TestCase):
    def test_filters_either_team_and_excludes_unknown_ranks(self):
        tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "filter_cfb_team_scope")
        namespace = {"pd": pd}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
        games = pd.DataFrame({
            "Away Conference": ["SEC", "ACC", None, "Big Ten"],
            "Home Conference": ["Big Ten", "SEC", None, "ACC"],
            "Away Rank": [None, "25", None, 99],
            "Home Rank": [1, None, None, None],
        })
        select = namespace["filter_cfb_team_scope"]
        self.assertEqual(list(select(games, "Any Top 25 Team").index), [0, 1])
        self.assertEqual(list(select(games, "SEC").index), [0, 1])
        self.assertEqual(len(select(games, "All Teams")), 4)
        self.assertTrue(select(games.iloc[:0], "Any Top 25 Team").empty)

    def test_snapshot_persists_filter_metadata(self):
        with sqlite3.connect(":memory:") as connection:
            init_db(connection)
            init_db(connection)
            values = prediction_values({
                "Game ID": "1", "Game": "Away @ Home", "Away": "Away",
                "Home": "Home", "Away Conference": "SEC", "Home Conference": "ACC",
                "Away Rank": 7, "Home Rank": None,
            }, "Full Game", MARKETS["Full Game"], "2026-10-03", "test", "test", "now")
            insert_prediction(connection, values)
            self.assertEqual(connection.execute(
                "SELECT away_conference, home_conference, away_rank, home_rank FROM cfb_model_history"
            ).fetchone(), ("SEC", "ACC", 7, None))


if __name__ == "__main__":
    unittest.main()
