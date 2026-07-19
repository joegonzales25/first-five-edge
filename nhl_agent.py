import pandas as pd
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from nhl_data import add_rest_days, load_nhl_current_season


@dataclass(frozen=True)
class NHLConfig:
    side_a: float = 1.15
    side_b: float = 0.85
    side_c: float = 0.55
    min_a_games: int = 8
    min_b_games: int = 5
    min_c_games: int = 0
    home_ice: float = 0.18
    rest_weight: float = 0.06
    recent_margin_weight: float = 0.32
    default_total: float = 6.1


NHL_CONFIG = NHLConfig()


@dataclass
class TeamState:
    games: int = 0
    wins: int = 0
    goals_for: float = 0.0
    goals_against: float = 0.0
    margin: float = 0.0
    totals: list[float] = field(default_factory=list)
    recent_margins: list[float] = field(default_factory=list)

    def goals_for_avg(self, league_goals: float) -> float:
        if self.games == 0:
            return league_goals
        return self.goals_for / self.games

    def goals_against_avg(self, league_goals: float) -> float:
        if self.games == 0:
            return league_goals
        return self.goals_against / self.games

    def margin_avg(self) -> float:
        if self.games == 0:
            return 0.0
        return self.margin / self.games

    def recent_form(self) -> float:
        if not self.recent_margins:
            return 0.0
        recent = self.recent_margins[-5:]
        return sum(recent) / len(recent)

    def total_avg(self, league_total: float) -> float:
        if not self.totals:
            return league_total
        recent = self.totals[-8:]
        return sum(recent) / len(recent)


def split_notes(notes):
    if not notes:
        return []
    return [note.strip() for note in str(notes).split(";") if note.strip()]


def key_factors_summary(notes):
    factors = split_notes(notes)
    if not factors:
        return "Neutral model profile"
    return "; ".join(factors[:2])


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


def rating_for(team: TeamState, league_goals: float, config=NHL_CONFIG) -> float:
    offense = team.goals_for_avg(league_goals) - league_goals
    defense = league_goals - team.goals_against_avg(league_goals)
    season_form = team.margin_avg() * 0.46
    recent_form = team.recent_form() * config.recent_margin_weight
    return offense * 0.48 + defense * 0.52 + season_form + recent_form


def confidence_from_margin(edge_margin, away_games=0, home_games=0, config=NHL_CONFIG):
    edge = abs(edge_margin)
    prior_games = min(away_games, home_games)
    if edge >= config.side_a and prior_games >= config.min_a_games:
        return "A"
    if edge >= config.side_b and prior_games >= config.min_b_games:
        return "B"
    if edge >= config.side_c and prior_games >= config.min_c_games:
        return "C"
    return "Pass"


def moneyline_edge_label(edge_margin, away, home, away_games=0, home_games=0):
    confidence = confidence_from_margin(edge_margin, away_games, home_games)
    if confidence == "Pass":
        return "Pass"
    team = home if edge_margin > 0 else away
    return f"{team} Edge"


def goal_environment_label(projected_total, league_total):
    delta = projected_total - league_total
    if delta >= 0.75:
        return "High Goal Environment"
    if delta <= -0.75:
        return "Low Goal Environment"
    return "Neutral Goal Environment"


def model_signal_display(moneyline_edge):
    return moneyline_edge if moneyline_edge != "Pass" else "Pass"


def calculate_edge_score(edge_margin, confidence):
    score = 45 + min(abs(edge_margin) * 25, 34)
    if confidence == "A":
        score += 8
    elif confidence == "B":
        score += 5
    elif confidence == "C":
        score += 2
    return round(max(0, min(score, 95)), 1)


def side_result_for_game(edge, predicted_winner, actual_winner, completed):
    if edge == "Pass":
        return "No Signal"
    if not completed or actual_winner is None:
        return "Pending"
    return "Correct" if predicted_winner == actual_winner else "Missed"


def status_for_game(game):
    if bool(game.get("completed")):
        return "Final"
    return game.get("status") or "Scheduled"


def side_reasons(away, home, away_rating, home_rating, rest_edge, edge_margin, away_games, home_games):
    reasons = []
    rating_gap = home_rating - away_rating
    leading_team = home if edge_margin > 0 else away
    if abs(rating_gap) >= 0.75:
        stronger = home if rating_gap > 0 else away
        reasons.append(f"{stronger} holds the stronger rolling goal profile")
    elif abs(rating_gap) >= 0.35:
        stronger = home if rating_gap > 0 else away
        reasons.append(f"{stronger} has a modest rolling goal-profile edge")
    reasons.append(f"{home} receives home-ice context")
    if abs(rest_edge) >= 2:
        rested = home if rest_edge > 0 else away
        reasons.append(f"{rested} has a meaningful rest advantage")
    elif abs(rest_edge) >= 1:
        rested = home if rest_edge > 0 else away
        reasons.append(f"{rested} has a small rest advantage")
    confidence = confidence_from_margin(edge_margin, away_games, home_games)
    if confidence == "Pass":
        reasons.append("Moneyline edge stays below official threshold")
    else:
        reasons.append(f"{leading_team} clears the moneyline-edge threshold")
    if min(away_games, home_games) < NHL_CONFIG.min_b_games:
        reasons.append("Limited team history keeps confidence capped early")
    reasons.append("Goalie confirmation is not modeled in v0")
    return reasons


def update_team(states, team, goals_for, goals_against):
    state = states.setdefault(team, TeamState())
    margin = goals_for - goals_against
    total = goals_for + goals_against
    state.games += 1
    state.wins += int(goals_for > goals_against)
    state.goals_for += goals_for
    state.goals_against += goals_against
    state.margin += margin
    state.totals.append(float(total))
    state.recent_margins.append(float(margin))


def completed_games_for_lab(games: pd.DataFrame) -> pd.DataFrame:
    if games.empty:
        return games
    return games[
        games["completed"]
        & games["away_score"].notna()
        & games["home_score"].notna()
    ].copy()


def prepare_schedule(games: pd.DataFrame) -> pd.DataFrame:
    games = games.copy()
    if games.empty:
        return games

    if "game_date_dt" not in games.columns:
        games["game_date_dt"] = pd.to_datetime(games["game_date"], errors="coerce")
    else:
        games["game_date_dt"] = pd.to_datetime(games["game_date_dt"], errors="coerce")

    for score_col in ["away_score", "home_score"]:
        games[score_col] = pd.to_numeric(games.get(score_col), errors="coerce")

    if "completed" not in games.columns:
        games["completed"] = games["away_score"].notna() & games["home_score"].notna()
    else:
        games["completed"] = games["completed"].map(
            lambda value: value
            if isinstance(value, bool)
            else str(value).strip().lower() in ["true", "1", "yes", "final", "completed"]
        )
    if "status" not in games.columns:
        games["status"] = games["completed"].map(lambda value: "Final" if value else "Scheduled")
    if "game_id" not in games.columns:
        games["game_id"] = [
            f"nhl-{idx}-{row.get('away_team', '')}-{row.get('home_team', '')}"
            for idx, row in games.iterrows()
        ]
    if "season" not in games.columns:
        games["season"] = games["game_date_dt"].dt.year

    games = games.dropna(subset=["game_date_dt", "away_team", "home_team"]).copy()
    games = games.sort_values(["game_date_dt", "game_id"]).reset_index(drop=True)
    if "away_rest" not in games.columns or "home_rest" not in games.columns:
        games = add_rest_days(games)
    return games


def build_slate_from_games(games: pd.DataFrame, target_date=None, season=None):
    games = prepare_schedule(games)
    if games.empty:
        return pd.DataFrame(), {"empty_reason": "no_games"}

    states: dict[str, TeamState] = {}
    league_totals = []
    rows = []
    target_date = pd.Timestamp(target_date).date() if target_date is not None else None

    for _, game in games.sort_values(["game_date_dt", "game_id"]).iterrows():
        away = game["away_team"]
        home = game["home_team"]
        completed = bool(game.get("completed"))
        away_score = game.get("away_score")
        home_score = game.get("home_score")
        league_total = (
            sum(league_totals) / len(league_totals)
            if league_totals
            else NHL_CONFIG.default_total
        )
        league_goals = league_total / 2
        away_state = states.setdefault(away, TeamState())
        home_state = states.setdefault(home, TeamState())
        away_rating = rating_for(away_state, league_goals)
        home_rating = rating_for(home_state, league_goals)
        rest_edge = float(game.get("home_rest", 0) or 0) - float(
            game.get("away_rest", 0) or 0
        )
        edge_margin = (
            home_rating
            - away_rating
            + NHL_CONFIG.home_ice
            + (rest_edge * NHL_CONFIG.rest_weight)
        )
        projected_total = (
            away_state.total_avg(league_total) * 0.33
            + home_state.total_avg(league_total) * 0.33
            + league_total * 0.34
        )
        confidence = confidence_from_margin(
            edge_margin,
            away_state.games,
            home_state.games,
        )
        moneyline_edge = moneyline_edge_label(
            edge_margin,
            away,
            home,
            away_state.games,
            home_state.games,
        )
        goal_environment = goal_environment_label(projected_total, league_total)
        edge_score = calculate_edge_score(edge_margin, confidence)
        notes = "; ".join(
            side_reasons(
                away,
                home,
                away_rating,
                home_rating,
                rest_edge,
                edge_margin,
                away_state.games,
                home_state.games,
            )
        )
        predicted_winner = home if edge_margin > 0 else away
        actual_winner = None
        actual_total = None
        margin_error = None
        total_error = None
        side_result = side_result_for_game(
            moneyline_edge,
            predicted_winner,
            actual_winner,
            completed,
        )

        if completed and pd.notna(away_score) and pd.notna(home_score):
            away_score_int = int(away_score)
            home_score_int = int(home_score)
            actual_winner = home if home_score_int > away_score_int else away
            actual_total = away_score_int + home_score_int
            margin_error = abs(edge_margin - (home_score_int - away_score_int))
            total_error = abs(projected_total - actual_total)
            side_result = side_result_for_game(
                moneyline_edge,
                predicted_winner,
                actual_winner,
                completed,
            )

        game_day = eastern_game_date(game["game_date_dt"])
        if target_date is None or game_day == target_date:
            rows.append(
                {
                    "Sport": "NHL",
                    "Game ID": game.get("game_id"),
                    "Season": int(game["season"]) if pd.notna(game["season"]) else None,
                    "Game Date": game_day,
                    "Game Time": format_game_time(game["game_date_dt"]),
                    "Sort Date": game["game_date_dt"],
                    "Game": f"{away} @ {home}",
                    "Away": away,
                    "Home": home,
                    "Away Score": int(away_score)
                    if completed and pd.notna(away_score)
                    else None,
                    "Home Score": int(home_score)
                    if completed and pd.notna(home_score)
                    else None,
                    "Actual Winner": actual_winner,
                    "Predicted Winner": predicted_winner,
                    "Actual Total": actual_total,
                    "Model Signal": model_signal_display(moneyline_edge),
                    "Edge Score": edge_score,
                    "Confidence": confidence,
                    "Side Edge": moneyline_edge,
                    "Scoring Edge": goal_environment,
                    "Early Edge": "First Period Pending",
                    "Side Result": side_result,
                    "Winner Result": side_result,
                    "Scoring Result": "No Signal",
                    "Model Margin": round(edge_margin, 2),
                    "Projected Total": round(projected_total, 2),
                    "League Total Baseline": round(league_total, 2),
                    "Margin Error": round(margin_error, 2) if margin_error is not None else None,
                    "Total Error": round(total_error, 2) if total_error is not None else None,
                    "Away Prior Games": away_state.games,
                    "Home Prior Games": home_state.games,
                    "Rest Edge": round(rest_edge, 2),
                    "Key Factors Summary": key_factors_summary(notes),
                    "Key Factors List": split_notes(notes),
                    "Agent Notes": notes,
                    "Status": status_for_game(game),
                }
            )

        if completed and pd.notna(away_score) and pd.notna(home_score):
            update_team(states, away, int(away_score), int(home_score))
            update_team(states, home, int(home_score), int(away_score))
            league_totals.append(int(away_score) + int(home_score))

    slate = pd.DataFrame(rows)
    if not slate.empty:
        slate = slate.sort_values(["Sort Date", "Game"])
    meta_date = target_date or (
        games["game_date_dt"].max().date() if not games.empty else pd.Timestamp.today().date()
    )
    return slate, {"season": season or meta_date.year, "slate_date": meta_date}


def build_current_slate(season=None, today=None, days_ahead=14, slate_date=None):
    target_date = slate_date or today or pd.Timestamp.today().date()
    games = load_nhl_current_season(
        season=season,
        today=target_date,
        days_ahead=days_ahead,
    )
    return build_slate_from_games(games, target_date=target_date, season=season)


def backtest_schedule(games: pd.DataFrame, season=None):
    games = prepare_schedule(games)
    completed = completed_games_for_lab(games)
    if completed.empty:
        return pd.DataFrame(), {"games": 0.0}
    results, _ = build_slate_from_games(completed, target_date=None, season=season)
    return prepare_historical_lab(results), historical_summary(results)


def build_current_season_lab(season=None, today=None):
    games = load_nhl_current_season(season=season, today=today)
    return backtest_schedule(games, season=season)


def build_historical_lab(games_csv, season=None):
    games = games_csv.copy() if isinstance(games_csv, pd.DataFrame) else pd.read_csv(games_csv)
    return backtest_schedule(games, season=season)


def prepare_historical_lab(results: pd.DataFrame) -> pd.DataFrame:
    return results


def historical_summary(results: pd.DataFrame) -> dict[str, float]:
    if results.empty:
        return {"games": 0.0, "moneyline_signal_games": 0.0, "moneyline_accuracy": 0.0}
    signals = results[results["Side Edge"] != "Pass"]
    graded = signals[signals["Side Result"].isin(["Correct", "Missed"])]
    accuracy = float((graded["Side Result"] == "Correct").mean()) if not graded.empty else 0.0
    return {
        "games": float(len(results)),
        "moneyline_signal_games": float(len(signals)),
        "moneyline_accuracy": round(accuracy, 4),
    }


def historical_summary_tables(results: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if results.empty:
        return {"core": pd.DataFrame(), "confidence": pd.DataFrame(), "rest": pd.DataFrame()}
    signals = results[results["Side Edge"] != "Pass"]
    rows = [
        {
            "Segment": "All Games",
            "Games": len(results),
            "Moneyline Signals": len(signals),
            "Moneyline Accuracy": historical_summary(results)["moneyline_accuracy"],
        }
    ]
    confidence_rows = []
    for confidence in ["A", "B", "C", "Pass"]:
        group = results[results["Confidence"] == confidence]
        if not group.empty:
            confidence_rows.append(
                {
                    "Confidence": confidence,
                    "Games": len(group),
                    "Moneyline Signals": len(group[group["Side Edge"] != "Pass"]),
                }
            )
    return {
        "core": pd.DataFrame(rows),
        "confidence": pd.DataFrame(confidence_rows),
        "rest": pd.DataFrame(),
    }
