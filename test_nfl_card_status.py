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


class NflCardStatusTests(unittest.TestCase):
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
