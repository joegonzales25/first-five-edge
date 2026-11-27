"""Read-only summaries for stored model and market results."""

import pandas as pd
from cfb_market import number
from html import escape


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


def cbb_report_details(rows, signal="All", confidence="All"):
    details = []
    for row in rows:
        if row.get("snapshot_status") == "Not Tracked":
            continue
        for name in (["Side", "Scoring"] if signal == "All" else [signal]):
            side = name == "Side"
            pick = row.get("predicted_winner" if side else "scoring_edge")
            edge = row.get("side_edge" if side else "scoring_edge")
            if edge in (None, "", "Pass", "Neutral Scoring Environment", "Not Tracked"):
                continue
            if side and confidence != "All" and row.get("confidence") != confidence:
                continue
            result = row.get("side_result" if side else "scoring_result") or "Pending"
            details.append({
                "Slate": row.get("slate_date"), "Signal": name, "Model Track": "Baseline",
                "Game": row.get("game"), "Pick": pick,
                "Confidence": row.get("confidence") if side else "Uncalibrated",
                "Side Confidence": row.get("confidence") if side else None,
                "Score": row.get("edge_score") if side else row.get("projected_total"),
                "Result": result, "Status": row.get("status"), "Model": row.get("model_version"),
                "Baseline Version": row.get("model_version"), "Market Version": row.get("market_version"),
                "Evaluation Basis": "Outright winner" if side else "Internal scoring baseline",
                "Margin Error": row.get("margin_error") if side and str(row.get("status")).lower() == "final" else None,
                "Total Error": row.get("total_error") if not side and str(row.get("status")).lower() == "final" else None,
            })
    return pd.DataFrame(details)


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


def performance_cards_html(frame, kind):
    """Render the existing summaries without changing counts or selection scope."""
    summary = market_summary(frame) if kind == "market" else model_result_summary(frame)
    if summary.empty:
        return ""
    label_column = "Market" if kind == "market" else "Signal"
    labels = {"Side": "Full-Game Winner", "Scoring": "Scoring vs Internal Baseline",
              "First Half": "Halftime Leader", "Spread": "Spread", "Total": "Total"}
    order = {name: i for i, name in enumerate(labels)}
    records = sorted(summary.to_dict("records"), key=lambda r: (
        order.get(r[label_column], 99), 0 if r["Track"] == "Baseline" else 1,
        str(r["Model"]), str(r["Baseline Version"]), str(r["Market Version"])))

    def percentage(value):
        return f"{value:.1f}%" if pd.notna(value) else "N/A"

    cards = []
    for row in records:
        title = f"{row['Track']} | {labels.get(row[label_column], row[label_column])}"
        track_class = "baseline" if row["Track"] == "Baseline" else "challenger"
        versions = summary.loc[(summary["Track"] == row["Track"]) & (summary[label_column] == row[label_column])]
        version_label = (f'<p class="nfl-report-note">Model {escape(str(row["Model"]))} | Baseline {escape(str(row["Baseline Version"]))} | Market {escape(str(row["Market Version"]))}</p>'
                         if len(versions) > 1 else "")
        if kind == "market":
            body = (f'<tr><th scope="row">{escape(title)}{version_label}</th>'
                    f'<td><strong>{escape(row["Record"])}</strong></td>'
                    f'<td>{percentage(row["Win Rate %"])}</td><td>{row["Pending"]}</td></tr>')
        else:
            subset = frame.loc[(frame["Model Track"] == row["Track"]) & (frame["Model"] == row["Model"])
                               & (frame["Baseline Version"] == row["Baseline Version"])
                               & (frame["Market Version"] == row["Market Version"])
                               & (frame["Signal"] == row["Signal"])]
            segments = []
            for segment in ["Official", "Lean", "Watch"]:
                if "Segment" not in subset:
                    break
                results = subset.loc[subset["Segment"] == segment, "Result"]
                if results.empty:
                    continue
                correct, missed, pushes = (int(results.eq(v).sum()) for v in ["Correct", "Missed", "Push"])
                accuracy = 100 * correct / (correct + missed) if correct + missed else None
                segments.append(f'<tr><th scope="row">{segment}</th><td>{correct}-{missed}-{pushes}</td>'
                                f'<td>{percentage(accuracy)}</td><td>{int(results.eq("Pending").sum())}</td></tr>')
            notes = [f'{row[field]} {label}' for field, label in [("Pending", "pending"), ("No Signal", "no signal")] if row[field]]
            note_html = f'<p class="nfl-report-note">{" | ".join(notes)}</p>' if notes else ""
            segment_html = ('<table class="nfl-report-segments"><thead><tr><th>Segment</th><th>W-L-P</th><th>Accuracy</th><th>Pending</th></tr></thead>'
                            f'<tbody>{"".join(segments)}</tbody></table>') if segments else ""
            body = (f'<div class="nfl-report-value">{percentage(row["Accuracy %"])}<span> Accuracy</span></div>'
                    f'<p>{row["Correct"]} Correct | {row["Missed"]} Missed | {row["Push"]} Push</p>'
                    f'{note_html}'
                    f'{segment_html}')
        if kind == "market":
            cards.append(body)
        else:
            cards.append(f'<article class="nfl-report-card {track_class}"><h4>{escape(title)}</h4>{version_label}{body}</article>')
    if kind == "market":
        cards = ['<article class="nfl-report-card market"><h4>Model vs Market</h4>'
                 '<table class="nfl-market-summary"><colgroup><col style="width:38%">'
                 '<col style="width:25%"><col style="width:18%"><col style="width:19%"></colgroup>'
                 '<thead><tr><th>Track / Market</th><th>Win-Loss-Push</th><th>Win Rate</th><th>Pending</th></tr></thead>'
                 f'<tbody>{"".join(cards)}</tbody></table></article>']
    return '''<style>
.nfl-report-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:16px 0 24px;letter-spacing:0}
.nfl-report-card{min-width:0;padding:20px;background:#14212d;color:#f5f7fa;border:1px solid #46525e;border-top:4px solid #35b58b;border-radius:8px;overflow-wrap:anywhere}
.nfl-report-card.challenger{border-top-color:#35bad2}
.nfl-report-card h4{font-size:18px;line-height:1.4;margin:0 0 16px;color:#f5f7fa;letter-spacing:0}
.nfl-report-card p{font-size:14px;line-height:1.5;margin:10px 0}
.nfl-report-value{font-size:30px;font-weight:700;line-height:1.3}.nfl-report-value span{font-size:15px;font-weight:400}
.nfl-report-card .nfl-report-note{color:#c2ccd5;font-size:12px}
.nfl-report-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:16px 0}
.nfl-report-card.market{grid-column:1/-1}
.nfl-report-card .nfl-market-summary{width:100%;table-layout:fixed;border-collapse:collapse;background:transparent;font-size:13px}
.nfl-market-summary th,.nfl-market-summary td{padding:12px 3px;border-bottom:1px solid #46525e;text-align:right;color:#f5f7fa;overflow-wrap:anywhere}
.nfl-market-summary th:first-child{text-align:left}.nfl-market-summary tbody th{font-weight:400}
.nfl-market-summary thead th{font-size:11px;font-weight:400;color:#c2ccd5}
.nfl-report-metrics dt{font-size:12px;color:#c2ccd5}.nfl-report-metrics dd{font-size:16px;font-weight:600;margin:4px 0 0}
.nfl-report-card .nfl-report-segments{width:100%;table-layout:fixed;border-collapse:collapse;margin-top:16px;font-size:12px;background:transparent}
.nfl-report-segments th,.nfl-report-segments td{text-align:right;padding:8px 3px;border-bottom:1px solid #46525e;color:#f5f7fa}
.nfl-report-segments th:first-child{text-align:left}.nfl-report-segments thead th{font-weight:400;color:#c2ccd5}
@media(max-width:700px){.nfl-report-grid{grid-template-columns:minmax(0,1fr)}.nfl-report-card{padding:16px}}
</style><div class="nfl-report-grid">''' + "".join(cards) + "</div>"
