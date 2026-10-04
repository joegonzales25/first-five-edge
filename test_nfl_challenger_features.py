import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from nfl_challenger import CORE_FEATURES, evaluate_challenger
from nfl_challenger_features import (
    FEATURE_SOURCE, FEATURE_VERSION, build_feature_frame,
    load_play_by_play, valid_plays,
)
from nfl_schedule_store import (
    feature_rows_to_frame, load_latest_nfl_features, record_nfl_pregame_features,
)


class ChallengerFeatureTests(unittest.TestCase):
    def fixtures(self):
        schedule, plays = [], []
        for week, day in ((1, "2026-09-13"), (2, "2026-09-20")):
            for team in ("HME", "AWY"):
                game_id = f"2026_{week:02}_{team}_OPP"
                schedule.append(dict(game_id=game_id, season=2026, game_type="REG",
                                     gameday=day, gametime="13:00", away_team=team,
                                     home_team="OPP", away_score=21, home_score=14))
                for offense in (True, False):
                    for index in range(60):
                        advantage = (team == "HME") == offense
                        plays.append(dict(
                            game_id=game_id, play_id=index + (0 if offense else 60),
                            season=2026, season_type="REG", posteam=team if offense else "OPP",
                            defteam="OPP" if offense else team, play_type="pass",
                            down=1 if index < 40 else 3, epa=0.2 if advantage else -0.1,
                            qb_epa=0.3 if advantage else -0.1, qb_dropback=1,
                            sack=int(not advantage and index < 6),
                            yards_gained=25 if advantage and index < 12 else 5,
                            pass_attempt=1, rush_attempt=0, qb_kneel=0, qb_spike=0,
                        ))
        schedule.append(dict(game_id="target", season=2026, game_type="REG",
                             gameday="2026-09-27", gametime="13:00", away_team="AWY",
                             home_team="HME", away_score=None, home_score=None,
                             location="Home", away_rest=7, home_rest=8))
        return pd.DataFrame(schedule), pd.DataFrame(plays)

    def test_home_advantage_orientation_and_pregame_timestamp(self):
        games, plays = self.fixtures()
        row = build_feature_frame(games, plays, "2026-09-27T12:00:00Z").iloc[0]
        self.assertAlmostEqual(row.net_epa_diff, 0.6)
        self.assertAlmostEqual(row.early_down_success_diff, 2)
        self.assertAlmostEqual(row.qb_epa_diff, 0.4)
        self.assertAlmostEqual(row.sack_rate_diff, 0.1)
        self.assertAlmostEqual(row.explosive_play_diff, 0.4)
        self.assertEqual(row.home_field, 1.8)
        self.assertAlmostEqual(row.rest_adjustment, 0.15)
        self.assertLess(pd.Timestamp(row.as_of), pd.Timestamp("2026-09-27T17:00:00Z"))

    def test_started_and_far_future_targets_not_collected(self):
        games, plays = self.fixtures()
        self.assertTrue(build_feature_frame(games, plays, "2026-09-27T17:00:00Z").empty)
        self.assertTrue(build_feature_frame(games, plays, "2026-09-01T12:00:00Z").empty)

    def test_live_recent_and_postseason_history_not_used(self):
        games, plays = self.fixtures()
        for mode in ("live", "recent", "postseason"):
            changed = games.copy()
            selection = changed.game_id.str.contains("2026_02")
            if mode == "live":
                changed.loc[selection, "home_score"] = None
            elif mode == "recent":
                changed.loc[selection, "gameday"] = "2026-09-27"
                changed.loc[selection, "gametime"] = "05:00"
            else:
                changed.loc[selection, "game_type"] = "POST"
            row = build_feature_frame(changed, plays, "2026-09-27T12:00:00Z").iloc[0]
            self.assertTrue(row[list(CORE_FEATURES)].isna().all(), mode)

    def test_missing_qb_metric_stays_missing(self):
        games, plays = self.fixtures()
        plays.loc[plays.posteam.eq("HME"), "qb_epa"] = float("inf")
        row = build_feature_frame(games, plays, "2026-09-27T12:00:00Z").iloc[0]
        self.assertIsNone(row.qb_epa_diff)
        self.assertEqual(row[list(CORE_FEATURES)].notna().sum(), 4)
        self.assertEqual(evaluate_challenger({}, row.to_dict())["status"], "Awaiting features")

    def test_invalid_plays_and_missing_explosive_flags(self):
        _, plays = self.fixtures()
        plays.loc[0, "qb_kneel"] = 1
        plays.loc[1, "qb_spike"] = 1
        plays.loc[2, "play_type"] = "no_play"
        plays.loc[3, "season_type"] = "POST"
        plays.loc[4, ["pass_attempt", "rush_attempt"]] = None
        valid = valid_plays(plays)
        self.assertEqual(len(valid), len(plays) - 4)
        self.assertTrue(pd.isna(valid.loc[4, "explosive"]))

    def test_latest_five_only(self):
        games, plays = self.fixtures()
        old = games.iloc[:2].copy()
        old["game_id"] = ["old_home", "old_away"]
        old["gameday"] = "2026-08-01"
        old_plays = plays.iloc[:240].copy()
        old_plays["game_id"] = old_plays.game_id.map(dict(zip(games.game_id.iloc[:2], old.game_id)))
        old_plays["epa"] = 100
        extra_games, extra_plays = [], []
        for index, day in enumerate(("2026-08-23", "2026-08-30", "2026-09-06")):
            copy_games = games.iloc[:2].copy()
            ids = [f"extra_{index}_home", f"extra_{index}_away"]
            copy_games["game_id"], copy_games["gameday"] = ids, day
            copy_plays = plays.iloc[:240].copy()
            copy_plays["game_id"] = copy_plays.game_id.map(dict(zip(games.game_id.iloc[:2], ids)))
            extra_games.append(copy_games)
            extra_plays.append(copy_plays)
        result = build_feature_frame(pd.concat([games, old] + extra_games),
                                     pd.concat([plays, old_plays] + extra_plays), "2026-09-27T12:00:00Z")
        self.assertAlmostEqual(result.iloc[0].net_epa_diff, 0.6)

    def test_store_round_trip_preserves_source_and_features(self):
        games, plays = self.fixtures()
        frame = build_feature_frame(games, plays, "2026-09-27T12:00:00Z")
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"HISTORY_BACKEND": "sqlite"}):
            path = Path(directory) / "history.sqlite3"
            record_nfl_pregame_features(frame, feature_version=FEATURE_VERSION,
                                       source=FEATURE_SOURCE, db_path=path)
            rows = load_latest_nfl_features(["target"], db_path=path)
            # SQLite context managers commit but leave handles for GC on Windows.
            gc.collect()
        self.assertEqual(rows[0]["source"], FEATURE_SOURCE)
        self.assertEqual(rows[0]["feature_version"], FEATURE_VERSION)
        restored = feature_rows_to_frame(rows).iloc[0]
        for feature in CORE_FEATURES:
            self.assertAlmostEqual(restored[feature], frame.iloc[0][feature])
        result = evaluate_challenger({"Home": "HME", "Away": "AWY"}, restored.to_dict())
        self.assertEqual(result["status"], "Tracked")
        self.assertEqual(result["scoring_edge"], "Neutral Scoring Environment")

    def test_collection_failure_does_not_stop_snapshot(self):
        import snapshot_nfl_slate as snapshot
        from argparse import Namespace
        games, _ = self.fixtures()
        args = Namespace(date="2026-09-27", challenger_features=None,
                         lookback_days=3, lookahead_days=8)
        with patch.object(snapshot, "parse_args", return_value=args), \
                patch.object(snapshot, "load_nfl_schedule", return_value=games), \
                patch.object(snapshot, "sync_nfl_schedule"), \
                patch.object(snapshot, "collect_feature_frame", side_effect=ValueError("bad feed")), \
                patch.object(snapshot, "load_latest_nfl_features", return_value=[]) as stored, \
                patch.object(snapshot, "target_weeks", return_value=[]):
            self.assertEqual(snapshot.main(), 0)
            stored.assert_called_once()

    def test_loader_rejects_missing_columns(self):
        import gzip
        from unittest.mock import Mock
        response = Mock(content=gzip.compress(b"game_id,season\ntarget,2026\n"))
        with patch("nfl_challenger_features.requests.get", return_value=response):
            with self.assertRaisesRegex(ValueError, "missing columns"):
                load_play_by_play(2026)


if __name__ == "__main__":
    unittest.main()
