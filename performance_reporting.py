"""Read-only summaries for stored model and market results."""

import pandas as pd
from cfb_market import number


DIFFERENCE_BANDS = {
    "All": (None, None), "Under 1 point": (0, 1),
    "1 to under 3 points": (1, 3), "3 to under 5 points": (3, 5),
    "5+ points": (5, None),
}


def nfl_report_projection_error(row, track, signal):
    if str(row.get("status")).lower() not in {"final", "game over", "completed early"}:
        return None
    home, away = number(row.get("home_score")), number(row.get("away_score"))
    prefix = "challenger_" if track == "Challenger" else ""
    predicted = number(row.get(prefix + ("model_margin" if signal == "Side" else "projected_total")))
    if home is None or away is None or predicted is None:
        return None
    # Automated Challenger totals are not an independent forecast.
    if track == "Challenger" and signal == "Scoring":
        return None
    return abs(predicted - (home - away if signal == "Side" else home + away))


def filter_market_report(frame, start=None, end=None, track="Both", market="All",
                         result="All", band="All", version=None):
    if frame.empty:
        return frame.copy()
    selected = frame.copy()
    dates = pd.to_datetime(selected["Slate"], errors="coerce").dt.date
    mask = dates.notna()
    if start is not None:
        mask &= dates >= start
    if end is not None:
        mask &= dates <= end
    for column, value, all_value in [("Model Track", track, "Both"), ("Market", market, "All"),
                                      ("Result", result, "All")]:
        if value != all_value:
            mask &= selected[column] == value
    if version is not None:
        mask &= selected["Baseline Version"] == version
    low, high = DIFFERENCE_BANDS[band]
    differences = pd.to_numeric(selected["Projection Difference"], errors="coerce")
    if low is not None:
        mask &= differences >= low
    if high is not None:
        mask &= differences < high
    return selected.loc[mask].copy()


def market_statistics(frame):
    results = frame.get("Result", pd.Series(dtype=str))
    wins, losses, pushes = (int((results == value).sum()) for value in ("Cover", "Miss", "Push"))
    settled = results.isin(["Cover", "Miss", "Push"])
    units = pd.to_numeric(frame.get("Hypothetical Units", pd.Series(dtype=float)), errors="coerce")
    odds = pd.to_numeric(frame.get("American Odds", pd.Series(dtype=float)), errors="coerce")
    priced = settled & units.map(number).notna() & odds.map(number).notna() & (odds.abs() >= 100)
    count = int(priced.sum())
    net = float(units.loc[priced].sum()) if count else None
    return {
        "Record": f"{wins}-{losses}-{pushes}", "Settled": wins + losses + pushes,
        "Win Rate %": round(100 * wins / (wins + losses), 2) if wins + losses else None,
        "Pending": int((results == "Pending").sum()),
        "No Difference": int((results == "No Difference").sum()),
        "Missing Odds": int((odds.isna() | (odds.abs() < 100)).sum()),
        "Priced Settled": count, "Net Units": round(net, 3) if net is not None else None,
        "Return %": round(100 * net / count, 2) if count else None,
    }


def market_summary(frame):
    rows = []
    if frame.empty:
        return pd.DataFrame()
    for (track, model, baseline, release, market), group in frame.groupby(
            ["Model Track", "Model", "Baseline Version", "Market Version", "Market"], dropna=False):
        rows.append({"Track": track, "Model": model, "Baseline Version": baseline,
                     "Market Version": release, "Market": market, **market_statistics(group)})
    return pd.DataFrame(rows)


def difference_summary(frame):
    rows = []
    if frame.empty:
        return pd.DataFrame()
    for (track, model, baseline, release, market), group in frame.groupby(
            ["Model Track", "Model", "Baseline Version", "Market Version", "Market"], dropna=False):
        differences = pd.to_numeric(group["Projection Difference"], errors="coerce")
        for label, (low, high) in DIFFERENCE_BANDS.items():
            if label == "All":
                continue
            selected = group.loc[(differences >= low) & ((differences < high) if high is not None else True)]
            if not selected.empty:
                rows.append({"Track": track, "Model": model, "Baseline Version": baseline,
                             "Market Version": release, "Market": market,
                             "Difference": label, **market_statistics(selected)})
    return pd.DataFrame(rows)


def paired_market_summary(frame):
    """Pair only identical captured spreads; never multiply unmatched observations."""
    if frame.empty:
        return pd.DataFrame()
    spreads = frame.loc[frame["Market"] == "Spread"].copy()
    spreads["Book Key"] = spreads["Book"].str.replace(" ", "", regex=False).str.lower()
    keys = ["Sport", "Slate", "Game", "Baseline Version", "Market Version", "Book Key",
            "Captured At", "Market Line", "Rule"]
    baseline = spreads.loc[spreads["Model Track"] == "Baseline"]
    challenger = spreads.loc[spreads["Model Track"] == "Challenger"]
    if baseline.empty or challenger.empty:
        return pd.DataFrame()
    baseline = baseline.drop_duplicates(keys, keep=False)
    rows = []
    for version, group in challenger.groupby("Model", dropna=False):
        pairs = baseline.merge(group.drop_duplicates(keys, keep=False), on=keys, suffixes=(" Base", " Challenger"))
        # Keep baseline releases distinct when viewing multiple versions.
        for release, release_pairs in pairs.groupby(["Baseline Version", "Market Version"]):
            for label, agrees in [("Same side", True), ("Opposite sides", False)]:
                valid = ~release_pairs["Result Base"].eq("No Difference") & ~release_pairs["Result Challenger"].eq("No Difference")
                match = release_pairs["Comparison Base"] == release_pairs["Comparison Challenger"]
                subset = release_pairs.loc[valid & (match == agrees)]
                if subset.empty:
                    continue
                # A head-to-head record uses only decisions settled on both tracks.
                settled = subset["Result Base"].isin(["Cover", "Miss", "Push"]) & subset["Result Challenger"].isin(["Cover", "Miss", "Push"])
                subset = subset.loc[settled]
                if subset.empty:
                    continue
                row = {"Baseline Version": release[0], "Market Version": release[1],
                       "Challenger Version": version, "Selections": label, "Paired Games": len(subset)}
                for suffix, title in [(" Base", "Baseline"), (" Challenger", "Challenger")]:
                    columns = {name: subset[name + suffix].values for name in
                               ["Result", "Hypothetical Units", "American Odds"]}
                    stats = market_statistics(pd.DataFrame(columns))
                    row[f"{title} Record"] = stats["Record"]
                    row[f"{title} Units"] = stats["Net Units"]
                rows.append(row)
    return pd.DataFrame(rows)


def model_result_summary(details):
    if details.empty:
        return pd.DataFrame()
    rows = []
    for (track, model, baseline, release, signal), group in details.groupby(
            ["Model Track", "Model", "Baseline Version", "Market Version", "Signal"], dropna=False):
        result = group["Result"]
        correct, missed = int(result.eq("Correct").sum()), int(result.eq("Missed").sum())
        rows.append({"Track": track, "Model": model, "Baseline Version": baseline,
                     "Market Version": release, "Signal": signal, "Correct": correct,
                     "Missed": missed, "Push": int(result.eq("Push").sum()),
                     "Pending": int(result.eq("Pending").sum()),
                     "No Signal": int(result.eq("No Signal").sum()),
                     "Accuracy %": round(100 * correct / (correct + missed), 2) if correct + missed else None,
                     "Margin MAE": pd.to_numeric(group["Margin Error"], errors="coerce").mean() if signal == "Side" else None,
                     "Total MAE": pd.to_numeric(group["Total Error"], errors="coerce").mean() if signal == "Scoring" else None})
    return pd.DataFrame(rows)


def paired_model_summary(details):
    if details.empty:
        return pd.DataFrame()
    keys = ["Slate", "Game", "Signal", "Baseline Version", "Market Version"]
    baseline = details.loc[details["Model Track"] == "Baseline"].drop_duplicates(keys, keep=False)
    challenger = details.loc[details["Model Track"] == "Challenger"]
    rows = []
    for version, group in challenger.groupby("Model", dropna=False):
        pairs = baseline.merge(group.drop_duplicates(keys, keep=False), on=keys,
                               suffixes=(" Base", " Challenger"))
        for release, candidates in pairs.groupby(["Baseline Version", "Market Version", "Signal"]):
            settled = candidates["Result Base"].isin(["Correct", "Missed", "Push"]) & candidates["Result Challenger"].isin(["Correct", "Missed", "Push"])
            candidates = candidates.loc[settled]
            if candidates.empty:
                continue
            for track in ["Base", "Challenger"]:
                result = candidates["Result " + track]
                wins, losses = int(result.eq("Correct").sum()), int(result.eq("Missed").sum())
                rows.append({"Track": "Baseline" if track == "Base" else track,
                             "Baseline Version": release[0], "Market Version": release[1],
                             "Challenger Version": version, "Signal": release[2],
                             "Paired Games": len(candidates), "Correct": wins, "Missed": losses,
                             "Push": int(result.eq("Push").sum()),
                             "Accuracy %": round(100 * wins / (wins + losses), 2) if wins + losses else None})
    return pd.DataFrame(rows)
