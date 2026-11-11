import ast
from pathlib import Path
import unittest

import pandas as pd


class GameCardTitleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "game_card_title")
        namespace = {"pd": pd}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
        cls.format_title = staticmethod(namespace["game_card_title"])

    def row(self, **values):
        return {"Sport": "CBB", "Game": "Away @ Home", "Away": "Away", "Home": "Home", **values}

    def test_ranked_teams_show_rank_without_mutating_matchup(self):
        row = self.row(**{"Away Rank": 2.0, "Home Rank": "25"})
        self.assertEqual(self.format_title(row), "#2 Away @ #25 Home")
        self.assertEqual(row["Game"], "Away @ Home")

    def test_either_team_can_be_ranked(self):
        self.assertEqual(self.format_title(self.row(**{"Home Rank": 7})), "Away @ #7 Home")
        self.assertEqual(self.format_title(self.row(**{"Away Rank": 1})), "#1 Away @ Home")

    def test_unranked_and_invalid_values_are_not_displayed(self):
        for rank in (None, float("nan"), pd.NA, "", "unranked", 0, 26, 99, 1.5, float("inf")):
            with self.subTest(rank=rank):
                self.assertEqual(self.format_title(self.row(**{"Away Rank": rank})), "Away @ Home")

    def test_other_sports_and_missing_names_preserve_original(self):
        self.assertEqual(self.format_title(self.row(Sport="CFB", **{"Away Rank": 2})), "Away @ Home")
        self.assertEqual(self.format_title({"Sport": "CBB", "Game": "Original"}), "Original")


if __name__ == "__main__":
    unittest.main()
