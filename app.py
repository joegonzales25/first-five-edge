import streamlit as st
from datetime import date, timedelta
from mlb_agent import get_today_games

st.set_page_config(
    page_title="First Five Edge",
    page_icon="⚾",
    layout="wide"
)

st.markdown("""
<style>
.main {
    background-color: #0b1220;
}
.game-card {
    background: #111827;
    border: 1px solid #263244;
    border-radius: 18px;
    padding: 20px;
    margin-bottom: 18px;
}
.power-card {
    background: linear-gradient(90deg, #064e3b, #047857);
    border-radius: 18px;
    padding: 22px;
    margin-bottom: 18px;
    color: white;
}
.badge {
    display: inline-block;
    padding: 6px 12px;
    border-radius: 999px;
    background: #2563eb;
    color: white;
    font-weight: 700;
    margin-right: 8px;
}
.small-muted {
    color: #9ca3af;
    font-size: 14px;
}
.big-pick {
    font-size: 26px;
    font-weight: 800;
}
</style>
""", unsafe_allow_html=True)

st.title("⚾ First Five Edge")
st.caption("MLB YRFI / NRFI • First 5 • Bullpen Fatigue Intelligence")

# Sidebar
st.sidebar.title("Controls")
selected_date = st.sidebar.date_input("Slate Date", value=date.today())

if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

view = st.sidebar.radio(
    "View",
    ["All Games", "Power Picks", "NRFI", "YRFI", "F5", "Bullpen Watch"]
)

min_edge = st.sidebar.slider("Minimum Edge Score", 0, 100, 0)

@st.cache_data(ttl=900)
def load_games(selected_date):
    return get_today_games(selected_date.isoformat())

games = load_games(selected_date)

if games.empty:
    st.warning("No MLB games found for selected date.")
    st.stop()

games = games.copy()
games["Edge Score"] = games["Edge Score"].fillna(0)

# Filters
filtered = games[games["Edge Score"] >= min_edge].copy()

if view == "Power Picks":
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

filtered = filtered.sort_values("Edge Score", ascending=False)

# Header metrics
st.subheader(f"Slate: {selected_date}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Games", len(games))
c2.metric("Power Picks", len(games[games["Recommendation"] != "Pass"]))
c3.metric("NRFI Looks", len(games[games["Lean"].isin(["NRFI", "Strong NRFI"])]))
c4.metric("F5 Edges", len(games[games["F5 Edge"] != "F5 Pass"]))

st.divider()

# Power Pick Hero
power_picks = games[games["Recommendation"] != "Pass"].sort_values(
    "Edge Score",
    ascending=False
)

if not power_picks.empty:
    top = power_picks.iloc[0]

    st.markdown(
        f"""
        <div class="power-card">
            <div class="small-muted">MODEL FAVORITE</div>
            <div class="big-pick">{top["Recommendation"]}</div>
            <h2>{top["Game"]}</h2>
            <p>{top["Game Time"]}</p>
            <span class="badge">Confidence {top["Confidence"]}</span>
            <span class="badge">Edge {top["Edge Score"]}</span>
            <span class="badge">{top["Lean"]}</span>
            <p style="margin-top:15px;">{top["Agent Notes"]}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

st.subheader("Game Cards")

# Game Cards
for _, row in filtered.iterrows():
    with st.container(border=True):
        left, right = st.columns([2, 1])

        with left:
            st.markdown(f"### {row['Game']}")
            st.caption(f"{row['Game Time']} • {row['Status']}")

            st.markdown(f"**Recommendation:** {row['Recommendation']}")
            st.markdown(f"**Lean:** {row['Lean']}")

        with right:
            st.metric("Edge Score", row["Edge Score"])
            st.metric("Confidence", row["Confidence"])

        a, b, c = st.columns(3)
        a.metric("NRFI Score", row["NRFI Score"])
        b.metric("F5 Edge", row["F5 Edge"])
        c.metric(
            "Bullpen",
            f'{row["Away Bullpen Status"]} / {row["Home Bullpen Status"]}'
        )

        with st.expander("View Analysis"):
            st.markdown("#### Starting Pitchers")
            st.write(f'{row["Away Pitcher"]}: ERA {row["Away ERA"]}, WHIP {row["Away WHIP"]}')
            st.write(f'{row["Home Pitcher"]}: ERA {row["Home ERA"]}, WHIP {row["Home WHIP"]}')

            st.markdown("#### First Inning Risk")
            st.write(f'Away: {row["Away 1st Inning Risk"]}')
            st.write(f'Home: {row["Home 1st Inning Risk"]}')

            st.markdown("#### Bullpen Fatigue")
            st.write(
                f'Away: {row["Away Bullpen Fatigue"]} '
                f'({row["Away Bullpen Status"]})'
            )
            st.write(
                f'Home: {row["Home Bullpen Fatigue"]} '
                f'({row["Home Bullpen Status"]})'
            )

            st.markdown("#### Model Notes")
            st.write(row["Agent Notes"])

st.divider()

# Download
csv = filtered.to_csv(index=False).encode("utf-8")

st.download_button(
    label="Download MLB Report",
    data=csv,
    file_name=f"first_five_edge_report_{selected_date}.csv",
    mime="text/csv"
)