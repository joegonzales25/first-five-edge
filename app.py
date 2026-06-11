import streamlit as st
from datetime import date
from mlb_agent import get_today_games

APP_VERSION = "2.0"

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
    border-left: 8px solid #9ca3af;
    padding: 22px;
    margin-bottom: 6px;
    background: #ffffff;
}
.card-nrfi { border-left-color: #22c55e; }
.card-yrfi { border-left-color: #ef4444; }
.card-f5 { border-left-color: #3b82f6; }
.card-pass { border-left-color: #9ca3af; }

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
    margin-bottom: 14px;
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


def get_card_class(row):
    if row["Lean"] in ["Strong NRFI", "NRFI"]:
        return "card-nrfi"
    if row["Lean"] in ["Strong YRFI", "YRFI"]:
        return "card-yrfi"
    if row["F5 Edge"] != "F5 Pass":
        return "card-f5"
    return "card-pass"


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
        card_class = get_card_class(row)
        badge_class = get_badge_class(row)
        away_team, home_team = split_game_name(row["Game"])

        st.html(f"""
        <div class="game-card {card_class}">
            <span class="badge {badge_class}">{row["Lean"]}</span>
            <span class="badge badge-edge">Edge {row["Edge Score"]}</span>
            <span class="badge badge-edge">Confidence {row["Confidence"]}</span>

            <div class="game-title">{row["Game"]}</div>
            <div class="muted">{row["Game Time"]} • {row["Status"]}</div>

            <div class="recommendation">
                <strong>Recommendation:</strong> {row["Recommendation"]}
            </div>

            <div class="muted">
                NRFI Score: <strong>{row["NRFI Score"]}</strong> &nbsp; • &nbsp;
                F5 Edge: <strong>{row["F5 Edge"]}</strong> &nbsp; • &nbsp;
                Bullpen: <strong>{row["Away Bullpen Status"]} / {row["Home Bullpen Status"]}</strong>
            </div>
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
                | YRFI Risk | {row["Away 1st Inning Risk"]} |
                | Pitcher YRFI % | {row["Away Pitcher YRFI %"]} |
                | 1st ERA | {row["Away 1st ERA"]} |
                | 1st WHIP | {row["Away 1st WHIP"]} |
                | Offense YRFI % | {row["Away Offense YRFI %"]} |
                | 1st Run Avg | {row["Away 1st Run Avg"]} |
                """)

            with home_first_col:
                st.markdown(f"#### {home_team}")
                st.markdown(f"""
                | Metric | Value |
                |---|---|
                | YRFI Risk | {row["Home 1st Inning Risk"]} |
                | Pitcher YRFI % | {row["Home Pitcher YRFI %"]} |
                | 1st ERA | {row["Home 1st ERA"]} |
                | 1st WHIP | {row["Home 1st WHIP"]} |
                | Offense YRFI % | {row["Home Offense YRFI %"]} |
                | 1st Run Avg | {row["Home 1st Run Avg"]} |
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
                | Yesterday Relievers | {row["Away Yesterday Relievers"]} |
                | Yesterday Pitches | {row["Away Yesterday Pitches"]} |
                | 3-Day Bullpen Pitches | {row["Away 3 Day Bullpen Pitches"]} |
                | Back-to-Back Arms | {row["Away Back-to-Back Arms"]} |
                """)

            with home_bullpen_col:
                st.markdown(f"#### {home_team}")
                st.markdown(f"""
                | Metric | Value |
                |---|---|
                | Rating | {row["Home Bullpen Status"]} |
                | Fatigue Score | {row["Home Bullpen Fatigue"]} |
                | Yesterday Relievers | {row["Home Yesterday Relievers"]} |
                | Yesterday Pitches | {row["Home Yesterday Pitches"]} |
                | 3-Day Bullpen Pitches | {row["Home 3 Day Bullpen Pitches"]} |
                | Back-to-Back Arms | {row["Home Back-to-Back Arms"]} |
                """)

            st.markdown("---")
            st.markdown("### Model Notes")
            st.info(row["Agent Notes"])

st.divider()

csv = filtered.to_csv(index=False).encode("utf-8")

st.download_button(
    label="Download MLB Report",
    data=csv,
    file_name=f"first_five_edge_report_{selected_date}.csv",
    mime="text/csv"
)
