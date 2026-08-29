import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from cfb_agent import TeamState, build_current_slate, build_preseason_priors
from cfb_model_history import MARKETS, connect, init_db, prediction_values


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
