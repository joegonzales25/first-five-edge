import unittest
from datetime import date
from unittest.mock import Mock, patch

import requests

from cfb_data import (
    fetch_espn_season,
    load_cfb_prior_season,
    load_cfb_season,
    normalize_espn_games,
    season_for_date,
)


def competitor(team_id, location, side, score=None, quarters=None):
    row = {
        "homeAway": side,
        "team": {
            "id": team_id,
            "location": location,
            "displayName": f"{location} Mascots",
        },
        "score": score,
    }
    if quarters is not None:
        row["linescores"] = [{"value": value} for value in quarters]
    return row


def event(completed=True):
    return {
        "id": "401000001",
        "date": "2026-08-29T16:00:00Z",
        "season": {"year": 2026, "type": 2, "slug": "regular-season"},
        "week": {"number": 1},
        "status": {
            "type": {
                "completed": completed,
                "description": "Final" if completed else "Scheduled",
            }
        },
        "competitions": [
            {
                "neutralSite": True,
                "conferenceCompetition": False,
                "venue": {"fullName": "Example Stadium"},
                "competitors": [
                    competitor("2", "FCS State", "away", "10", [3, 7, 0, 0]),
                    competitor("1", "FBS Tech", "home", "24", [7, 10, 7, 0]),
                ],
            }
        ],
    }


class CfbDataTests(unittest.TestCase):
    def test_normalizes_espn_schedule_and_grading_fields(self):
        games = normalize_espn_games(
            [event()],
            {"1": "Example Conference"},
        )

        self.assertEqual(len(games), 1)
        row = games.iloc[0]
        self.assertEqual(row["away_team"], "FCS State")
        self.assertEqual(row["home_team"], "FBS Tech")
        self.assertEqual(row["away_classification"], "FCS")
        self.assertEqual(row["home_classification"], "FBS")
        self.assertEqual(row["away_first_half"], 10)
        self.assertEqual(row["home_first_half"], 17)
        self.assertTrue(row["neutral_site"])
        self.assertEqual(row["source"], "ESPN")

    @patch("cfb_data.fetch_espn_season")
    @patch("cfb_data.fetch_espn_fbs_teams")
    def test_loads_without_cfbd_key(self, fetch_teams, fetch_season):
        fetch_teams.return_value = {"1": "Example Conference"}
        fetch_season.return_value = {"events": [event(completed=False)]}

        with patch.dict("os.environ", {}, clear=True):
            games = load_cfb_season(
                season=2026,
                today=date(2026, 8, 29),
                days_ahead=0,
            )

        self.assertEqual(len(games), 1)
        self.assertEqual(games.iloc[0]["status"], "Scheduled")
        self.assertEqual(games.iloc[0]["source"], "ESPN")
        fetch_season.assert_called_once_with(
            date(2026, 7, 1), date(2026, 8, 30)
        )

    def test_january_uses_previous_cfb_season(self):
        self.assertEqual(season_for_date(date(2027, 1, 10)), 2026)

    @patch("cfb_data.fetch_espn_season")
    @patch("cfb_data.fetch_espn_fbs_teams")
    def test_prior_loader_uses_previous_completed_season(
        self,
        fetch_teams,
        fetch_season,
    ):
        fetch_teams.return_value = {"1": "Example Conference"}
        fetch_season.return_value = {"events": [event(completed=True)]}

        games = load_cfb_prior_season(2026)

        self.assertEqual(len(games), 1)
        fetch_season.assert_called_once_with(
            date(2025, 7, 1), date(2026, 1, 31)
        )

    def test_excludes_non_playoff_postseason_games(self):
        bowl = event()
        bowl["season"] = {
            "year": 2026,
            "type": 3,
            "slug": "post-season",
        }
        bowl["competitions"][0]["notes"] = [
            {"headline": "Example Sponsor Bowl"}
        ]

        games = normalize_espn_games(
            [bowl],
            {"1": "Example Conference"},
        )

        self.assertTrue(games.empty)


class EspnRangeTests(unittest.TestCase):
    @patch("cfb_data.requests.get")
    def test_weekly_ranges_overlap_and_deduplicate(self, get):
        get.return_value = Mock(status_code=200)
        get.return_value.json.return_value = {"events": [{"id": "1"}]}
        result = fetch_espn_season(date(2026, 9, 1), date(2026, 9, 16))
        self.assertEqual([call.kwargs["params"]["dates"] for call in get.call_args_list],
                         ["20260901-20260908", "20260908-20260915", "20260915-20260916"])
        self.assertEqual(result, {"events": [{"id": "1"}]})

    @patch("cfb_data.fetch_espn_scoreboard")
    @patch("cfb_data.requests.get")
    def test_400_falls_back_to_each_date(self, get, daily):
        get.return_value = Mock(status_code=400)
        daily.side_effect = [{"events": [{"id": "1"}]}, {"events": [{"id": "2"}]}]
        result = fetch_espn_season(date(2026, 9, 1), date(2026, 9, 2))
        self.assertEqual([call.args[0] for call in daily.call_args_list],
                         [date(2026, 9, 1), date(2026, 9, 2)])
        self.assertEqual(len(result["events"]), 2)

    @patch("cfb_data.fetch_espn_scoreboard")
    @patch("cfb_data.requests.get")
    def test_daily_failure_is_not_silently_skipped(self, get, daily):
        get.return_value = Mock(status_code=400)
        daily.side_effect = requests.HTTPError("400")
        with self.assertRaises(requests.HTTPError):
            fetch_espn_season(date(2026, 9, 1), date(2026, 9, 2))

    @patch("cfb_data.requests.get")
    def test_other_http_errors_propagate(self, get):
        get.return_value = Mock(status_code=503)
        get.return_value.raise_for_status.side_effect = requests.HTTPError("503")
        with self.assertRaises(requests.HTTPError):
            fetch_espn_season(date(2026, 9, 1), date(2026, 9, 2))

    @patch("cfb_data.fetch_espn_scoreboard", return_value={"events": []})
    def test_single_day(self, daily):
        self.assertEqual(fetch_espn_season(date(2026, 9, 1), date(2026, 9, 1)), {"events": []})
        daily.assert_called_once_with(date(2026, 9, 1))


if __name__ == "__main__":
    unittest.main()
