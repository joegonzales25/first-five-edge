import ast
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from cbb_data import load_cbb_team_filter_metadata


class CbbTeamFilterTests(unittest.TestCase):
    @patch("cbb_data.fetch_cbb_scoreboard")
    @patch("cbb_data.requests.get")
    def test_conferences_and_either_team_rank(self, get, scoreboard):
        get.return_value = Mock()
        get.return_value.json.return_value = {"sports": [{"leagues": [{"groups": [
            {"name": "ACC", "teams": [{"id": "1"}]},
            {"name": "Big Ten", "teams": [{"id": "2"}]},
        ]}]}]}
        scoreboard.return_value = {"events": [{"id": "game", "competitions": [{"competitors": [
            {"homeAway": "away", "team": {"id": "1"}, "curatedRank": {"current": 25}},
            {"homeAway": "home", "team": {"id": "2"}, "curatedRank": {"current": 99}},
        ]}]}]}
        frame, conferences = load_cbb_team_filter_metadata(date(2026, 11, 10))
        self.assertEqual(conferences, ["ACC", "Big Ten"])
        self.assertEqual(frame.iloc[0].away_conference, "ACC")
        self.assertEqual(frame.iloc[0].home_conference, "Big Ten")
        self.assertEqual(frame.iloc[0].away_rank, 25)
        self.assertIsNone(frame.iloc[0].home_rank)
        scoreboard.assert_called_once_with(date(2026, 11, 10), date(2026, 11, 10))

    def render_app(self, unavailable=False):
        from streamlit.testing.v1 import AppTest
        tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
        names = {"render_cbb_current", "enrich_cfb_filter_metadata", "filter_cfb_team_scope", "sort_nfl_game_cards"}
        source = "import streamlit as st\nimport pandas as pd\nfrom datetime import date\n"
        source += "\n".join(ast.unparse(n) for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names)
        source += '''
FALLBACK_TIMEZONE = "America/New_York"
MODEL_BASELINES = MARKET_RELEASES = {"CBB": "test"}
selected_cbb_view = lambda _: "all"
current_date_for_timezone = lambda _: date(2026, 11, 10)
render_cbb_view_pills = lambda _: None
render_secondary_filter_pills = lambda _: []
safe_load_cbb_slate_history_rows = lambda *args: []
format_snapshot_caption = lambda _: "Snapshot as of: 11/10/2026, 6:00 PM ET"
filter_wnba_games = lambda slate, view: slate
apply_secondary_filters = lambda slate, filtered, *args: filtered
render_wnba_card = lambda row: st.markdown("Card: " + row["Game"])
slate = pd.DataFrame([
    {"Game ID": "final", "Game": "Final", "Status": "Final", "Sort Date": "2026-11-10T18:00:00Z"},
    {"Game ID": "later", "Game": "Later", "Status": "Scheduled", "Sort Date": "2030-11-10T23:00:00Z"},
    {"Game ID": "live", "Game": "Live", "Status": "In Progress", "Sort Date": "2026-11-10T19:00:00Z"},
    {"Game ID": "soon", "Game": "Soon", "Status": "Scheduled", "Sort Date": "2030-11-10T20:00:00Z"},
])
slate["Model Signal"] = slate["Side Edge"] = "Pass"
slate["Scoring Edge"] = "Neutral Scoring Environment"
load_cbb_current = lambda _: (slate.copy(), {})
metadata = pd.DataFrame([
    {"game_id": "final", "away_conference": "ACC", "home_conference": "Big Ten", "away_rank": None, "home_rank": None},
    {"game_id": "later", "away_conference": "ACC", "home_conference": "ACC", "away_rank": None, "home_rank": None},
    {"game_id": "live", "away_conference": "Big Ten", "home_conference": "Big Ten", "away_rank": 5, "home_rank": None},
    {"game_id": "soon", "away_conference": "SEC", "home_conference": "Big Ten", "away_rank": None, "home_rank": 25},
])
load_cbb_filter_metadata = lambda _: (metadata, ["ACC", "Big Ten", "SEC"])
attach_cbb_game_history = lambda slate, metadata, loader: slate
load_cbb_team_schedule = lambda *args: []
'''
        if unavailable:
            source += "def load_cbb_filter_metadata(_):\n    raise ValueError('offline')\n"
        source += "render_cbb_current()\n"
        return AppTest.from_string(source).run()

    def test_dropdown_and_status_time_order(self):
        app = self.render_app()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.selectbox[0].options, ["All Teams", "Any Top 25 Team", "ACC", "Big Ten", "SEC"])
        self.assertEqual([x.value for x in app.markdown], ["Card: Soon", "Card: Later", "Card: Live", "Card: Final"])
        app.selectbox[0].select("Any Top 25 Team").run()
        self.assertEqual([x.value for x in app.markdown], ["Card: Soon", "Card: Live"])
        app.selectbox[0].select("ACC").run()
        self.assertEqual([x.value for x in app.markdown], ["Card: Later", "Card: Final"])
        self.assertTrue(any("Snapshot as of:" in x.value for x in app.caption))

    def test_metadata_outage_keeps_all_games_available(self):
        app = self.render_app(unavailable=True)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.markdown), 4)
        self.assertTrue(any("temporarily unavailable" in x.value for x in app.caption))


if __name__ == "__main__":
    unittest.main()
