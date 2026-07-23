from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

import pandas as pd

from mls_data import load_mls_current_season


DEFAULT_TOTAL = 2.8
HOME_FIELD = 0.22
REST_WEIGHT = 0.025
MIN_SIGNAL_GAMES = 5


@dataclass
class TeamState:
    games: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    btts_games: int = 0
    over_25_games: int = 0
    clean_sheets: int = 0
    failed_to_score: int = 0
    recent_points: list[int] = field(default_factory=list)
    recent_totals: list[int] = field(default_factory=list)

    def ppg(self, default=1.35):
        return sum(self.recent_points[-5:]) / min(len(self.recent_points), 5) if self.recent_points else default

    def season_ppg(self, default=1.35):
        if not self.games:
            return default
        return ((self.wins * 3) + self.draws) / self.games

    def gf_avg(self, default=1.4):
        return self.goals_for / self.games if self.games else default

    def ga_avg(self, default=1.4):
        return self.goals_against / self.games if self.games else default

    def goal_diff_avg(self):
        return (self.goals_for - self.goals_against) / self.games if self.games else 0.0

    def btts_rate(self, default=0.52):
        return self.btts_games / self.games if self.games else default

    def over_25_rate(self, default=0.50):
        return self.over_25_games / self.games if self.games else default

    def recent_total_avg(self, default=DEFAULT_TOTAL):
        return sum(self.recent_totals[-5:]) / min(len(self.recent_totals), 5) if self.recent_totals else default


def update_team(state: TeamState, goals_for: int, goals_against: int):
    state.games += 1
    state.goals_for += goals_for
    state.goals_against += goals_against
    if goals_for > goals_against:
        state.wins += 1
        state.recent_points.append(3)
    elif goals_for == goals_against:
        state.draws += 1
        state.recent_points.append(1)
    else:
        state.losses += 1
        state.recent_points.append(0)
    total = goals_for + goals_against
    state.recent_totals.append(total)
    if goals_for > 0 and goals_against > 0:
        state.btts_games += 1
    if total > 2.5:
        state.over_25_games += 1
    if goals_against == 0:
        state.clean_sheets += 1
    if goals_for == 0:
        state.failed_to_score += 1


def format_game_time(raw_value):
    if pd.isna(raw_value) or not raw_value:
        return "TBD"
    try:
        game_dt = pd.to_datetime(raw_value)
        if game_dt.tzinfo is not None:
            game_dt = game_dt.tz_convert(ZoneInfo("America/New_York"))
        return game_dt.strftime("%a %b %d, %I:%M %p")
    except Exception:
        return str(raw_value)


def eastern_game_date(raw_value):
    game_dt = pd.to_datetime(raw_value)
    if game_dt.tzinfo is not None:
        game_dt = game_dt.tz_convert(ZoneInfo("America/New_York"))
    return game_dt.date()


def status_for_game(game):
    if bool(game.get("completed")):
        return "Final"
    return game.get("status") or "Scheduled"


def rating_for(state: TeamState):
    return (
        state.season_ppg() * 0.55
        + state.ppg() * 0.25
        + state.goal_diff_avg() * 0.35
    )


def confidence_from_edge(edge, away_games, home_games, draw_risk=0.0):
    history_penalty = 0.18 if min(away_games, home_games) < MIN_SIGNAL_GAMES else 0.0
    adjusted = abs(edge) - history_penalty - draw_risk
    if adjusted >= 0.82:
        return "A"
    if adjusted >= 0.58:
        return "B"
    if adjusted >= 0.38:
        return "C"
    return "Pass"


def double_chance_edge(model_margin, away, home, away_games, home_games, projected_total):
    if min(away_games, home_games) < MIN_SIGNAL_GAMES:
        return "Pass", "Pass"
    if model_margin >= 0.42:
        confidence = confidence_from_edge(model_margin, away_games, home_games)
        return f"{home} or Draw", confidence
    if model_margin <= -0.50:
        confidence = confidence_from_edge(model_margin, away_games, home_games)
        return f"{away} or Draw", confidence
    if abs(model_margin) <= 0.18 and projected_total >= 3.15:
        return "Home or Away", "C"
    return "Pass", "Pass"


def full_match_edge(model_margin, away, home, away_games, home_games, projected_total):
    if min(away_games, home_games) < MIN_SIGNAL_GAMES:
        return "Pass"
    if model_margin >= 0.78:
        return home
    if model_margin <= -0.88:
        return away
    if abs(model_margin) <= 0.12 and projected_total <= 2.45:
        return "Draw"
    return "Pass"


def goals_edge(projected_total, league_total):
    if projected_total >= league_total + 0.42:
        return "High Goals Environment"
    if projected_total <= league_total - 0.38:
        return "Low Goals Environment"
    return "Neutral Goals Environment"


def btts_edge(away_state, home_state, projected_total):
    yes_score = (away_state.btts_rate() + home_state.btts_rate()) / 2
    no_score = (
        (away_state.clean_sheets / away_state.games if away_state.games else 0.25)
        + (home_state.clean_sheets / home_state.games if home_state.games else 0.25)
        + (away_state.failed_to_score / away_state.games if away_state.games else 0.22)
        + (home_state.failed_to_score / home_state.games if home_state.games else 0.22)
    ) / 4
    if yes_score >= 0.62 and projected_total >= DEFAULT_TOTAL:
        return "BTTS Yes Watch" if yes_score < 0.68 else "BTTS Yes Lean"
    if no_score >= 0.36 and projected_total <= DEFAULT_TOTAL:
        return "BTTS No Watch" if no_score < 0.42 else "BTTS No Lean"
    return "Pass"


def model_signal_display(double_chance, full_match, scoring, btts):
    signals = []
    if double_chance != "Pass":
        signals.append(double_chance)
    if full_match != "Pass":
        signals.append(f"Full Match: {full_match}")
    if scoring != "Neutral Goals Environment":
        signals.append(scoring)
    if btts != "Pass":
        signals.append(btts)
    return " / ".join(signals) if signals else "Pass"


def release_segment(value, no_signal_values):
    text = str(value or "")
    if text.endswith(" Lean"):
        return "Lean"
    if text.endswith(" Watch"):
        return "Watch"
    if value in no_signal_values:
        return "No Edge"
    return "Official"


def discovery_release(pick=None, segment="No Edge"):
    return {
        "segment": segment,
        "pick": pick if segment in ["Lean", "Watch"] else None,
        "label": (
            f"{pick} {segment}"
            if pick and segment in ["Lean", "Watch"]
            else None
        ),
    }


def double_chance_release(edge, model_margin, away, home):
    if edge != "Pass":
        return discovery_release(segment="Official")
    if model_margin >= 0.32:
        return discovery_release(f"{home} or Draw", "Lean")
    if model_margin >= 0.24:
        return discovery_release(f"{home} or Draw", "Watch")
    if model_margin <= -0.40:
        return discovery_release(f"{away} or Draw", "Lean")
    if model_margin <= -0.30:
        return discovery_release(f"{away} or Draw", "Watch")
    return discovery_release()


def full_match_release(edge, model_margin, projected_total, away, home):
    if edge != "Pass":
        return discovery_release(segment="Official")
    if model_margin >= 0.62:
        return discovery_release(home, "Lean")
    if model_margin >= 0.50:
        return discovery_release(home, "Watch")
    if model_margin <= -0.70:
        return discovery_release(away, "Lean")
    if model_margin <= -0.58:
        return discovery_release(away, "Watch")
    if abs(model_margin) <= 0.16 and projected_total <= 2.55:
        return discovery_release("Draw", "Lean")
    if abs(model_margin) <= 0.20 and projected_total <= 2.65:
        return discovery_release("Draw", "Watch")
    return discovery_release()


def scoring_release(edge, projected_total, league_total):
    if edge != "Neutral Goals Environment":
        return discovery_release(segment="Official")
    delta = projected_total - league_total
    if delta >= 0.32:
        return discovery_release("High Goals Environment", "Lean")
    if delta >= 0.22:
        return discovery_release("High Goals Environment", "Watch")
    if delta <= -0.28:
        return discovery_release("Low Goals Environment", "Lean")
    if delta <= -0.18:
        return discovery_release("Low Goals Environment", "Watch")
    return discovery_release()


def btts_release(edge):
    segment = release_segment(edge, [None, "", "Pass"])
    if segment not in ["Lean", "Watch"]:
        return discovery_release(segment=segment)
    suffix = f" {segment}"
    pick = edge[: -len(suffix)] if edge.endswith(suffix) else edge
    return discovery_release(pick, segment)


def double_chance_result(edge, away, home, away_score, home_score, completed):
    if edge == "Pass":
        return "No Signal"
    if not completed or away_score is None or home_score is None:
        return "Pending"
    if edge == f"{home} or Draw":
        return "Correct" if home_score >= away_score else "Missed"
    if edge == f"{away} or Draw":
        return "Correct" if away_score >= home_score else "Missed"
    if edge == "Home or Away":
        return "Correct" if home_score != away_score else "Missed"
    return "Pending"


def exact_result(edge, actual_winner, completed, away_score=None, home_score=None):
    if edge == "Pass":
        return "No Signal"
    if not completed or actual_winner is None:
        return "Pending"
    if edge == "Draw":
        return "Correct" if away_score == home_score else "Missed"
    return "Correct" if edge == actual_winner else "Missed"


def scoring_result_for_game(scoring_edge, actual_total, league_total, completed):
    if scoring_edge == "Neutral Goals Environment":
        return "No Signal"
    if not completed or actual_total is None:
        return "Pending"
    if scoring_edge == "High Goals Environment":
        return "Correct" if actual_total > league_total else "Missed"
    if scoring_edge == "Low Goals Environment":
        return "Correct" if actual_total < league_total else "Missed"
    return "No Signal"


def btts_result_for_game(edge, away_score, home_score, completed):
    if edge == "Pass":
        return "No Signal"
    if not completed or away_score is None or home_score is None:
        return "Pending"
    actual_yes = away_score > 0 and home_score > 0
    wants_yes = "Yes" in edge
    return "Correct" if wants_yes == actual_yes else "Missed"


def split_notes(notes):
    if not notes:
        return []
    return [note.strip() for note in str(notes).split(";") if note.strip()]


def build_current_slate(season=None, today=None, days_ahead=14, slate_date=None):
    target_date = slate_date or today or pd.Timestamp.today().date()
    games = load_mls_current_season(
        season=season,
        today=target_date,
        days_ahead=days_ahead,
    )
    if games.empty:
        return pd.DataFrame(), {"empty_reason": "no_games"}

    states: dict[str, TeamState] = {}
    league_totals = []
    rows = []
    target_date = pd.Timestamp(target_date).date()

    for _, game in games.sort_values(["game_date_dt", "game_id"]).iterrows():
        away = game["away_team"]
        home = game["home_team"]
        completed = bool(game.get("completed"))
        away_score = game.get("away_score")
        home_score = game.get("home_score")
        league_total = sum(league_totals) / len(league_totals) if league_totals else DEFAULT_TOTAL

        away_state = states.setdefault(away, TeamState())
        home_state = states.setdefault(home, TeamState())
        rest_edge = float(game.get("home_rest", 0) or 0) - float(game.get("away_rest", 0) or 0)
        model_margin = rating_for(home_state) - rating_for(away_state) + HOME_FIELD + rest_edge * REST_WEIGHT

        away_goal_base = (away_state.gf_avg() + home_state.ga_avg()) / 2
        home_goal_base = (home_state.gf_avg() + away_state.ga_avg()) / 2 + 0.08
        recent_total = (away_state.recent_total_avg() + home_state.recent_total_avg()) / 2
        projected_total = (away_goal_base + home_goal_base) * 0.62 + recent_total * 0.18 + league_total * 0.20
        draw_risk = max(0.0, 0.28 - abs(model_margin)) + (0.10 if projected_total <= league_total else 0.0)

        side_edge, side_confidence = double_chance_edge(
            model_margin, away, home, away_state.games, home_state.games, projected_total
        )
        full_edge = full_match_edge(model_margin, away, home, away_state.games, home_state.games, projected_total)
        scoring_edge = goals_edge(projected_total, league_total)
        btts_signal = btts_edge(away_state, home_state, projected_total)
        side_release = double_chance_release(side_edge, model_margin, away, home)
        full_release = full_match_release(
            full_edge,
            model_margin,
            projected_total,
            away,
            home,
        )
        scoring_release_value = scoring_release(
            scoring_edge,
            projected_total,
            league_total,
        )
        btts_release_value = btts_release(btts_signal)

        score_strength = max(abs(model_margin) * 42, abs(projected_total - league_total) * 55)
        if side_confidence == "A":
            score_strength += 10
        elif side_confidence == "B":
            score_strength += 5
        edge_score = round(min(99.0, score_strength), 1)

        confidence = side_confidence
        if confidence == "Pass" and scoring_edge != "Neutral Goals Environment":
            confidence = "C"
        if confidence == "Pass" and full_edge != "Pass":
            confidence = "C"

        actual_winner = None
        actual_total = None
        away_score_int = None
        home_score_int = None
        if completed and pd.notna(away_score) and pd.notna(home_score):
            away_score_int = int(away_score)
            home_score_int = int(home_score)
            actual_total = away_score_int + home_score_int
            if home_score_int > away_score_int:
                actual_winner = home
            elif away_score_int > home_score_int:
                actual_winner = away
            else:
                actual_winner = "Draw"

        side_result = double_chance_result(side_edge, away, home, away_score_int, home_score_int, completed)
        full_result = exact_result(full_edge, actual_winner, completed, away_score_int, home_score_int)
        scoring_result = scoring_result_for_game(scoring_edge, actual_total, league_total, completed)
        btts_result = btts_result_for_game(
            "Pass",
            away_score_int,
            home_score_int,
            completed,
        )
        side_discovery_result = double_chance_result(
            side_release["pick"] or "Pass",
            away,
            home,
            away_score_int,
            home_score_int,
            completed,
        )
        full_discovery_result = exact_result(
            full_release["pick"] or "Pass",
            actual_winner,
            completed,
            away_score_int,
            home_score_int,
        )
        scoring_discovery_result = scoring_result_for_game(
            scoring_release_value["pick"] or "Neutral Goals Environment",
            actual_total,
            league_total,
            completed,
        )
        btts_discovery_result = btts_result_for_game(
            btts_release_value["pick"] or "Pass",
            away_score_int,
            home_score_int,
            completed,
        )

        notes = [
            f"Model margin {model_margin:.2f} toward {'home' if model_margin >= 0 else 'away'}",
            f"Projected goals {projected_total:.2f} vs league baseline {league_total:.2f}",
            f"Draw risk {draw_risk:.2f}",
            f"Prior games: {away} {away_state.games}, {home} {home_state.games}",
        ]

        game_day = eastern_game_date(game["game_date_dt"])
        if game_day == target_date:
            rows.append(
                {
                    "Sport": "MLS",
                    "Game ID": game.get("game_id"),
                    "Season": int(game["season"]) if pd.notna(game["season"]) else None,
                    "Game Time": format_game_time(game["game_date_dt"]),
                    "Sort Date": game["game_date_dt"],
                    "Game": f"{away} @ {home}",
                    "Away": away,
                    "Home": home,
                    "Away Score": away_score_int,
                    "Home Score": home_score_int,
                    "Actual Winner": actual_winner,
                    "Predicted Winner": full_edge if full_edge != "Pass" else None,
                    "Actual Total": actual_total,
                    "Model Signal": model_signal_display(
                        side_edge,
                        full_edge,
                        scoring_edge,
                        "Pass",
                    ),
                    "Edge Score": edge_score,
                    "Confidence": confidence,
                    "Side Edge": side_edge,
                    "Side Tracking Segment": side_release["segment"],
                    "Side Discovery Pick": side_release["pick"],
                    "Side Discovery Label": side_release["label"],
                    "Side Discovery Result": side_discovery_result,
                    "Full Match Edge": full_edge,
                    "Full Match Tracking Segment": full_release["segment"],
                    "Full Match Discovery Pick": full_release["pick"],
                    "Full Match Discovery Label": full_release["label"],
                    "Full Match Discovery Result": full_discovery_result,
                    "Scoring Edge": scoring_edge,
                    "Scoring Tracking Segment": scoring_release_value["segment"],
                    "Scoring Discovery Pick": scoring_release_value["pick"],
                    "Scoring Discovery Label": scoring_release_value["label"],
                    "Scoring Discovery Result": scoring_discovery_result,
                    "BTTS Edge": btts_signal,
                    "BTTS Tracking Segment": btts_release_value["segment"],
                    "BTTS Discovery Pick": btts_release_value["pick"],
                    "BTTS Discovery Label": btts_release_value["label"],
                    "BTTS Discovery Result": btts_discovery_result,
                    "Early Edge": "First Half Pending",
                    "Side Result": side_result,
                    "Winner Result": full_result,
                    "Scoring Result": scoring_result,
                    "BTTS Result": btts_result,
                    "Model Margin": round(model_margin, 2),
                    "Projected Total": round(projected_total, 2),
                    "League Total Baseline": round(league_total, 2),
                    "Away Prior Games": away_state.games,
                    "Home Prior Games": home_state.games,
                    "Rest Edge": round(rest_edge, 2),
                    "Draw Risk": round(draw_risk, 2),
                    "Key Factors Summary": "; ".join(notes[:2]),
                    "Key Factors List": notes,
                    "Agent Notes": "; ".join(notes),
                    "Status": status_for_game(game),
                }
            )

        if completed and pd.notna(away_score) and pd.notna(home_score):
            update_team(away_state, int(away_score), int(home_score))
            update_team(home_state, int(home_score), int(away_score))
            league_totals.append(int(away_score) + int(home_score))

    slate = pd.DataFrame(rows)
    if not slate.empty:
        slate = slate.sort_values(["Sort Date", "Game"])
    return slate, {"season": season or target_date.year, "slate_date": target_date}
