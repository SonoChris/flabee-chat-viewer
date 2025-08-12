import os
import pandas as pd
import altair as alt
import streamlit as st
from supabase import create_client
from datetime import datetime, timedelta, timezone

# ----- branding --------------------------------------------------------------
LOGO_PATH = "flabeelogo.jpg"
PALETTE = {
    "FUCHSIA": "#FF3C69",
    "BABY":    "#FFC2C8",
    "JASMINE": "#F9ECE4",
    "CONGO":   "#F18471",
    "NAVY":    "#34345B",
    "WHITE":   "#FFFFFF",
}

GLASS_CSS = f"""
<style>
:root {{
  --fuchsia:{PALETTE["FUCHSIA"]}; --baby:{PALETTE["BABY"]}; --jasmine:{PALETTE["JASMINE"]};
  --navy:{PALETTE["NAVY"]}; --white:{PALETTE["WHITE"]};
  --glass-bg: rgba(255,255,255,.55); --glass-border: rgba(255,255,255,.28);
  --shadow: 0 10px 30px rgba(0,0,0,.10);
}}
html, body, [data-testid="stAppViewContainer"]>.main {{
  background: radial-gradient(1200px 600px at 10% -10%, var(--baby) 0%, var(--jasmine) 42%, var(--white) 100%);
  color: var(--navy);
}}
.card {{
  background: var(--glass-bg); border:1px solid var(--glass-border);
  border-radius:16px; padding:16px; box-shadow:var(--shadow);
}}
.kpi {{ font-size:28px; font-weight:700; }}
.kpi-label {{ color: rgba(0,0,0,.55); font-size:12px; }}
</style>
"""
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Flabee Analytics", layout="wide")
st.markdown(GLASS_CSS, unsafe_allow_html=True)

sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_KEY"])

@st.cache_data(ttl=60)
def load_data(cutoff_iso: str):
    # Use .order("day") for ascending; desc=False is the default
    daily = (
        sb.table("daily_message_counts")
          .select("*")
          .gte("day", cutoff_iso)
          .order("day")              # ascending
          .execute()
          .data
    )
    channel = (
        sb.table("channel_message_counts")
          .select("*")
          .gte("day", cutoff_iso)
          .order("day")              # ascending
          .execute()
          .data
    )
    active = (
        sb.table("daily_active_conversations")
          .select("*")
          .gte("day", cutoff_iso)
          .order("day")              # ascending
          .execute()
          .data
    )
    convs = (
        sb.table("conversations")
          .select("status,last_message_at")
          .gte("last_message_at", cutoff_iso)
          .execute()
          .data
    )
    import pandas as pd
    return pd.DataFrame(daily), pd.DataFrame(channel), pd.DataFrame(active), pd.DataFrame(convs)


# ----- sidebar controls ------------------------------------------------------
try:
    st.sidebar.image(LOGO_PATH, width=140)
except Exception:
    pass

st.sidebar.title("Analytics")
range_days = st.sidebar.selectbox("Range", [7, 30, 90], index=1)
cutoff_dt = (datetime.now(timezone.utc) - timedelta(days=range_days)).date()
cutoff_iso = cutoff_dt.isoformat()

daily_df, channel_df, active_df, convs_df = load_data(cutoff_iso)

st.title("Flabee Analytics")

# ----- KPIs ------------------------------------------------------------------
total_msgs = int(daily_df["total"].sum()) if not daily_df.empty else 0
total_convs = int(active_df["active_conversations"].sum()) if not active_df.empty else 0
avg_msgs_per_conv = round(total_msgs / max(total_convs, 1), 2)

if convs_df.empty:
    closed = 0
    total_in_range = 0
    resolution_rate = 0.0
else:
    total_in_range = len(convs_df)
    closed = int((convs_df["status"] == "closed").sum())
    resolution_rate = round(100.0 * closed / max(total_in_range, 1), 1)

k1, k2, k3, k4 = st.columns(4)
with k1: st.markdown(f'<div class="card kpi">{total_msgs}</div><div class="kpi-label">Messages</div>', unsafe_allow_html=True)
with k2: st.markdown(f'<div class="card kpi">{total_convs}</div><div class="kpi-label">Active conversations</div>', unsafe_allow_html=True)
with k3: st.markdown(f'<div class="card kpi">{avg_msgs_per_conv}</div><div class="kpi-label">Avg msgs / conversation</div>', unsafe_allow_html=True)
with k4: st.markdown(f'<div class="card kpi">{resolution_rate}%</div><div class="kpi-label">Resolution rate</div>', unsafe_allow_html=True)

st.divider()

# ----- Daily volume (user vs assistant) -------------------------------------
if not daily_df.empty:
    daily_long = daily_df.melt(id_vars=["day"], value_vars=["user_msgs","assistant_msgs"],
                               var_name="role", value_name="count")
    chart = alt.Chart(daily_long).mark_line(point=True).encode(
        x=alt.X("day:T", title="Day"),
        y=alt.Y("count:Q", title="Messages"),
        color=alt.Color("role:N", title="Role",
                        scale=alt.Scale(domain=["user_msgs","assistant_msgs"],
                                        range=[PALETTE["NAVY"], PALETTE["FUCHSIA"]]))
    ).properties(height=300).interactive()
    st.altair_chart(chart, use_container_width=True)
else:
    st.info("No daily data in selected range.")

# ----- Channel breakdown -----------------------------------------------------
st.subheader("Channel breakdown")
if not channel_df.empty:
    # aggregate over the selected range
    chan_tot = channel_df.groupby("channel", as_index=False)["cnt"].sum().sort_values("cnt", ascending=False)
    bar = alt.Chart(chan_tot).mark_bar().encode(
        x=alt.X("cnt:Q", title="Messages"),
        y=alt.Y("channel:N", sort='-x', title="Channel"),
        color=alt.value(PALETTE["FUCHSIA"])
    ).properties(height=280)
    st.altair_chart(bar, use_container_width=True)
else:
    st.info("No channel data in selected range.")

# ----- Active conversations line --------------------------------------------
st.subheader("Daily active conversations")
if not active_df.empty:
    act = alt.Chart(active_df).mark_line(point=True).encode(
        x=alt.X("day:T", title="Day"),
        y=alt.Y("active_conversations:Q", title="Active conversations"),
        color=alt.value(PALETTE["NAVY"])
    ).properties(height=260)
    st.altair_chart(act, use_container_width=True)
else:
    st.info("No activity data in selected range.")

# ----- Exports ---------------------------------------------------------------
st.subheader("Exports")
cA, cB, cC = st.columns(3)
with cA:
    if not daily_df.empty:
        st.download_button("Download daily.csv", daily_df.to_csv(index=False), "daily.csv", "text/csv")
with cB:
    if not channel_df.empty:
        st.download_button("Download channels.csv", channel_df.to_csv(index=False), "channels.csv", "text/csv")
with cC:
    if not active_df.empty:
        st.download_button("Download active.csv", active_df.to_csv(index=False), "active.csv", "text/csv")

