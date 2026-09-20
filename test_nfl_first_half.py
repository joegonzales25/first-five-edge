import unittest

import pandas as pd

from nfl_first_half import normalize_events, predict, attach_first_half


class FirstHalfTests(unittest.TestCase):
    def history(self):
        return [{"away": "A", "home": "B", "away_half": 3, "home_half": 17,
                 "kickoff": pd.Timestamp("2025-09-01", tz="UTC") + pd.Timedelta(days=i * 7),
                 "completed": True, "neutral": False} for i in range(10)]

    def test_future_scores_cannot_change_prediction(self):
        history = self.history()
        kickoff = pd.Timestamp("2026-09-20", tz="UTC")
        result = predict("A", "B", kickoff, history)
        future = {**history[0], "kickoff": kickoff, "home_half": 0, "away_half": 100}
        self.assertEqual(result, predict("A", "B", kickoff, history + [future]))
        self.assertEqual(result["First Half Pick"], "B")
        self.assertEqual(result["First Half Tracking Segment"], "Watch")

    def test_insufficient_history_is_unavailable(self):
        self.assertEqual(predict("A", "B", "2026-09-20", self.history()[:7])["Early Edge"], "Not Available")

    def test_missing_quarter_is_not_zero_and_halftime_required(self):
        contest = {"status": {"period": 2, "type": {"name": "STATUS_IN_PROGRESS"}},
                   "competitors": [{"homeAway": side, "team": {"abbreviation": name},
                                    "linescores": [{"value": 0}, {"value": 7}]}
                                   for side, name in (("away", "A"), ("home", "B"))]}
        payload = {"events": [{"date": "2026-09-20T17:00Z", "competitions": [contest]}]}
        self.assertEqual(normalize_events(payload), [])
        contest["status"]["type"]["name"] = "STATUS_HALFTIME"
        self.assertEqual(normalize_events(payload)[0]["away_half"], 7)
        contest["competitors"][0]["linescores"][1]["value"] = None
        self.assertEqual(normalize_events(payload), [])

    def test_halftime_scores_attach_to_matching_game_only(self):
        history = self.history()
        slate = pd.DataFrame([{"Away": "A", "Home": "B", "Scheduled Kickoff": history[-1]["kickoff"]}])
        result = attach_first_half(slate, history).iloc[0]
        self.assertEqual(result["Away First Half"], 3)
        self.assertEqual(result["Home First Half"], 17)


if __name__ == "__main__":
    unittest.main()
