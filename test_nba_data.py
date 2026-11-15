import unittest
from datetime import date
from unittest.mock import patch

import requests

from nba_data import fetch_nba_scoreboard
from test_wnba_data import response


class NbaScoreboardTests(unittest.TestCase):
    @patch("nba_data.requests.get")
    def test_weekly_ranges_and_deduplication(self, get):
        get.return_value = response(events=[{"id": "1"}])
        data = fetch_nba_scoreboard(date(2026, 10, 1), date(2026, 11, 15), limit=123)
        dates = [c.kwargs["params"]["dates"] for c in get.call_args_list]
        self.assertEqual(dates, ["20261001-20261008", "20261008-20261015",
                                 "20261015-20261022", "20261022-20261029",
                                 "20261029-20261105", "20261105-20261112",
                                 "20261112-20261115"])
        self.assertTrue(all(c.kwargs["params"]["limit"] == 123 for c in get.call_args_list))
        self.assertEqual(data, {"events": [{"id": "1"}]})

    @patch("nba_data.requests.get")
    def test_daily_fallback_on_400(self, get):
        get.side_effect = [response(400), response(events=[{"id": "1"}]),
                           response(events=[{"id": "2"}])]
        data = fetch_nba_scoreboard(date(2026, 11, 14), date(2026, 11, 15))
        self.assertEqual([c.kwargs["params"]["dates"] for c in get.call_args_list],
                         ["20261114-20261115", "20261114", "20261115"])
        self.assertEqual(len(data["events"]), 2)

    @patch("nba_data.requests.get")
    def test_failed_daily_request_propagates(self, get):
        get.side_effect = [response(400), response(), response(400)]
        with self.assertRaises(requests.HTTPError):
            fetch_nba_scoreboard(date(2026, 11, 14), date(2026, 11, 15))

    @patch("nba_data.requests.get")
    def test_other_http_errors_propagate(self, get):
        for status in [401, 429, 503]:
            get.reset_mock()
            get.return_value = response(status)
            with self.assertRaises(requests.HTTPError):
                fetch_nba_scoreboard(date(2026, 11, 14), date(2026, 11, 15))
            self.assertEqual(get.call_count, 1)

    @patch("nba_data.requests.get")
    def test_single_day_empty_response(self, get):
        get.return_value = response()
        self.assertEqual(fetch_nba_scoreboard(date(2026, 11, 15), date(2026, 11, 15)),
                         {"events": []})
        self.assertEqual(get.call_args.kwargs["params"]["dates"], "20261115")

    @patch("nba_data.requests.get")
    def test_malformed_payload_and_missing_id_fail(self, get):
        for payload in [{}, {"events": None}, {"events": [{}]}]:
            get.return_value = response()
            get.return_value.json.return_value = payload
            with self.assertRaises(ValueError):
                fetch_nba_scoreboard(date(2026, 11, 15), date(2026, 11, 15))


if __name__ == "__main__":
    unittest.main()
