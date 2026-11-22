from datetime import date
import unittest
from unittest.mock import Mock, patch

import requests

from cbb_data import fetch_cbb_scoreboard, filter_cbb_events_by_date


class CbbScoreboardTests(unittest.TestCase):
    @patch("cbb_data.requests.get")
    def test_daily_requests_include_all_division_one_games(self, get):
        get.return_value = Mock()
        get.return_value.json.return_value = {"events": [{"id": str(i)} for i in range(42)]}
        result = fetch_cbb_scoreboard(date(2026, 11, 22), date(2026, 11, 22))
        self.assertEqual(len(result["events"]), 42)
        self.assertEqual(get.call_args.kwargs["params"],
                         {"dates": "20261122", "groups": 50, "limit": 1000})

    @patch("cbb_data.requests.get")
    def test_history_uses_each_day_across_year_boundary_and_deduplicates(self, get):
        def respond(*args, **kwargs):
            response = Mock()
            day = kwargs["params"]["dates"]
            response.json.return_value = {"events": [{"id": day}, {"id": "shared"}]}
            return response
        get.side_effect = respond
        result = fetch_cbb_scoreboard(date(2026, 12, 31), date(2027, 1, 2))
        self.assertEqual({c.kwargs["params"]["dates"] for c in get.call_args_list},
                         {"20261231", "20270101", "20270102"})
        self.assertEqual(len(result["events"]), 4)

    @patch("cbb_data.requests.get")
    def test_incomplete_responses_fail_instead_of_silently_dropping_games(self, get):
        for payload in [{}, {"events": None}, {"events": [{"id": "1"}, {"id": "2"}]}]:
            get.return_value = Mock()
            get.return_value.json.return_value = payload
            with self.assertRaises(ValueError):
                fetch_cbb_scoreboard(date(2026, 11, 22), date(2026, 11, 22), limit=2)

    @patch("cbb_data.requests.get")
    def test_history_request_error_propagates(self, get):
        get.side_effect = requests.HTTPError("unavailable")
        with self.assertRaises(requests.HTTPError):
            fetch_cbb_scoreboard(date(2026, 11, 21), date(2026, 11, 22))

    def test_eastern_date_filter_includes_evening_games(self):
        events = [{"id": "late", "date": "2026-11-23T02:00Z"},
                  {"id": "tomorrow", "date": "2026-11-23T18:00Z"}]
        result = filter_cbb_events_by_date(events, date(2026, 11, 22), date(2026, 11, 22))
        self.assertEqual([e["id"] for e in result], ["late"])


if __name__ == "__main__":
    unittest.main()
