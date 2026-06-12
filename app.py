import streamlit as st
from datetime import date
from html import escape
from mlb_agent import get_today_games

APP_VERSION = "2.1.0"

team_logo_map = {
    "Arizona Diamondbacks": "https://www.mlbstatic.com/team-logos/109.svg",
    "Athletics": "https://www.mlbstatic.com/team-logos/133.svg",
    "Atlanta Braves": "https://www.mlbstatic.com/team-logos/144.svg",
    "Baltimore Orioles": "https://www.mlbstatic.com/team-logos/110.svg",
    "Boston Red Sox": "https://www.mlbstatic.com/team-logos/111.svg",
    "Chicago Cubs": "https://www.mlbstatic.com/team-logos/112.svg",
    "Chicago White Sox": "https://www.mlbstatic.com/team-logos/145.svg",
    "Cincinnati Reds": "https://www.mlbstatic.com/team-logos/113.svg",
    "Cleveland Guardians": "https://www.mlbstatic.com/team-logos/114.svg",
    "Colorado Rockies": "https://www.mlbstatic.com/team-logos/115.svg",
    "Detroit Tigers": "https://www.mlbstatic.com/team-logos/116.svg",
    "Houston Astros": "https://www.mlbstatic.com/team-logos/117.svg",
    "Kansas City Royals": "https://www.mlbstatic.com/team-logos/118.svg",
    "Los Angeles Angels": "https://www.mlbstatic.com/team-logos/108.svg",
    "Los Angeles Dodgers": "https://www.mlbstatic.com/team-logos/119.svg",
    "Miami Marlins": "https://www.mlbstatic.com/team-logos/146.svg",
    "Milwaukee Brewers": "https://www.mlbstatic.com/team-logos/158.svg",
    "Minnesota Twins": "https://www.mlbstatic.com/team-logos/142.svg",
    "New York Mets": "https://www.mlbstatic.com/team-logos/121.svg",
    "New York Yankees": "https://www.mlbstatic.com/team-logos/147.svg",
    "Oakland Athletics": "https://www.mlbstatic.com/team-logos/133.svg",
    "Philadelphia Phillies": "https://www.mlbstatic.com/team-logos/143.svg",
    "Pittsburgh Pirates": "https://www.mlbstatic.com/team-logos/134.svg",
    "San Diego Padres": "https://www.mlbstatic.com/team-logos/135.svg",
    "San Francisco Giants": "https://www.mlbstatic.com/team-logos/137.svg",
    "Seattle Mariners": "https://www.mlbstatic.com/team-logos/136.svg",
    "St. Louis Cardinals": "https://www.mlbstatic.com/team-logos/138.svg",
    "Tampa Bay Rays": "https://www.mlbstatic.com/team-logos/139.svg",
    "Texas Rangers": "https://www.mlbstatic.com/team-logos/140.svg",
    "Toronto Blue Jays": "https://www.mlbstatic.com/team-logos/141.svg",
    "Washington Nationals": "https://www.mlbstatic.com/team-logos/120.svg",
}

st.set_page_config(
    page_title="First Five Edge",
    page_icon="⚾",
    layout="wide"
)

st.html("""
<style>
.game-card {
    border-radius: 18px;
    border: 1px solid #d1d5db;
    border-left: 8px solid #9CA3AF;
    padding: 22px;
    margin-bottom: 6px;
    background: #ffffff;
}

.badge {
    display: inline-block;
    padding: 6px 12px;
    border-radius: 999px;
    color: white;
    font-weight: 700;
    font-size: 14px;
    margin-right: 8px;
    margin-bottom: 8px;
}
.badge-nrfi { background: #16a34a; }
.badge-yrfi { background: #dc2626; }
.badge-f5 { background: #2563eb; }
.badge-pass { background: #6b7280; }
.badge-edge { background: #111827; }

.logo-row {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-top: 4px;
    margin-bottom: 6px;
    flex-wrap: wrap;
}
.logo-team {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-height: 42px;
}
.team-logo {
    width: 38px;
    height: 38px;
    object-fit: contain;
}
.team-logo-name {
    font-size: 15px;
    font-weight: 700;
    color: #374151;
}
.logo-at {
    color: #6b7280;
    font-weight: 800;
}

.game-title {
    font-size: 28px;
    font-weight: 800;
    margin-top: 8px;
    margin-bottom: 4px;
}
.muted {
    color: #6b7280;
    font-size: 15px;
    margin-bottom: 14px;
}
.recommendation {
    font-size: 18px;
    margin-top: 10px;
    margin-bottom: 10px;
}
.market-watch {
    margin: 12px 0 14px 0;
    padding: 10px 12px;
    border-left: 4px solid #2563eb;
    background: #f8fafc;
}
.market-heading {
    font-size: 14px;
    font-weight: 800;
    color: #475569;
    margin-bottom: 4px;
}
.market-pick {
    font-size: 18px;
    font-weight: 900;
    color: #111827;
    margin-bottom: 6px;
}
.market-why {
    font-size: 13px;
    font-weight: 800;
    color: #475569;
    margin-bottom: 4px;
}
.key-factors {
    margin: 0 0 12px 0;
}
.decision-stack {
    display: grid;
    gap: 6px;
    margin: 10px 0 12px 0;
    color: #111827;
    font-size: 16px;
}
.decision-line {
    font-weight: 700;
    line-height: 1.3;
}
.reason-stack {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 6px 14px;
    margin: 0 0 14px 0;
    color: #374151;
    font-size: 14px;
}
.reason-item {
    display: flex;
    align-items: flex-start;
    gap: 7px;
    line-height: 1.3;
}
.reason-check {
    color: #16a34a;
    font-weight: 900;
    line-height: 1.2;
}
.model-favorite {
    background: linear-gradient(90deg, #064e3b, #047857);
    border-radius: 18px;
    padding: 22px;
    margin-bottom: 22px;
    color: white;
}
.model-label {
    font-size: 13px;
    letter-spacing: 1.5px;
    font-weight: 800;
    color: #bbf7d0;
}
.model-pick {
    font-size: 28px;
    font-weight: 900;
    margin-top: 6px;
}

div[data-testid="stExpander"] {
    margin-top: -4px;
    margin-bottom: 18px;
}
</style>
""")


def get_badge_class(row):
    if row["Lean"] in ["Strong NRFI", "NRFI"]:
        return "badge-nrfi"
    if row["Lean"] in ["Strong YRFI", "YRFI"]:
        return "badge-yrfi"
    if row["F5 Edge"] != "F5 Pass":
        return "badge-f5"
    return "badge-pass"


def split_game_name(game_name):
    if " @ " in game_name:
        away, home = game_name.split(" @ ", 1)
        return away, home
    return "Away", "Home"


def render_team_logo(team_name):
    logo_url = team_logo_map.get(team_name)
    if not logo_url:
        return ""

    return (
        f'<img class="team-logo" src="{escape(logo_url)}" '
        f'alt="{escape(team_name)} logo" loading="lazy">'
    )


def render_logo_matchup(away_team, home_team):
    away_logo = render_team_logo(away_team)
    home_logo = render_team_logo(home_team)

    return f"""
    <div class="logo-row">
        <div class="logo-team">
            {away_logo}
            <span class="team-logo-name">{escape(away_team)}</span>
        </div>
        <span class="logo-at">@</span>
        <div class="logo-team">
            {home_logo}
            <span class="team-logo-name">{escape(home_team)}</span>
        </div>
    </div>
    """


def build_reason_stack(row):
    reasons = [
        note.strip()
        for note in str(row["Agent Notes"]).split(";")
        if note.strip()
    ]

    if not reasons:
        reasons = ["Neutral model profile"]

    lean = row["Lean"]
    if lean == "Pass":
        reasons.append("Model lean remains in pass range")
    elif lean != "Pending":
        reasons.append(f"{lean} threshold cleared")

    if row["F5 Edge"] != "F5 Pass":
        reasons.append(row["F5 Edge"])

    bullpen_status = f'{row["Away Bullpen Status"]} / {row["Home Bullpen Status"]}'
    if bullpen_status != "Normal / Normal":
        reasons.append(f"Bullpen watch: {bullpen_status}")

    reasons.append(f'Confidence {row["Confidence"]}')

    return reasons[:5]


def render_reason_stack(row):
    items = "".join(
        f"""
        <div class="reason-item">
            <span class="reason-check">&#10003;</span>
            <span>{escape(reason)}</span>
        </div>
        """
        for reason in build_reason_stack(row)
    )

    return f'<div class="reason-stack">{items}</div>'


def get_row_value(row, column_name, default="Pass"):
    value = row.get(column_name, default)
    if value is None or value == "":
        return default
    return value


def is_no_edge_pick(pick):
    return str(pick).strip() in ["Pass", "No Edge", "F5 Pass"]


def format_decision_pick(pick, confidence):
    if is_no_edge_pick(pick):
        return "No Edge"

    if is_no_edge_pick(confidence) or confidence in [None, ""]:
        return str(pick)

    return f"{pick} ({confidence})"


def get_first_existing_value(row, column_names):
    for column_name in column_names:
        value = row.get(column_name)
        if value not in [None, "", "N/A"]:
            return value
    return None


def format_rank_metric(row, value_column, rank_columns, rank_scope):
    value = get_row_value(row, value_column, "N/A")
    rank = get_first_existing_value(row, rank_columns)

    if rank is None:
        return value

    return f"{value} (#{rank} {rank_scope})"


def get_numeric_value(row, column_name):
    value = get_row_value(row, column_name, "")
    try:
        return float(str(value).replace("%", "").strip())
    except ValueError:
        return None


def build_market_watch(row):
    away_fatigue = get_numeric_value(row, "Away Bullpen Fatigue")
    home_fatigue = get_numeric_value(row, "Home Bullpen Fatigue")
    starter_margin = get_numeric_value(row, "Starter Edge Margin") or 0
    bullpen_margin = get_numeric_value(row, "Bullpen Edge Margin") or 0
    away_era = get_numeric_value(row, "Away ERA")
    home_era = get_numeric_value(row, "Home ERA")
    away_whip = get_numeric_value(row, "Away WHIP")
    home_whip = get_numeric_value(row, "Home WHIP")

    both_bullpens_tired = (
        away_fatigue is not None and home_fatigue is not None
        and away_fatigue >= 8 and home_fatigue >= 8
    )
    both_bullpens_fresh = (
        away_fatigue is not None and home_fatigue is not None
        and away_fatigue <= 3 and home_fatigue <= 3
    )
    strong_starting_pitching = (
        away_era is not None and home_era is not None
        and away_whip is not None and home_whip is not None
        and ((away_era + home_era) / 2) <= 3.75
        and ((away_whip + home_whip) / 2) <= 1.22
    )

    if both_bullpens_tired:
        return "Over Watch", [
            "Both bullpens fatigued",
            "Elevated late-game scoring risk",
        ]

    if both_bullpens_fresh and strong_starting_pitching:
        return "Under Watch", [
            "Fresh bullpens",
            "Strong starting pitching",
        ]

    if starter_margin >= 8 and bullpen_margin < 6:
        return "Live Betting Watch", [
            "Strong starter edge",
            "Weak bullpen edge",
        ]

    return "No Market Edge", [
        "No meaningful market signal detected",
    ]


def render_market_watch(row):
    market_pick, reasons = build_market_watch(row)
    reason_items = "".join(
        f"""
        <div class="reason-item">
            <span class="reason-check">&#10003;</span>
            <span>{escape(reason)}</span>
        </div>
        """
        for reason in reasons[:4]
    )

    return f"""
    <div class="market-watch">
        <div class="market-heading">📈 Market Watch</div>
        <div class="market-pick">{escape(market_pick)}</div>
        <div class="market-why">Why?</div>
        <div class="reason-stack">{reason_items}</div>
    </div>
    """


def build_key_factors(row):
    factors = []

    starter_winner = get_row_value(row, "Starter Edge Winner", "Pass")
    starter_margin = get_numeric_value(row, "Starter Edge Margin")
    if not is_no_edge_pick(starter_winner) and starter_margin is not None and starter_margin >= 6:
        factors.append(f"Starter edge: {starter_winner} +{starter_margin:g}")

    offensive_winner = get_row_value(row, "Offensive Edge Winner", "Pass")
    offensive_margin = get_numeric_value(row, "Offensive Edge Margin")
    if not is_no_edge_pick(offensive_winner) and offensive_margin is not None and offensive_margin >= 5:
        factors.append(f"Offensive edge: {offensive_winner} +{offensive_margin:g}")

    bullpen_winner = get_row_value(row, "Bullpen Edge Winner", "Pass")
    bullpen_margin = get_numeric_value(row, "Bullpen Edge Margin")
    if not is_no_edge_pick(bullpen_winner) and bullpen_margin is not None and bullpen_margin >= 5:
        factors.append(f"Bullpen edge: {bullpen_winner} +{bullpen_margin:g}")

    if is_no_edge_pick(get_row_value(row, "First Inning Pick", "Pass")):
        factors.append("No clear first-inning edge")

    away_fatigue = get_numeric_value(row, "Away Bullpen Fatigue")
    home_fatigue = get_numeric_value(row, "Home Bullpen Fatigue")
    if (
        (away_fatigue is not None and away_fatigue >= 8)
        or (home_fatigue is not None and home_fatigue >= 8)
    ):
        factors.append("Bullpen fatigue watch")

    if not factors:
        factors.append("No major model imbalance detected")

    return factors[:3]


def render_key_factors(row):
    factor_items = "".join(
        f"""
        <div class="reason-item">
            <span class="reason-check">&#10003;</span>
            <span>{escape(factor)}</span>
        </div>
        """
        for factor in build_key_factors(row)
    )

    return f"""
    <div class="key-factors">
        <div class="market-heading">Key Factors</div>
        <div class="reason-stack">{factor_items}</div>
    </div>
    """


@st.cache_data(ttl=900)
def load_games(selected_date):
    return get_today_games(selected_date.isoformat())


st.title("⚾ First Five Edge")
st.caption("MLB YRFI / NRFI • First 5 • Bullpen Fatigue Intelligence")

st.sidebar.title("Controls")
st.sidebar.caption(f"Version {APP_VERSION}")
selected_date = st.sidebar.date_input("Slate Date", value=date.today())
st.sidebar.divider()
st.sidebar.subheader("Data Sources")

st.sidebar.markdown("""
**Game Schedule / Probable Pitchers**  
MLB Stats API

**Team Records**  
MLB Standings API

**Pitcher Season Stats**  
MLB Stats API

**Bullpen Fatigue**  
MLB Game Boxscore API

**Team 1st Inning Offense**  
MLB Linescore API

**Pitcher 1st Inning Metrics**  
Baseball Savant / Statcast
""")

if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

view = st.sidebar.radio(
    "View",
    ["All Games", "Model Favorites", "NRFI", "YRFI", "F5", "Bullpen Watch"]
)

min_edge = st.sidebar.slider("Minimum Edge Score", 0, 100, 0)

games = load_games(selected_date)

if games.empty:
    st.warning("No MLB games found for selected date.")
    st.stop()

games = games.copy()
games["Edge Score"] = games["Edge Score"].fillna(0)

filtered = games[games["Edge Score"] >= min_edge].copy()

if view == "Model Favorites":
    filtered = filtered[filtered["Recommendation"] != "Pass"]
elif view == "NRFI":
    filtered = filtered[filtered["Lean"].isin(["NRFI", "Strong NRFI"])]
elif view == "YRFI":
    filtered = filtered[filtered["Lean"].isin(["YRFI", "Strong YRFI"])]
elif view == "F5":
    filtered = filtered[filtered["F5 Edge"] != "F5 Pass"]
elif view == "Bullpen Watch":
    filtered = filtered[
        (filtered["Away Bullpen Fatigue"] >= 8) |
        (filtered["Home Bullpen Fatigue"] >= 8)
    ]

filtered = filtered.sort_values("Edge Score", ascending=False, na_position="last")

st.subheader(f"Slate: {selected_date}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Games", len(games))
c2.metric("Model Favorites", len(games[games["Recommendation"] != "Pass"]))
c3.metric("NRFI Looks", len(games[games["Lean"].isin(["NRFI", "Strong NRFI"])]))
c4.metric("F5 Edges", len(games[games["F5 Edge"] != "F5 Pass"]))

st.divider()

model_favorites = games[games["Recommendation"] != "Pass"].sort_values(
    "Edge Score",
    ascending=False,
    na_position="last"
)

if not model_favorites.empty:
    top = model_favorites.iloc[0]

    st.html(f"""
    <div class="model-favorite">
        <div class="model-label">MODEL FAVORITE</div>
        <div class="model-pick">{top["Recommendation"]}</div>
        <h2>{top["Game"]}</h2>
        <p>{top["Game Time"]} • {top["Status"]}</p>
        <span class="badge badge-edge">Edge {top["Edge Score"]}</span>
        <span class="badge badge-edge">Confidence {top["Confidence"]}</span>
        <span class="badge badge-edge">{top["Lean"]}</span>
        <p style="margin-top: 14px;">{top["Agent Notes"]}</p>
    </div>
    """)

st.subheader("Game Cards")

if filtered.empty:
    st.info("No games match the selected filters.")
else:
    for _, row in filtered.iterrows():
        away_team, home_team = split_game_name(row["Game"])
        logo_matchup = render_logo_matchup(away_team, home_team)
        market_watch = render_market_watch(row)
        key_factors = render_key_factors(row)
        first_inning_pick = get_row_value(row, "First Inning Pick")
        first_inning_confidence = get_row_value(row, "First Inning Confidence")
        f5_pick = get_row_value(row, "F5 Pick")
        f5_confidence = get_row_value(row, "F5 Confidence")
        full_game_pick = get_row_value(row, "Full Game Pick")
        full_game_confidence = get_row_value(row, "Full Game Confidence")
        first_inning_display = format_decision_pick(
            first_inning_pick,
            first_inning_confidence,
        )
        f5_display = format_decision_pick(f5_pick, f5_confidence)
        full_game_display = format_decision_pick(
            full_game_pick,
            full_game_confidence,
        )
        away_pitcher_yrfi = get_row_value(row, "Away Pitcher YRFI %", "N/A")
        home_pitcher_yrfi = get_row_value(row, "Home Pitcher YRFI %", "N/A")
        away_offense_yrfi = get_row_value(row, "Away Offense YRFI %", "N/A")
        home_offense_yrfi = get_row_value(row, "Home Offense YRFI %", "N/A")
        away_pitcher_yrfi_display = format_rank_metric(
            row,
            "Away Pitcher YRFI %",
            [
                "Away Pitcher YRFI Rank",
                "Away Pitcher YRFI % Rank",
                "Away Pitcher YRFI SP Rank",
                "Away Pitcher YRFI % SP Rank",
            ],
            "SP",
        )
        home_pitcher_yrfi_display = format_rank_metric(
            row,
            "Home Pitcher YRFI %",
            [
                "Home Pitcher YRFI Rank",
                "Home Pitcher YRFI % Rank",
                "Home Pitcher YRFI SP Rank",
                "Home Pitcher YRFI % SP Rank",
            ],
            "SP",
        )
        away_offense_yrfi_display = format_rank_metric(
            row,
            "Away Offense YRFI %",
            [
                "Away Offense YRFI Rank",
                "Away Offense YRFI % Rank",
                "Away Offense YRFI MLB Rank",
                "Away Offense YRFI % MLB Rank",
            ],
            "MLB",
        )
        home_offense_yrfi_display = format_rank_metric(
            row,
            "Home Offense YRFI %",
            [
                "Home Offense YRFI Rank",
                "Home Offense YRFI % Rank",
                "Home Offense YRFI MLB Rank",
                "Home Offense YRFI % MLB Rank",
            ],
            "MLB",
        )

        st.html(f"""
        <div class="game-card">
            {logo_matchup}

            <div class="game-title">{row["Game"]}</div>
            <div class="muted">{row["Game Time"]} • {row["Status"]}</div>

            <div class="decision-stack">
                <div class="decision-line">🎯 1st Inning: {first_inning_display}</div>
                <div class="decision-line">⚾ First 5: {f5_display}</div>
                <div class="decision-line">🏆 Full Game: {full_game_display}</div>
            </div>

            {key_factors}

            {market_watch}
        </div>
        """)

        with st.expander(f"🔍 Analysis: {row['Game']}"):
            st.markdown("### Analysis")

            away_col, home_col = st.columns(2)

            with away_col:
                st.markdown("#### Away")
                st.markdown(f"""
                | Field | Value |
                |---|---|
                | Team Name | {away_team} |
                | Record | {row["Away Record"]} |
                """)

            with home_col:
                st.markdown("#### Home")
                st.markdown(f"""
                | Field | Value |
                |---|---|
                | Team Name | {home_team} |
                | Record | {row["Home Record"]} |
                """)

            st.markdown("---")
            st.markdown("### Edge Breakdown")

            st.markdown("#### Starter Edge")
            st.markdown(f"""
            | Metric | Value |
            |---|---|
            | Away Starter Edge | {get_row_value(row, "Away Starter Edge", "TBD")} |
            | Home Starter Edge | {get_row_value(row, "Home Starter Edge", "TBD")} |
            | Starter Edge Winner | {get_row_value(row, "Starter Edge Winner", "Pass")} |
            | Starter Edge Margin | {get_row_value(row, "Starter Edge Margin", "TBD")} |
            """)

            st.markdown("#### Offensive Edge")
            st.markdown(f"""
            | Metric | Value |
            |---|---|
            | Away Offensive Edge | {get_row_value(row, "Away Offensive Edge", "TBD")} |
            | Home Offensive Edge | {get_row_value(row, "Home Offensive Edge", "TBD")} |
            | Offensive Edge Winner | {get_row_value(row, "Offensive Edge Winner", "Pass")} |
            | Offensive Edge Margin | {get_row_value(row, "Offensive Edge Margin", "TBD")} |
            """)

            st.markdown("#### Bullpen Edge")
            st.markdown(f"""
            | Metric | Value |
            |---|---|
            | Away Bullpen Edge | {get_row_value(row, "Away Bullpen Edge", "TBD")} |
            | Home Bullpen Edge | {get_row_value(row, "Home Bullpen Edge", "TBD")} |
            | Bullpen Edge Winner | {get_row_value(row, "Bullpen Edge Winner", "Pass")} |
            | Bullpen Edge Margin | {get_row_value(row, "Bullpen Edge Margin", "TBD")} |
            """)

            st.markdown("---")
            st.markdown("### Pitching Matchup")

            away_pitch_col, home_pitch_col = st.columns(2)

            with away_pitch_col:
                st.markdown(f"#### {away_team}")
                st.markdown(f"""
                | Metric | Value |
                |---|---|
                | Pitcher | {row["Away Pitcher"]} |
                | Record | {row["Away Pitcher Record"]} |
                | ERA | {row["Away ERA"]} |
                | WHIP | {row["Away WHIP"]} |
                | IP | {row["Away IP"]} |
                | K | {row["Away K"]} |
                """)

            with home_pitch_col:
                st.markdown(f"#### {home_team}")
                st.markdown(f"""
                | Metric | Value |
                |---|---|
                | Pitcher | {row["Home Pitcher"]} |
                | Record | {row["Home Pitcher Record"]} |
                | ERA | {row["Home ERA"]} |
                | WHIP | {row["Home WHIP"]} |
                | IP | {row["Home IP"]} |
                | K | {row["Home K"]} |
                """)

            st.markdown("---")
            st.markdown("### 1st Inning")

            away_first_col, home_first_col = st.columns(2)

            with away_first_col:
                st.markdown(f"#### {away_team}")
                st.markdown(f"""
                | Metric | Value |
                |---|---|
                | Pitcher YRFI % | {away_pitcher_yrfi_display} |
                | Offense YRFI % | {away_offense_yrfi_display} |
                """)

            with home_first_col:
                st.markdown(f"#### {home_team}")
                st.markdown(f"""
                | Metric | Value |
                |---|---|
                | Pitcher YRFI % | {home_pitcher_yrfi_display} |
                | Offense YRFI % | {home_offense_yrfi_display} |
                """)

            st.markdown("#### First Inning Matchup")
            st.markdown(f"""
            | Matchup | YRFI Profile |
            |---|---|
            | Away Offense vs Home Pitcher | {away_offense_yrfi}% / {home_pitcher_yrfi}% |
            | Home Offense vs Away Pitcher | {home_offense_yrfi}% / {away_pitcher_yrfi}% |
            """)

            st.markdown("---")
            st.markdown("### Bullpen Usage")

            away_bullpen_col, home_bullpen_col = st.columns(2)

            with away_bullpen_col:
                st.markdown(f"#### {away_team}")
                st.markdown(f"""
                | Metric | Value |
                |---|---|
                | Rating | {row["Away Bullpen Status"]} |
                | Fatigue Score | {row["Away Bullpen Fatigue"]} |
                | 3-Day Bullpen IP | {row["Away 3 Day Bullpen IP"]} |
                | 3-Day Bullpen Pitches | {row["Away 3 Day Bullpen Pitches"]} |
                | 3-Day Relievers Used | {row["Away 3 Day Relievers"]} |
                | Back-to-Back Arms | {row["Away Back-to-Back Arms"]} |
                """)

            with home_bullpen_col:
                st.markdown(f"#### {home_team}")
                st.markdown(f"""
                | Metric | Value |
                |---|---|
                | Rating | {row["Home Bullpen Status"]} |
                | Fatigue Score | {row["Home Bullpen Fatigue"]} |
                | 3-Day Bullpen IP | {row["Home 3 Day Bullpen IP"]} |
                | 3-Day Bullpen Pitches | {row["Home 3 Day Bullpen Pitches"]} |
                | 3-Day Relievers Used | {row["Home 3 Day Relievers"]} |
                | Back-to-Back Arms | {row["Home Back-to-Back Arms"]} |
                """)

st.divider()

csv = filtered.to_csv(index=False).encode("utf-8")

st.download_button(
    label="Download MLB Report",
    data=csv,
    file_name=f"first_five_edge_report_{selected_date}.csv",
    mime="text/csv"
)
