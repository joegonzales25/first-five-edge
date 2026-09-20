import unittest
from datetime import date
from unittest.mock import Mock, patch

import requests

from wnba_data import fetch_wnba_scoreboard


def response(status=200, events=None):
    result = Mock(status_code=status)
    result.json.return_value = {"events": events if events is not None else []}
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(str(status), response=result)
    return result


class WnbaScoreboardTests(unittest.TestCase):
    @patch("wnba_data.requests.get")
    def test_weekly_ranges_and_deduplication(self, get):
        get.return_value = response(events=[{"id": "1"}])
        data = fetch_wnba_scoreboard(date(2026, 9, 1), date(2026, 9, 16), limit=123)
        self.assertEqual([c.kwargs["params"]["dates"] for c in get.call_args_list],
                         ["20260901-20260908", "20260908-20260915", "20260915-20260916"])
        self.assertTrue(all(c.kwargs["params"]["limit"] == 123 for c in get.call_args_list))
        self.assertEqual(data, {"events": [{"id": "1"}]})

    @patch("wnba_data.requests.get")
    def test_daily_fallback_on_400(self, get):
        get.side_effect = [response(400), response(events=[{"id": "1"}]), response(events=[{"id": "2"}])]
        data = fetch_wnba_scoreboard(date(2026, 9, 1), date(2026, 9, 2))
        self.assertEqual([c.kwargs["params"]["dates"] for c in get.call_args_list],
                         ["20260901-20260902", "20260901", "20260902"])
        self.assertEqual(len(data["events"]), 2)

    @patch("wnba_data.requests.get")
    def test_failed_daily_request_propagates(self, get):
        get.side_effect = [response(400), response(), response(400)]
        with self.assertRaises(requests.HTTPError):
            fetch_wnba_scoreboard(date(2026, 9, 1), date(2026, 9, 2))

    @patch("wnba_data.requests.get")
    def test_server_error_is_not_treated_as_bad_range(self, get):
        get.return_value = response(503)
        with self.assertRaises(requests.HTTPError):
            fetch_wnba_scoreboard(date(2026, 9, 1), date(2026, 9, 2))
        self.assertEqual(get.call_count, 1)

    @patch("wnba_data.requests.get")
    def test_single_date_and_empty_events(self, get):
        get.return_value = response()
        self.assertEqual(fetch_wnba_scoreboard(date(2026, 9, 1), date(2026, 9, 1)), {"events": []})
        self.assertEqual(get.call_args.kwargs["params"]["dates"], "20260901")

    @patch("wnba_data.requests.get")
    def test_malformed_payload_fails(self, get):
        get.return_value = response()
        get.return_value.json.return_value = {}
        with self.assertRaises(ValueError):
            fetch_wnba_scoreboard(date(2026, 9, 1), date(2026, 9, 2))


if __name__ == "__main__":
    unittest.main()
