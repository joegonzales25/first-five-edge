import argparse
from dataclasses import dataclass, field

import pandas as pd


NFLVERSE_GAMES_URL = (
    "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
)


@dataclass(frozen=True)
class ModelConfig:
    side_a: float = 11.0
    side_b: float = 8.0
    side_c: float = 5.0
    scoring_threshold: float = 2.5
    home_field: float = 1.8
    rest_weight: float = 0.15


@dataclass
class TeamState:
    games: int = 0
    wins: int = 0
    points_for: float = 0.0
    points_against: float = 0.0
    margin: float = 0.0
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
        return sum(self.recent_margins[-4:]) / len(self.recent_margins[-4:])


def load_games(season: int) -> pd.DataFrame:
    seasons = [season - 1, season]
    games = pd.read_csv(NFLVERSE_GAMES_URL)
    games = games[
        (games["season"].isin(seasons))
        & (games["game_type"] == "REG")
        & games["away_score"].notna()
        & games["home_score"].notna()
    ].copy()

    games["away_score"] = games["away_score"].astype(int)
    games["home_score"] = games["home_score"].astype(int)
    games["week"] = games["week"].astype(int)
    games = games.sort_values(["season", "week", "gameday", "game_id"])
    return games


def rating_for(team: TeamState, league_points: float) -> float:
    offense = team.points_for_avg(league_points) - league_points
    defense = league_points - team.points_against_avg(league_points)
    season_form = team.margin_avg() * 0.45
    recent_form = team.recent_form() * 0.25
    return offense * 0.55 + defense * 0.55 + season_form + recent_form


def confidence_from_margin(model_margin: float, config: ModelConfig) -> str:
    edge = abs(model_margin)
    if edge >= config.side_a:
        return "A"
    if edge >= config.side_b:
        return "B"
    if edge >= config.side_c:
        return "C"
    return "Pass"


def side_edge_label(model_margin: float, config: ModelConfig) -> str:
    confidence = confidence_from_margin(model_margin, config)
    if confidence == "Pass":
        return "Pass"
    side = "Home Edge" if model_margin > 0 else "Away Edge"
    return f"{side} ({confidence})"


def total_edge_label(
    projected_total: float,
    league_total: float,
    config: ModelConfig,
) -> str:
    delta = projected_total - league_total
    if delta >= config.scoring_threshold:
        return "High Scoring Environment"
    if delta <= -config.scoring_threshold:
        return "Low Scoring Environment"
    return "Neutral Scoring Environment"


def side_reasons(
    away: str,
    home: str,
    away_rating: float,
    home_rating: float,
    home_field: float,
    rest_edge: float,
    model_margin: float,
    config: ModelConfig,
) -> list[str]:
    reasons = []
    rating_gap = home_rating - away_rating
    leading_team = home if model_margin > 0 else away

    if abs(rating_gap) >= 6:
        stronger = home if rating_gap > 0 else away
        reasons.append(f"{stronger} holds a clear rolling team-strength edge")
    elif abs(rating_gap) >= 3:
        stronger = home if rating_gap > 0 else away
        reasons.append(f"{stronger} has a modest rolling team-strength edge")

    if home_field:
        reasons.append(f"{home} receives home-field context")

    if abs(rest_edge) >= 3:
        rested = home if rest_edge > 0 else away
        reasons.append(f"{rested} has a meaningful rest advantage")
    elif abs(rest_edge) >= 1:
        rested = home if rest_edge > 0 else away
        reasons.append(f"{rested} has a small rest advantage")

    if confidence_from_margin(model_margin, config) == "Pass":
        reasons.append("Side edge stays below signal threshold")
    else:
        reasons.append(f"{leading_team} clears the side-edge threshold")

    return reasons


def scoring_reasons(
    away: str,
    home: str,
    projected_total: float,
    league_total: float,
    total_edge: str,
    away_points_for: float,
    home_points_for: float,
    away_points_against: float,
    home_points_against: float,
) -> list[str]:
    reasons = []
    delta = projected_total - league_total

    if total_edge == "High Scoring Environment":
        reasons.append("Projected scoring sits above the rolling league baseline")
    elif total_edge == "Low Scoring Environment":
        reasons.append("Projected scoring sits below the rolling league baseline")
    else:
        reasons.append("Scoring projection stays near the rolling league baseline")

    if away_points_for > league_total / 2 + 2:
        reasons.append(f"{away} has an above-baseline scoring profile")
    if home_points_for > league_total / 2 + 2:
        reasons.append(f"{home} has an above-baseline scoring profile")
    if away_points_against > league_total / 2 + 2:
        reasons.append(f"{away} has allowed above-baseline scoring")
    if home_points_against > league_total / 2 + 2:
        reasons.append(f"{home} has allowed above-baseline scoring")

    if abs(delta) < 1.5:
        reasons.append("Total projection is not separated enough for a strong signal")

    return reasons


def agent_notes(side_notes: list[str], scoring_notes: list[str]) -> str:
    return "; ".join(side_notes + scoring_notes)


def calculate_edge_score(
    model_margin: float,
    projected_total: float,
    league_total: float,
    confidence: str,
) -> float:
    score = 45 + min(abs(model_margin) * 2.2, 35)
    scoring_delta = abs(projected_total - league_total)

    if scoring_delta >= 2.5:
        score += min(scoring_delta * 1.4, 10)

    if confidence == "A":
        score += 8
    elif confidence == "B":
        score += 5
    elif confidence == "C":
        score += 2

    return round(max(0, min(score, 95)), 1)


def model_signal(side_edge: str, scoring_edge: str) -> str:
    signals = []

    if side_edge != "Pass":
        signals.append(side_edge)
    if scoring_edge != "Neutral Scoring Environment":
        signals.append(scoring_edge)

    return " / ".join(signals) if signals else "Pass"


def update_team(
    states: dict[str, TeamState],
    team: str,
    points_for: int,
    points_against: int,
) -> None:
    state = states.setdefault(team, TeamState())
    margin = points_for - points_against
    state.games += 1
    state.wins += int(points_for > points_against)
    state.points_for += points_for
    state.points_against += points_against
    state.margin += margin
    state.recent_margins.append(float(margin))


def backtest_season(
    season: int = 2025,
    config: ModelConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, float]]:
    config = config or ModelConfig()
    games = load_games(season)
    states: dict[str, TeamState] = {}
    rows = []
    league_totals = []

    for _, game in games.iterrows():
        away = game["away_team"]
        home = game["home_team"]
        away_score = int(game["away_score"])
        home_score = int(game["home_score"])

        league_total = (
            sum(league_totals) / len(league_totals) if league_totals else 44.0
        )
        league_points = league_total / 2

        away_state = states.setdefault(away, TeamState())
        home_state = states.setdefault(home, TeamState())

        away_rating = rating_for(away_state, league_points)
        home_rating = rating_for(home_state, league_points)

        rest_edge = float(game.get("home_rest", 7) or 7) - float(
            game.get("away_rest", 7) or 7
        )
        home_field = config.home_field if game.get("location") == "Home" else 0.0
        model_margin = (
            home_rating
            - away_rating
            + home_field
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
        projected_total = (away_total_base + home_total_base) * 0.72 + (
            league_total * 0.28
        )

        predicted_winner = home if model_margin > 0 else away
        actual_winner = home if home_score > away_score else away
        actual_margin = home_score - away_score
        actual_total = away_score + home_score
        side_edge = side_edge_label(model_margin, config)
        total_edge = total_edge_label(projected_total, league_total, config)
        confidence = confidence_from_margin(model_margin, config)
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
            home_field,
            rest_edge,
            model_margin,
            config,
        )
        scoring_notes = scoring_reasons(
            away,
            home,
            projected_total,
            league_total,
            total_edge,
            away_state.points_for_avg(league_points),
            home_state.points_for_avg(league_points),
            away_state.points_against_avg(league_points),
            home_state.points_against_avg(league_points),
        )
        scoring_correct = (
            (total_edge == "High Scoring Environment" and actual_total > league_total)
            or (total_edge == "Low Scoring Environment" and actual_total < league_total)
            or total_edge == "Neutral Scoring Environment"
        )

        if int(game["season"]) == season:
            rows.append(
                {
                    "Game": f"{away} @ {home}",
                    "Season": int(game["season"]),
                    "Week": int(game["week"]),
                    "Away": away,
                    "Home": home,
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
    signal_results = results[results["Confidence"] != "Pass"]
    high_low = results[results["Scoring Edge"] != "Neutral Scoring Environment"]

    summary = {
        "side_a": config.side_a,
        "side_b": config.side_b,
        "side_c": config.side_c,
        "scoring_threshold": config.scoring_threshold,
        "games": float(len(results)),
        "winner_accuracy": round(results["Winner Correct"].mean(), 4),
        "side_signal_games": float(len(signal_results)),
        "side_signal_accuracy": round(signal_results["Winner Correct"].mean(), 4)
        if not signal_results.empty
        else 0.0,
        "margin_mae": round(results["Margin Error"].mean(), 2),
        "total_mae": round(results["Total Error"].mean(), 2),
        "scoring_signal_games": float(len(high_low)),
        "scoring_signal_accuracy": round(high_low["Scoring Correct"].mean(), 4)
        if not high_low.empty
        else 0.0,
    }

    return results, summary


def sweep_configs(season: int) -> pd.DataFrame:
    rows = []
    side_thresholds = [
        (8.0, 5.0, 2.5),
        (9.0, 6.0, 3.5),
        (10.0, 7.0, 4.0),
        (11.0, 8.0, 5.0),
    ]
    scoring_thresholds = [2.0, 2.5, 3.0, 3.5, 4.0]

    for side_a, side_b, side_c in side_thresholds:
        for scoring_threshold in scoring_thresholds:
            _, summary = backtest_season(
                season,
                ModelConfig(
                    side_a=side_a,
                    side_b=side_b,
                    side_c=side_c,
                    scoring_threshold=scoring_threshold,
                ),
            )
            rows.append(summary)

    return pd.DataFrame(rows).sort_values(
        ["side_signal_accuracy", "side_signal_games"],
        ascending=[False, False],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtest the NFL outcome/scoring test model."
    )
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--output", default=None)
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args()

    if args.sweep:
        sweep = sweep_configs(args.season)
        print("NFL Test Model Threshold Sweep")
        print(sweep.to_string(index=False))
        if args.output:
            sweep.to_csv(args.output, index=False)
            print(f"saved: {args.output}")
        return

    results, summary = backtest_season(args.season)

    print("NFL Test Model Backtest")
    for key, value in summary.items():
        print(f"{key}: {value}")

    if args.output:
        results.to_csv(args.output, index=False)
        print(f"saved: {args.output}")


if __name__ == "__main__":
    main()
