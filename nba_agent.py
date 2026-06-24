import pandas as pd

from basketball_model import backtest_csv, backtest_games


def build_historical_lab(games_csv, season=None):
    results, summary = backtest_csv(games_csv, league="NBA", season=season)
    return prepare_basketball_lab(results), summary


def backtest_schedule(games: pd.DataFrame, season=None):
    results, summary = backtest_games(games, league="NBA", season=season)
    return prepare_basketball_lab(results), summary


def split_notes(notes):
    if not notes:
        return []
    return [note.strip() for note in str(notes).split(";") if note.strip()]


def key_factors_summary(notes):
    factors = split_notes(notes)
    if not factors:
        return "Neutral model profile"
    return "; ".join(factors[:2])


def prepare_basketball_lab(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return results

    prepared = results.copy()
    prepared["Status"] = "Final"
    prepared["Game Time"] = prepared["Game Date"]
    prepared["Early Edge"] = "Model Pending"
    prepared["Key Factors Summary"] = prepared["Agent Notes"].apply(
        key_factors_summary
    )
    prepared["Key Factors List"] = prepared["Agent Notes"].apply(split_notes)
    prepared["Winner Result"] = prepared["Winner Correct"].apply(
        lambda value: "Correct" if bool(value) else "Missed"
    )
    prepared["Scoring Result"] = prepared["Scoring Correct"].apply(
        lambda value: "Correct" if bool(value) else "Missed"
    )
    return prepared
