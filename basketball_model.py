import argparse
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


SUPPORTED_LEAGUES = {"NBA", "WNBA", "CBB"}


@dataclass(frozen=True)
class BasketballModelConfig:
    league: str
    side_a: float
    side_b: float
    side_c: float
    min_a_games: int
    min_b_games: int
    min_c_games: int
    total_threshold: float
    home_court: float
    rest_weight: float
    recent_margin_weight: float
    pace_weight: float
    default_total: float


NBA_CONFIG = BasketballModelConfig(
    league="NBA",
    side_a=9.0,
    side_b=6.5,
    side_c=4.0,
    min_a_games=5,
    min_b_games=3,
    min_c_games=0,
    total_threshold=5.0,
    home_court=2.4,
    rest_weight=0.35,
    recent_margin_weight=0.28,
    pace_weight=0.18,
    default_total=226.0,
)


WNBA_CONFIG = BasketballModelConfig(
    league="WNBA",
    side_a=7.0,
    side_b=5.0,
    side_c=3.0,
    min_a_games=5,
    min_b_games=3,
    min_c_games=0,
    total_threshold=4.0,
    home_court=2.0,
    rest_weight=0.30,
    recent_margin_weight=0.20,
    pace_weight=0.16,
    default_total=164.0,
)


CBB_CONFIG = BasketballModelConfig(
    league="CBB",
    side_a=10.0,
    side_b=7.5,
    side_c=5.5,
    min_a_games=12,
    min_b_games=8,
    min_c_games=5,
    total_threshold=6.0,
    home_court=2.8,
    rest_weight=0.18,
    recent_margin_weight=0.22,
    pace_weight=0.14,
    default_total=145.0,
)


@dataclass
class TeamState:
    games: int = 0
    wins: int = 0
    points_for: float = 0.0
    points_against: float = 0.0
    margin: float = 0.0
    totals: list[float] = field(default_factory=list)
    recent_margins: list[float] = field(default_factory=list)

    def points_for_avg(self, league_points: float) -> float:
        if self.games == 0:
            return league_points
        return self.points_for / self.games

    def points_against_avg(self, league_points: float) -> float:
        if self.games == 0:
            return league_points
        return self.points_against / self.games

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


def config_for_league(league: str) -> BasketballModelConfig:
    normalized = str(league).upper()
    if normalized == "NBA":
        return NBA_CONFIG
    if normalized == "WNBA":
        return WNBA_CONFIG
    if normalized == "CBB":
        return CBB_CONFIG
    raise ValueError(f"unsupported league: {league}")


def normalize_games(games: pd.DataFrame) -> pd.DataFrame:
    required = {
        "season",
        "game_date",
        "away_team",
        "home_team",
        "away_score",
        "home_score",
    }
    missing = sorted(required - set(games.columns))
    if missing:
        raise ValueError(f"missing required columns: {', '.join(missing)}")

    normalized = games.copy()
    normalized["game_date_dt"] = pd.to_datetime(
        normalized["game_date"],
        errors="coerce",
    )
    normalized["away_score"] = pd.to_numeric(
        normalized["away_score"],
        errors="coerce",
    )
    normalized["home_score"] = pd.to_numeric(
        normalized["home_score"],
        errors="coerce",
    )
    normalized = normalized[
        normalized["away_score"].notna()
        & normalized["home_score"].notna()
        & normalized["game_date_dt"].notna()
    ].copy()
    normalized["away_score"] = normalized["away_score"].astype(int)
    normalized["home_score"] = normalized["home_score"].astype(int)

    sort_cols = ["season", "game_date_dt", "away_team", "home_team"]
    if "game_id" in normalized.columns:
        sort_cols.append("game_id")

    return normalized.sort_values(sort_cols)


def rating_for(
    team: TeamState,
    league_points: float,
    config: BasketballModelConfig,
) -> float:
    offense = team.points_for_avg(league_points) - league_points
    defense = league_points - team.points_against_avg(league_points)
    season_form = team.margin_avg() * 0.42
    recent_form = team.recent_form() * config.recent_margin_weight
    return offense * 0.50 + defense * 0.50 + season_form + recent_form


def confidence_from_margin(
    model_margin: float,
    config: BasketballModelConfig,
    away_games: int = 0,
    home_games: int = 0,
) -> str:
    edge = abs(model_margin)
    prior_games = min(away_games, home_games)
    if edge >= config.side_a and prior_games >= config.min_a_games:
        return "A"
    if edge >= config.side_b and prior_games >= config.min_b_games:
        return "B"
    if edge >= config.side_c and prior_games >= config.min_c_games:
        return "C"
    return "Pass"


def side_edge_label(
    model_margin: float,
    away: str,
    home: str,
    config: BasketballModelConfig,
    away_games: int = 0,
    home_games: int = 0,
) -> str:
    confidence = confidence_from_margin(
        model_margin,
        config,
        away_games,
        home_games,
    )
    if confidence == "Pass":
        return "Pass"
    team = home if model_margin > 0 else away
    return f"{team} Edge"


def total_edge_label(
    projected_total: float,
    league_total: float,
    config: BasketballModelConfig,
) -> str:
    delta = projected_total - league_total
    if delta >= config.total_threshold:
        return "High Scoring Environment"
    if delta <= -config.total_threshold:
        return "Low Scoring Environment"
    return "Neutral Scoring Environment"


def calculate_edge_score(
    model_margin: float,
    projected_total: float,
    league_total: float,
    confidence: str,
) -> float:
    score = 45 + min(abs(model_margin) * 2.5, 34)
    total_delta = abs(projected_total - league_total)

    if total_delta >= 4.0:
        score += min(total_delta * 1.2, 10)

    if confidence == "A":
        score += 8
    elif confidence == "B":
        score += 5
    elif confidence == "C":
        score += 2

    return round(max(0, min(score, 95)), 1)


def rounded_float(value, digits: int = 4) -> float:
    return float(round(value, digits))


def model_signal(side_edge: str, scoring_edge: str) -> str:
    signals = []
    if side_edge != "Pass":
        signals.append(side_edge)
    if scoring_edge != "Neutral Scoring Environment":
        signals.append(scoring_edge)
    return " / ".join(signals) if signals else "Pass"


def side_reasons(
    away: str,
    home: str,
    away_rating: float,
    home_rating: float,
    home_court: float,
    rest_edge: float,
    model_margin: float,
    config: BasketballModelConfig,
    away_games: int = 0,
    home_games: int = 0,
) -> list[str]:
    reasons = []
    rating_gap = home_rating - away_rating
    leading_team = home if model_margin > 0 else away

    if abs(rating_gap) >= 5:
        stronger = home if rating_gap > 0 else away
        reasons.append(f"{stronger} holds a clear rolling team-strength edge")
    elif abs(rating_gap) >= 2.5:
        stronger = home if rating_gap > 0 else away
        reasons.append(f"{stronger} has a modest rolling team-strength edge")

    if home_court:
        reasons.append(f"{home} receives home-court context")

    if abs(rest_edge) >= 2:
        rested = home if rest_edge > 0 else away
        reasons.append(f"{rested} has a meaningful rest advantage")
    elif abs(rest_edge) >= 1:
        rested = home if rest_edge > 0 else away
        reasons.append(f"{rested} has a small rest advantage")

    confidence = confidence_from_margin(
        model_margin,
        config,
        away_games,
        home_games,
    )
    prior_games = min(away_games, home_games)
    if confidence == "Pass":
        reasons.append("Side edge stays below signal threshold")
    else:
        reasons.append(f"{leading_team} clears the side-edge threshold")

    if prior_games < config.min_b_games:
        reasons.append("Limited team history keeps confidence capped early")

    return reasons


def scoring_reasons(
    away: str,
    home: str,
    projected_total: float,
    league_total: float,
    total_edge: str,
    away_total_avg: float,
    home_total_avg: float,
) -> list[str]:
    reasons = []
    delta = projected_total - league_total

    if total_edge == "High Scoring Environment":
        reasons.append("Projected scoring sits above the rolling league baseline")
    elif total_edge == "Low Scoring Environment":
        reasons.append("Projected scoring sits below the rolling league baseline")
    else:
        reasons.append("Scoring projection stays near the rolling league baseline")

    if away_total_avg > league_total + 4:
        reasons.append(f"{away} games have recently played above baseline")
    if home_total_avg > league_total + 4:
        reasons.append(f"{home} games have recently played above baseline")
    if away_total_avg < league_total - 4:
        reasons.append(f"{away} games have recently played below baseline")
    if home_total_avg < league_total - 4:
        reasons.append(f"{home} games have recently played below baseline")

    if abs(delta) < 2.0:
        reasons.append("Total projection is not separated enough for a strong signal")

    return reasons


def agent_notes(side_notes: list[str], scoring_notes: list[str]) -> str:
    return "; ".join(side_notes + scoring_notes)


def update_team(
    states: dict[str, TeamState],
    team: str,
    points_for: int,
    points_against: int,
) -> None:
    state = states.setdefault(team, TeamState())
    margin = points_for - points_against
    total = points_for + points_against
    state.games += 1
    state.wins += int(points_for > points_against)
    state.points_for += points_for
    state.points_against += points_against
    state.margin += margin
    state.totals.append(float(total))
    state.recent_margins.append(float(margin))


def rest_edge_for_game(game: pd.Series) -> float:
    if "home_rest" in game and "away_rest" in game:
        try:
            home_rest = game.get("home_rest")
            away_rest = game.get("away_rest")
            home_value = float(home_rest) if pd.notna(home_rest) else 0.0
            away_value = float(away_rest) if pd.notna(away_rest) else 0.0
            return home_value - away_value
        except Exception:
            return 0.0
    return 0.0


def backtest_games(
    games: pd.DataFrame,
    league: str,
    season: int | None = None,
    config: BasketballModelConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, float]]:
    config = config or config_for_league(league)
    if config.league not in SUPPORTED_LEAGUES:
        raise ValueError(f"unsupported league: {config.league}")

    normalized = normalize_games(games)
    if season is not None:
        normalized = normalized[normalized["season"].astype(int) <= int(season)].copy()

    states: dict[str, TeamState] = {}
    rows = []
    league_totals = []

    for _, game in normalized.iterrows():
        game_season = int(game["season"])
        away = game["away_team"]
        home = game["home_team"]
        away_score = int(game["away_score"])
        home_score = int(game["home_score"])
        actual_total = away_score + home_score

        league_total = (
            sum(league_totals) / len(league_totals)
            if league_totals
            else config.default_total
        )
        league_points = league_total / 2

        away_state = states.setdefault(away, TeamState())
        home_state = states.setdefault(home, TeamState())
        away_rating = rating_for(away_state, league_points, config)
        home_rating = rating_for(home_state, league_points, config)

        rest_edge = rest_edge_for_game(game)
        model_margin = (
            home_rating
            - away_rating
            + config.home_court
            + (rest_edge * config.rest_weight)
        )

        away_total_base = (
            away_state.points_for_avg(league_points)
            + home_state.points_against_avg(league_points)
        ) / 2
        home_total_base = (
            home_state.points_for_avg(league_points)
            + away_state.points_against_avg(league_points)
        ) / 2
        recent_total_context = (
            away_state.total_avg(league_total) + home_state.total_avg(league_total)
        ) / 2
        recent_total_weight = config.pace_weight
        matchup_total_weight = 0.78 - recent_total_weight
        projected_total = (
            (away_total_base + home_total_base) * matchup_total_weight
            + league_total * 0.22
            + recent_total_context * recent_total_weight
        )

        predicted_winner = home if model_margin > 0 else away
        actual_winner = home if home_score > away_score else away
        actual_margin = home_score - away_score
        side_edge = side_edge_label(
            model_margin,
            away,
            home,
            config,
            away_state.games,
            home_state.games,
        )
        total_edge = total_edge_label(projected_total, league_total, config)
        confidence = confidence_from_margin(
            model_margin,
            config,
            away_state.games,
            home_state.games,
        )
        edge_score = calculate_edge_score(
            model_margin,
            projected_total,
            league_total,
            confidence,
        )
        side_notes = side_reasons(
            away,
            home,
            away_rating,
            home_rating,
            config.home_court,
            rest_edge,
            model_margin,
            config,
            away_state.games,
            home_state.games,
        )
        scoring_notes = scoring_reasons(
            away,
            home,
            projected_total,
            league_total,
            total_edge,
            away_state.total_avg(league_total),
            home_state.total_avg(league_total),
        )
        scoring_correct = (
            (total_edge == "High Scoring Environment" and actual_total > league_total)
            or (total_edge == "Low Scoring Environment" and actual_total < league_total)
            or total_edge == "Neutral Scoring Environment"
        )

        if season is None or game_season == int(season):
            rows.append(
                {
                    "Sport": config.league,
                    "Game": f"{away} @ {home}",
                    "Season": game_season,
                    "Game Date": game["game_date_dt"].date().isoformat(),
                    "Away": away,
                    "Home": home,
                    "Away Prior Games": away_state.games,
                    "Home Prior Games": home_state.games,
                    "Min Prior Games": min(away_state.games, home_state.games),
                    "Rest Edge": round(rest_edge, 2),
                    "Away Score": away_score,
                    "Home Score": home_score,
                    "Actual Winner": actual_winner,
                    "Predicted Winner": predicted_winner,
                    "Winner Correct": predicted_winner == actual_winner,
                    "Model Signal": model_signal(side_edge, total_edge),
                    "Edge Score": edge_score,
                    "Model Margin": round(model_margin, 2),
                    "Actual Margin": actual_margin,
                    "Margin Error": round(abs(model_margin - actual_margin), 2),
                    "Side Edge": side_edge,
                    "Confidence": confidence,
                    "Projected Total": round(projected_total, 2),
                    "Actual Total": actual_total,
                    "Total Error": round(abs(projected_total - actual_total), 2),
                    "Scoring Edge": total_edge,
                    "Scoring Correct": scoring_correct,
                    "League Total Baseline": round(league_total, 2),
                    "Agent Notes": agent_notes(side_notes, scoring_notes),
                }
            )

        update_team(states, away, away_score, home_score)
        update_team(states, home, home_score, away_score)
        league_totals.append(actual_total)

    results = pd.DataFrame(rows)
    if results.empty:
        return results, empty_summary(config)

    signal_results = results[results["Confidence"] != "Pass"]
    high_low = results[results["Scoring Edge"] != "Neutral Scoring Environment"]

    summary = {
        "league": config.league,
        "side_a": config.side_a,
        "side_b": config.side_b,
        "side_c": config.side_c,
        "min_a_games": config.min_a_games,
        "min_b_games": config.min_b_games,
        "min_c_games": config.min_c_games,
        "total_threshold": config.total_threshold,
        "recent_margin_weight": config.recent_margin_weight,
        "games": float(len(results)),
        "winner_accuracy": rounded_float(results["Winner Correct"].mean(), 4),
        "side_signal_games": float(len(signal_results)),
        "side_signal_accuracy": rounded_float(
            signal_results["Winner Correct"].mean(),
            4,
        )
        if not signal_results.empty
        else 0.0,
        "margin_mae": rounded_float(results["Margin Error"].mean(), 2),
        "total_mae": rounded_float(results["Total Error"].mean(), 2),
        "scoring_signal_games": float(len(high_low)),
        "scoring_signal_accuracy": rounded_float(
            high_low["Scoring Correct"].mean(),
            4,
        )
        if not high_low.empty
        else 0.0,
    }
    return results, summary


def empty_summary(config: BasketballModelConfig) -> dict[str, float]:
    return {
        "league": config.league,
        "side_a": config.side_a,
        "side_b": config.side_b,
        "side_c": config.side_c,
        "min_a_games": float(config.min_a_games),
        "min_b_games": float(config.min_b_games),
        "min_c_games": float(config.min_c_games),
        "total_threshold": config.total_threshold,
        "recent_margin_weight": config.recent_margin_weight,
        "games": 0.0,
        "winner_accuracy": 0.0,
        "side_signal_games": 0.0,
        "side_signal_accuracy": 0.0,
        "margin_mae": 0.0,
        "total_mae": 0.0,
        "scoring_signal_games": 0.0,
        "scoring_signal_accuracy": 0.0,
    }


def backtest_csv(
    csv_path: str | Path,
    league: str,
    season: int | None = None,
) -> tuple[pd.DataFrame, dict[str, float]]:
    games = pd.read_csv(csv_path)
    return backtest_games(games, league=league, season=season)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtest the NBA/WNBA outcome and scoring-environment model."
    )
    parser.add_argument("--league", choices=sorted(SUPPORTED_LEAGUES), required=True)
    parser.add_argument("--games-csv", required=True)
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    results, summary = backtest_csv(
        args.games_csv,
        league=args.league,
        season=args.season,
    )

    print(f"{args.league} Test Model Backtest")
    for key, value in summary.items():
        print(f"{key}: {value}")

    if args.output:
        results.to_csv(args.output, index=False)
        print(f"saved: {args.output}")


if __name__ == "__main__":
    main()
