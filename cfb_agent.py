from dataclasses import dataclass, field
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd

from cfb_data import load_cfb_prior_season, load_cfb_season


EASTERN = ZoneInfo("America/New_York")
DEFAULT_RATING = 1500.0
DEFAULT_TOTAL = 52.0
HOME_FIELD_POINTS = 2.5
RATING_POINTS_SCALE = 25.0
MIN_PRESEASON_GAMES = 6
PRESEASON_RATING_RETENTION = 0.55
PRESEASON_SCORING_RETENTION = 0.50
PRESEASON_DECAY_GAMES = 6


@dataclass
class TeamState:
    preseason_rating: float = DEFAULT_RATING
    preseason_offense: float = DEFAULT_TOTAL / 2
    preseason_defense: float = DEFAULT_TOTAL / 2
    prior_games: int = 0
    current_rating: float = DEFAULT_RATING
    games: int = 0
    points_for: list[float] = field(default_factory=list)
    points_against: list[float] = field(default_factory=list)

    @property
    def prior_ready(self):
        return self.prior_games >= MIN_PRESEASON_GAMES

    def prior_influence(self):
        if not self.prior_ready:
            return 0.0
        return max(
            0.0,
            1.0 - (self.games / float(PRESEASON_DECAY_GAMES)),
        )

    def rating(self):
        weight = self.prior_influence()
        return (
            self.preseason_rating * weight
            + self.current_rating * (1.0 - weight)
        )

    def offense(self, fallback):
        current = (
            sum(self.points_for[-6:]) / len(self.points_for[-6:])
            if self.points_for
            else fallback
        )
        weight = self.prior_influence()
        return self.preseason_offense * weight + current * (1.0 - weight)

    def defense(self, fallback):
        current = (
            sum(self.points_against[-6:]) / len(self.points_against[-6:])
            if self.points_against
            else fallback
        )
        weight = self.prior_influence()
        return self.preseason_defense * weight + current * (1.0 - weight)


@dataclass
class PriorState:
    rating: float = DEFAULT_RATING
    games: int = 0
    points_for: list[float] = field(default_factory=list)
    points_against: list[float] = field(default_factory=list)


def format_game_time(value):
    timestamp = pd.to_datetime(value, utc=True)
    return timestamp.tz_convert(EASTERN).strftime("%a %b %d, %I:%M %p ET")


def eastern_date(value):
    return pd.to_datetime(value, utc=True).tz_convert(EASTERN).date()


def status_for_game(game):
    if bool(game.get("completed")):
        return "Final"
    return str(game.get("status") or "Scheduled")


def update_state(state: TeamState, points_for: int, points_against: int, residual: float):
    state.current_rating += max(-35.0, min(35.0, residual * 0.65))
    state.games += 1
    state.points_for.append(float(points_for))
    state.points_against.append(float(points_against))


def game_team_key(game, side):
    team_id = str(game.get(f"{side}_team_id") or "").strip()
    if team_id:
        return f"espn:{team_id}"
    return f"name:{str(game.get(f'{side}_team') or '').strip().casefold()}"


def build_preseason_priors(games):
    states: dict[str, PriorState] = {}
    if games is None or games.empty:
        return {}
    for _, game in games.sort_values(["game_date_dt", "game_id"]).iterrows():
        away_score = game.get("away_score")
        home_score = game.get("home_score")
        if (
            not bool(game.get("completed"))
            or pd.isna(away_score)
            or pd.isna(home_score)
        ):
            continue
        away_score = int(away_score)
        home_score = int(home_score)
        away_state = states.setdefault(game_team_key(game, "away"), PriorState())
        home_state = states.setdefault(game_team_key(game, "home"), PriorState())
        home_field = 0.0 if bool(game.get("neutral_site")) else HOME_FIELD_POINTS
        expected_margin = (
            (home_state.rating - away_state.rating) / RATING_POINTS_SCALE
            + home_field
        )
        residual = (home_score - away_score) - expected_margin
        adjustment = max(-35.0, min(35.0, residual * 0.65))
        home_state.rating += adjustment
        away_state.rating -= adjustment
        for state, points_for, points_against in [
            (home_state, home_score, away_score),
            (away_state, away_score, home_score),
        ]:
            state.games += 1
            state.points_for.append(float(points_for))
            state.points_against.append(float(points_against))

    priors = {}
    league_points = DEFAULT_TOTAL / 2
    for team_key, state in states.items():
        if state.games < MIN_PRESEASON_GAMES:
            continue
        offense = sum(state.points_for) / len(state.points_for)
        defense = sum(state.points_against) / len(state.points_against)
        priors[team_key] = {
            "rating": DEFAULT_RATING
            + (state.rating - DEFAULT_RATING) * PRESEASON_RATING_RETENTION,
            "offense": league_points
            + (offense - league_points) * PRESEASON_SCORING_RETENTION,
            "defense": league_points
            + (defense - league_points) * PRESEASON_SCORING_RETENTION,
            "games": state.games,
        }
    return priors


def team_state(priors, team_key):
    prior = priors.get(team_key)
    if not prior:
        return TeamState()
    return TeamState(
        preseason_rating=prior["rating"],
        preseason_offense=prior["offense"],
        preseason_defense=prior["defense"],
        prior_games=prior["games"],
    )


def base_segment(abs_margin):
    if abs_margin >= 10:
        return "Official"
    if abs_margin >= 7:
        return "Lean"
    if abs_margin >= 4:
        return "Watch"
    return "Pass"


def cap_segment(segment, cap):
    order = {"Pass": 0, "Watch": 1, "Lean": 2, "Official": 3}
    if segment == "Pass":
        return segment
    return segment if order[segment] <= order[cap] else cap


def confidence_for(segment, abs_margin):
    if segment == "Official":
        return "A" if abs_margin >= 14 else "B"
    if segment == "Lean":
        return "B"
    if segment == "Watch":
        return "C"
    return "Pass"


def decision_label(pick, segment):
    return f"{pick} {segment}" if segment in {"Lean", "Watch"} else pick


def grade_team_pick(pick, actual_winner, completed):
    if not pick or pick == "Pass":
        return "No Signal"
    if not completed or not actual_winner:
        return "Pending"
    return "Correct" if pick == actual_winner else "Missed"


def grade_scoring(label, actual_total, baseline, completed):
    if label == "Neutral Scoring Environment":
        return "No Signal"
    if not completed or actual_total is None:
        return "Pending"
    if label == "High Scoring Environment":
        return "Correct" if actual_total > baseline else "Missed"
    return "Correct" if actual_total < baseline else "Missed"


def key_factors(row):
    factors = [
        f"Model margin {row['Model Margin']:+.1f} toward {row['Predicted Winner']}",
        (
            f"Projected total {row['Projected Total']:.1f} vs rolling "
            f"baseline {row['League Total Baseline']:.1f}"
        ),
        (
            f"Prior-season regressed ratings: {row['Away']} "
            f"{row['Away Preseason Rating']:.0f}, {row['Home']} "
            f"{row['Home Preseason Rating']:.0f}"
        ),
        (
            f"Prior-season adjusted offense: {row['Away']} "
            f"{row['Away Preseason Offense']:.1f}, {row['Home']} "
            f"{row['Home Preseason Offense']:.1f}"
        ),
        (
            f"Preseason prior influence: {row['Away']} "
            f"{row['Away Prior Influence']:.0%}, {row['Home']} "
            f"{row['Home Prior Influence']:.0%}"
        ),
    ]
    if row["Neutral Site"]:
        factors.append("Neutral site removes standard home-field advantage")
    if row["FBS vs FCS"]:
        factors.append("FBS-vs-FCS policy caps every decision at Watch")
    factors.extend(row["Downgrade Reasons"])
    return factors


def build_current_slate(
    season=None,
    today=None,
    days_ahead=14,
    slate_date=None,
):
    target_date = pd.Timestamp(slate_date or today or date.today()).date()
    games = load_cfb_season(
        season=season,
        today=target_date,
        days_ahead=days_ahead,
    )
    if games.empty:
        return pd.DataFrame(), {
            "season": season or target_date.year,
            "slate_date": target_date,
            "empty_reason": "no_games",
        }

    model_season = int(games.iloc[0]["season"])
    prior_games = load_cfb_prior_season(model_season)
    preseason_priors = build_preseason_priors(prior_games)
    states: dict[str, TeamState] = {}
    league_totals = []
    rows = []
    for _, game in games.sort_values(["game_date_dt", "game_id"]).iterrows():
        away = game["away_team"]
        home = game["home_team"]
        away_key = game_team_key(game, "away")
        home_key = game_team_key(game, "home")
        away_state = states.setdefault(
            away_key,
            team_state(preseason_priors, away_key),
        )
        home_state = states.setdefault(
            home_key,
            team_state(preseason_priors, home_key),
        )
        league_total = (
            sum(league_totals[-80:]) / len(league_totals[-80:])
            if league_totals
            else DEFAULT_TOTAL
        )
        league_points = league_total / 2
        neutral = bool(game.get("neutral_site"))
        home_field = 0.0 if neutral else HOME_FIELD_POINTS
        model_margin = (
            (home_state.rating() - away_state.rating()) / RATING_POINTS_SCALE
            + home_field
        )
        away_projection = (
            away_state.offense(league_points)
            + home_state.defense(league_points)
        ) / 2
        home_projection = (
            home_state.offense(league_points)
            + away_state.defense(league_points)
        ) / 2
        projected_total = (
            (away_projection + home_projection) * 0.78 + league_total * 0.22
        )

        predicted_winner = home if model_margin >= 0 else away
        abs_margin = abs(model_margin)
        side_segment = base_segment(abs_margin)
        scoring_delta = projected_total - league_total
        if abs(scoring_delta) >= 7:
            scoring_segment = "Lean"
        elif abs(scoring_delta) >= 4:
            scoring_segment = "Watch"
        else:
            scoring_segment = "Pass"
        first_half_segment = (
            "Lean" if abs_margin >= 10 else "Watch" if abs_margin >= 6 else "Pass"
        )

        downgrade_reasons = []
        fbs_vs_fcs = {
            game.get("away_classification"),
            game.get("home_classification"),
        } != {"FBS"}
        if fbs_vs_fcs:
            downgrade_reasons.append("FBS-vs-FCS matchup")
            side_segment = cap_segment(side_segment, "Watch")
            scoring_segment = cap_segment(scoring_segment, "Watch")
            first_half_segment = cap_segment(first_half_segment, "Watch")

        if not away_state.prior_ready or not home_state.prior_ready:
            downgrade_reasons.append("Insufficient preseason history")
            side_segment = cap_segment(side_segment, "Watch")
            scoring_segment = cap_segment(scoring_segment, "Watch")
            first_half_segment = cap_segment(first_half_segment, "Watch")

        min_history = min(away_state.games, home_state.games)
        if min_history < 3:
            downgrade_reasons.append("Limited current-season team history")
            side_segment = cap_segment(side_segment, "Watch")
            scoring_segment = cap_segment(scoring_segment, "Watch")
            first_half_segment = cap_segment(first_half_segment, "Watch")

        # Availability is an approved hard gate and is not in the v0 feed yet.
        downgrade_reasons.append("Availability feed incomplete")
        side_segment = cap_segment(side_segment, "Watch")
        scoring_segment = cap_segment(scoring_segment, "Watch")
        first_half_segment = cap_segment(first_half_segment, "Watch")

        side_pick = predicted_winner if side_segment != "Pass" else "Pass"
        scoring_pick = (
            "High Scoring Environment"
            if scoring_delta > 0 and scoring_segment != "Pass"
            else "Low Scoring Environment"
            if scoring_segment != "Pass"
            else "Neutral Scoring Environment"
        )
        first_half_pick = (
            predicted_winner if first_half_segment != "Pass" else "Pass"
        )
        side_confidence = confidence_for(side_segment, abs_margin)
        scoring_confidence = confidence_for(
            scoring_segment,
            abs(scoring_delta),
        )
        first_half_confidence = confidence_for(
            first_half_segment,
            abs_margin,
        )
        completed = bool(game.get("completed"))
        away_score = game.get("away_score")
        home_score = game.get("home_score")
        actual_winner = None
        actual_total = None
        if completed and pd.notna(away_score) and pd.notna(home_score):
            away_score = int(away_score)
            home_score = int(home_score)
            if away_score != home_score:
                actual_winner = home if home_score > away_score else away
            actual_total = away_score + home_score

        away_half = game.get("away_first_half")
        home_half = game.get("home_first_half")
        first_half_winner = None
        first_half_result = "Pending" if first_half_pick != "Pass" else "No Signal"
        if completed and pd.notna(away_half) and pd.notna(home_half):
            away_half = int(away_half)
            home_half = int(home_half)
            if away_half == home_half:
                first_half_result = "Push" if first_half_pick != "Pass" else "No Signal"
            else:
                first_half_winner = home if home_half > away_half else away
                first_half_result = grade_team_pick(
                    first_half_pick, first_half_winner, True
                )

        if eastern_date(game["game_date_dt"]) == target_date:
            row = {
                "Sport": "CFB",
                "Game ID": game["game_id"],
                "Season": int(game["season"]),
                "Week": game.get("week"),
                "Game Time": format_game_time(game["game_date_dt"]),
                "Scheduled Kickoff": game["game_date_dt"].isoformat(),
                "Sort Date": game["game_date_dt"],
                "Game": f"{away} @ {home}",
                "Away": away,
                "Home": home,
                "Away Score": away_score if completed else None,
                "Home Score": home_score if completed else None,
                "Away First Half": away_half if pd.notna(away_half) else None,
                "Home First Half": home_half if pd.notna(home_half) else None,
                "Actual Winner": actual_winner,
                "Actual Total": actual_total,
                "Predicted Winner": predicted_winner,
                "Side Pick": side_pick,
                "Side Edge": decision_label(side_pick, side_segment),
                "Side Tracking Segment": side_segment,
                "Side Discovery Label": (
                    f"Full Game {side_segment}: {side_pick}"
                    if side_segment in {"Lean", "Watch"}
                    else None
                ),
                "Scoring Pick": scoring_pick,
                "Scoring Edge": decision_label(scoring_pick, scoring_segment),
                "Scoring Tracking Segment": scoring_segment,
                "Scoring Discovery Label": (
                    f"Scoring {scoring_segment}: {scoring_pick}"
                    if scoring_segment in {"Lean", "Watch"}
                    else None
                ),
                "First Half Pick": first_half_pick,
                "Early Edge": decision_label(first_half_pick, first_half_segment),
                "First Half Tracking Segment": first_half_segment,
                "First Half Discovery Label": (
                    f"First Half {first_half_segment}: {first_half_pick}"
                    if first_half_segment in {"Lean", "Watch"}
                    else None
                ),
                "Model Signal": (
                    side_pick
                    if side_segment != "Pass"
                    else scoring_pick
                    if scoring_segment != "Pass"
                    else "Pass"
                ),
                "Edge Score": round(abs_margin * 5, 1),
                "Confidence": side_confidence,
                "Side Score": round(abs_margin, 2),
                "Side Confidence": side_confidence,
                "Scoring Score": round(abs(scoring_delta), 2),
                "Scoring Confidence": scoring_confidence,
                "First Half Score": round(abs_margin, 2),
                "First Half Confidence": first_half_confidence,
                "Side Result": grade_team_pick(
                    side_pick, actual_winner, completed
                ),
                "Winner Result": grade_team_pick(
                    side_pick, actual_winner, completed
                ),
                "Scoring Result": grade_scoring(
                    scoring_pick, actual_total, league_total, completed
                ),
                "First Half Result": first_half_result,
                "Model Margin": round(model_margin, 2),
                "Projected Total": round(projected_total, 2),
                "League Total Baseline": round(league_total, 2),
                "Away Prior Games": away_state.games,
                "Home Prior Games": home_state.games,
                "Away Preseason Games": away_state.prior_games,
                "Home Preseason Games": home_state.prior_games,
                "Away Preseason Rating": away_state.preseason_rating,
                "Home Preseason Rating": home_state.preseason_rating,
                "Away Preseason Offense": away_state.preseason_offense,
                "Home Preseason Offense": home_state.preseason_offense,
                "Away Preseason Defense": away_state.preseason_defense,
                "Home Preseason Defense": home_state.preseason_defense,
                "Away Prior Influence": away_state.prior_influence(),
                "Home Prior Influence": home_state.prior_influence(),
                "Neutral Site": neutral,
                "FBS vs FCS": fbs_vs_fcs,
                "Availability Status": "Incomplete",
                "Data Quality": "Limited" if downgrade_reasons else "Complete",
                "Downgrade Reasons": downgrade_reasons,
                "Source": (
                    (
                        f"ESPN current slate + ESPN {model_season - 1} bootstrap"
                        if game.get("source") == "ESPN"
                        else f"{game.get('source')} + ESPN "
                        f"{model_season - 1} bootstrap"
                    )
                    if preseason_priors
                    else game.get("source")
                ),
                "Source Timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
                "Status": status_for_game(game),
            }
            row["Key Factors List"] = key_factors(row)
            row["Key Factors Summary"] = "; ".join(row["Key Factors List"][:3])
            row["Agent Notes"] = "; ".join(row["Key Factors List"])
            rows.append(row)

        if completed and actual_winner:
            actual_margin = home_score - away_score
            residual = actual_margin - model_margin
            update_state(home_state, home_score, away_score, residual)
            update_state(away_state, away_score, home_score, -residual)
            league_totals.append(actual_total)

    slate = pd.DataFrame(rows)
    if not slate.empty:
        slate = slate.sort_values(["Sort Date", "Game"]).reset_index(drop=True)
    return slate, {
        "season": season or target_date.year,
        "slate_date": target_date,
    }
