import json
import ast
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from cfb_agent import MODEL_VERSION, TeamState, build_current_slate, build_preseason_priors
from cfb_model_history import MARKETS, connect, init_db, prediction_values, record_cfb_history


def prior_games(count=6):
    rows = []
    for index in range(count):
        rows.append(
            {
                "game_id": f"prior-{index}",
                "season": 2025,
                "game_date_dt": pd.Timestamp(
                    f"2025-09-{index + 1:02d}T16:00:00Z"
                ),
                "away_team_id": "1",
                "home_team_id": "2",
                "away_team": "Alpha",
                "home_team": "Beta",
                "away_score": 45,
                "home_score": 10,
                "neutral_site": True,
                "completed": True,
            }
        )
    return pd.DataFrame(rows)


def current_game():
    return pd.DataFrame(
        [
            {
                "game_id": "current-1",
                "season": 2026,
                "week": 1,
                "game_date_dt": pd.Timestamp("2026-08-29T20:00:00Z"),
                "away_team_id": "1",
                "home_team_id": "2",
                "away_team": "Alpha",
                "home_team": "Beta",
                "away_classification": "FBS",
                "home_classification": "FBS",
                "away_score": None,
                "home_score": None,
                "away_first_half": None,
                "home_first_half": None,
                "neutral_site": True,
                "completed": False,
                "status": "Scheduled",
                "source": "ESPN",
            }
        ]
    )


class CfbAgentTests(unittest.TestCase):
    def policy_slate(self, margin=16, games=3, prior=6, classification="FBS"):
        frame = current_game()
        frame.loc[0, "home_classification"] = classification
        away = TeamState(preseason_rating=1500 + margin * 25, current_rating=1500 + margin * 25,
                         prior_games=prior, games=games, preseason_offense=60, preseason_defense=10,
                         points_for=[60] * games, points_against=[10] * games)
        home = TeamState(prior_games=prior, games=games, preseason_offense=40, preseason_defense=20,
                         points_for=[40] * games, points_against=[20] * games)
        with patch("cfb_agent.load_cfb_season", return_value=frame), \
                patch("cfb_agent.load_cfb_prior_season", return_value=prior_games()), \
                patch("cfb_agent.team_state", side_effect=[away, home]):
            return build_current_slate(season=2026, slate_date=date(2026, 8, 29))[0]

    def test_availability_warning_does_not_cap_qualified_sides_or_scoring(self):
        for margin, tier, confidence in [(16, "Official", "A"), (10, "Official", "B"),
                                         (7, "Lean", "B"), (4, "Watch", "C"), (3, "Pass", "Pass")]:
            with self.subTest(margin=margin):
                row = self.policy_slate(margin).iloc[0]
                self.assertEqual(row["Side Tracking Segment"], tier)
                self.assertEqual(row["Side Confidence"], confidence)
                self.assertEqual(row["Scoring Tracking Segment"], "Lean")
                self.assertIn("Availability unverified", row["Downgrade Reasons"])
                self.assertEqual(row["Availability Status"], "Unverified")
                self.assertEqual(row["Data Quality"], "Limited")
                self.assertEqual(row["Model Margin"], -margin)
                self.assertEqual(row["Projected Total"], 62.14)
                self.assertIn(row["First Half Tracking Segment"], ["Watch", "Pass"])

    def test_other_watch_caps_are_retained(self):
        for overrides, reason in [({"classification": "FCS"}, "FBS-vs-FCS matchup"),
                                  ({"games": 2}, "Limited current-season team history"),
                                  ({"prior": 5}, "Insufficient preseason history")]:
            with self.subTest(overrides=overrides):
                row = self.policy_slate(**overrides).iloc[0]
                self.assertEqual(row["Side Tracking Segment"], "Watch")
                self.assertEqual(row["Scoring Tracking Segment"], "Watch")
                self.assertEqual(row["First Half Tracking Segment"], "Watch")
                self.assertIn(reason, row["Downgrade Reasons"])

    def test_new_policy_version_does_not_relabel_existing_snapshots(self):
        slate = self.policy_slate()
        old = slate.copy(deep=True)
        old["Side Tracking Segment"] = "Watch"
        old["Side Confidence"] = "C"
        old["Scoring Tracking Segment"] = "Watch"
        old["Scoring Confidence"] = "C"
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            with patch("cfb_model_history.connect", return_value=connection), \
                    patch("cfb_model_history.datetime") as clock:
                clock.now.return_value = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
                record_cfb_history(old, "2026-08-29", "market", "0.2.0-test")
                before = [dict(r) for r in connection.execute("SELECT * FROM cfb_model_history ORDER BY id")]
                record_cfb_history(slate, "2026-08-29", "market", MODEL_VERSION)
                after = [dict(r) for r in connection.execute("SELECT * FROM cfb_model_history ORDER BY id")]
            self.assertEqual(after[:3], before)
            self.assertEqual(len(after), 6)
            self.assertEqual(after[3]["decision_tier"], "Official")
            self.assertEqual(after[3]["model_version"], MODEL_VERSION)
        finally:
            connection.close()

    def test_snapshot_and_gui_use_the_new_policy_version(self):
        from snapshot_cfb_slate import DEFAULT_MODEL_VERSION
        self.assertEqual(DEFAULT_MODEL_VERSION, MODEL_VERSION)
        tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
        assignment = next(n for n in tree.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == "MODEL_BASELINES" for t in n.targets))
        pairs = zip(assignment.value.keys, assignment.value.values)
        value = next(value for key, value in pairs if key.value == "CFB")
        self.assertEqual(value.id, "CFB_MODEL_VERSION")
        notice = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "cfb_availability_notice")
        namespace = {}
        exec(compile(ast.Module(body=[notice], type_ignores=[]), "app.py", "exec"), namespace)
        self.assertIn("Availability unverified", namespace["cfb_availability_notice"](
            {"Sport": "CFB", "Downgrade Reasons": "Availability unverified"}))
        self.assertEqual(namespace["cfb_availability_notice"]({"Sport": "CBB"}), "")

    def test_prior_influence_decays_through_six_games(self):
        state = TeamState(prior_games=10)
        expected = [1.0, 5 / 6, 4 / 6, 0.5, 2 / 6, 1 / 6, 0.0]

        for games, influence in enumerate(expected):
            state.games = games
            self.assertAlmostEqual(state.prior_influence(), influence)

    def test_requires_six_prior_games(self):
        self.assertEqual(build_preseason_priors(prior_games(5)), {})
        self.assertEqual(len(build_preseason_priors(prior_games(6))), 2)

    @patch("cfb_agent.load_cfb_prior_season")
    @patch("cfb_agent.load_cfb_season")
    def test_bootstrap_creates_opening_week_differentiation(
        self,
        load_season,
        load_prior,
    ):
        load_season.return_value = current_game()
        load_prior.return_value = prior_games()

        slate, _ = build_current_slate(
            season=2026,
            today=date(2026, 8, 29),
            slate_date=date(2026, 8, 29),
            days_ahead=0,
        )

        row = slate.iloc[0]
        self.assertGreater(abs(row["Model Margin"]), 4)
        self.assertEqual(row["Side Tracking Segment"], "Watch")
        self.assertEqual(row["Away Prior Influence"], 1.0)
        self.assertIn("ESPN 2025 bootstrap", row["Source"])
        self.assertTrue(
            any(
                "Prior-season regressed ratings" in factor
                for factor in row["Key Factors List"]
            )
        )

    def test_history_schema_and_prediction_preserve_key_factors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "cfb.sqlite3"
            with patch.dict("os.environ", {"HISTORY_BACKEND": "sqlite"}):
                connection = connect(db_path)
                try:
                    init_db(connection)
                    columns = {
                        row["name"]
                        for row in connection.execute(
                            "PRAGMA table_info(cfb_model_history)"
                        ).fetchall()
                    }
                finally:
                    connection.close()

        values = prediction_values(
            {
                "Game ID": "current-1",
                "Game": "Alpha @ Beta",
                "Key Factors List": ["Prior-season factor"],
            },
            "Full Game",
            MARKETS["Full Game"],
            "2026-08-29",
            "0.1.0-test",
            "0.2.0-test",
            "2026-08-29T12:00:00+00:00",
        )

        self.assertIn("key_factors", columns)
        self.assertEqual(
            json.loads(values["key_factors"]),
            ["Prior-season factor"],
        )

    @patch("cfb_agent.load_cfb_prior_season")
    @patch("cfb_agent.load_cfb_season")
    def test_future_results_do_not_change_target_date_prediction(
        self,
        load_season,
        load_prior,
    ):
        load_prior.return_value = prior_games()
        baseline_games = current_game()
        load_season.return_value = baseline_games
        baseline, _ = build_current_slate(
            season=2026,
            slate_date=date(2026, 8, 29),
        )

        future = baseline_games.iloc[0].copy()
        future["game_id"] = "future-1"
        future["game_date_dt"] = pd.Timestamp("2026-08-30T20:00:00Z")
        future["away_score"] = 0
        future["home_score"] = 100
        future["completed"] = True
        future["status"] = "Final"
        load_season.return_value = pd.concat(
            [baseline_games, pd.DataFrame([future])],
            ignore_index=True,
        )
        with_future, _ = build_current_slate(
            season=2026,
            slate_date=date(2026, 8, 29),
        )

        self.assertEqual(
            baseline.iloc[0]["Model Margin"],
            with_future.iloc[0]["Model Margin"],
        )


if __name__ == "__main__":
    unittest.main()
