import os
import json
import streamlit as st
from supabase import create_client
from datetime import datetime, timezone, date

# ========= Brand + Assets =========
LOGO_PATH = r"D:\chat-viewer\flabeelogo.jpg"
if not os.path.exists(LOGO_PATH):
    LOGO_PATH = "flabeelogo.jpg"

PALETTE = {
    "FUCHSIA": "#FF3C69",   # Flabee pink (primary)
    "BABY":    "#FFC2C8",
    "JASMINE": "#F9ECE4",
    "CONGO":   "#F18471",
    "NAVY":    "#34345B",
    "WHITE":   "#FFFFFF",
}

# ========= App config =========
st.set_page_config(page_title="Flabee Chat Viewer", layout="wide")
sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_KEY"])

# ========= Global styles (glassmorphism) =========
GLASS_CSS = f"""
<style>
:root {{
  --fuchsia: {PALETTE["FUCHSIA"]};
  --baby:    {PALETTE["BABY"]};
  --jasmine: {PALETTE["JASMINE"]};
  --congo:   {PALETTE["CONGO"]};
  --navy:    {PALETTE["NAVY"]};
  --white:   {PALETTE["WHITE"]};

  --glass-bg: rgba(255,255,255,0.35);
  --glass-strong: rgba(255,255,255,0.58);
  --glass-border: rgba(255,255,255,0.28);
  --shadow: 0 10px 30px rgba(0,0,0,.10);
}}

html, body, [data-testid="stAppViewContainer"] > .main {{
  background: radial-gradient(1200px 600px at 10% -10%, var(--baby) 0%, var(--jasmine) 42%, var(--white) 100%);
  color: var(--navy);
}}

h1, h2, h3 {{ color: var(--navy); }}

[data-testid="stSidebar"] > div:first-child {{
  background: linear-gradient(180deg, var(--baby) 0%, var(--jasmine) 100%);
  backdrop-filter: blur(10px);
  border-right: 1px solid var(--glass-border);
}}

.stButton > button {{
  background: linear-gradient(135deg, var(--fuchsia), var(--congo));
  color: white !important;
  border-radius: 12px;
  padding: 8px 14px;
  border: 0;
  box-shadow: var(--shadow);
}}
.stButton > button:disabled {{ background: rgba(0,0,0,.08); color: rgba(0,0,0,.35) !important; }}

.header-card {{
  margin-bottom: 12px;
  padding: 14px 18px;
  border-radius: 16px;
  background: var(--glass-strong);
  border: 1px solid var(--glass-border);
  box-shadow: var(--shadow);
}}

.chat-row{{display:flex; margin:10px 0;}}
.chat-left{{justify-content:flex-start;}}
.chat-right{{justify-content:flex-end;}}

.bubble{{
  max-width: 74%;
  padding: 12px 14px;
  border-radius: 16px;
  line-height: 1.45;
  word-wrap: break-word;
  white-space: pre-wrap;
  box-shadow: var(--shadow);
  border: 1px solid var(--glass-border);
  backdrop-filter: blur(8px);
}}

.user {{ background: rgba(255,255,255,0.55); }}
.assistant {{
  background: rgba(255, 60, 105, 0.18);
  border-color: rgba(255, 60, 105, 0.35);
}}

.meta{{ font-size:12px; color: rgba(0,0,0,.45); margin-top:6px; }}
.small-cap{{ font-variant-caps: all-small-caps; letter-spacing: .6px; color: rgba(0,0,0,.45); }}
</style>
"""
st.markdown(GLASS_CSS, unsafe_allow_html=True)

# ========= Helpers =========
def fmt_time(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return ts

def bubble(role: str, content: str, ts: str):
    side_class = "chat-left" if (role or "").lower() == "user" else "chat-right"
    role_class = "user" if (role or "").lower() == "user" else "assistant"
    st.markdown(
        f"""
        <div class="chat-row {side_class}">
          <div>
            <div class="bubble {role_class}">{content}</div>
            <div class="meta">{fmt_time(ts)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

def to_jsonl(rows):
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)

# ========= Sidebar: logo + conversations =========
with st.sidebar:
    try:
        st.image(LOGO_PATH, width=140)
    except Exception:
        st.write(" ")

    st.title("Conversations")

    # paging state
    if "conv_page" not in st.session_state:
        st.session_state.conv_page = 1

    # search
    search = st.text_input("Search (user / last msg)", value="")

    # simple date filters (set defaults to avoid None issues)
    col_from, col_to = st.columns(2)
    with col_from:
        start_date = st.date_input("From", value=date(2000, 1, 1))
    with col_to:
        end_date = st.date_input("To", value=date.today())

    # paging buttons
    c1, c2 = st.columns(2)
    with c1:
        if st.button("⟨ Prev", use_container_width=True, disabled=st.session_state.conv_page <= 1):
            st.session_state.conv_page = max(1, st.session_state.conv_page - 1)
    with c2:
        if st.button("Next ⟩", use_container_width=True):
            st.session_state.conv_page += 1

    limit = 30
    offset = (st.session_state.conv_page - 1) * limit

    # fetch page
    convs_raw = sb.rpc(
        "list_conversations",
        {"p_search": search or None, "p_limit": limit, "p_offset": offset},
    ).execute().data or []

    # channel options from page
    page_channels = sorted({(c.get("last_channel") or "unknown") for c in convs_raw})
    channel = st.selectbox("Channel", options=["(all)"] + page_channels, index=0)

    # date + channel filter (client-side)
    def in_date_range(iso_ts: str) -> bool:
        if not iso_ts:
            return True
        try:
            dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00")).date()
        except Exception:
            return True
        return (dt >= start_date) and (dt <= end_date)

    convs = []
    for c in convs_raw:
        ch_ok = (channel == "(all)") or ((c.get("last_channel") or "unknown") == channel)
        dt_ok = in_date_range(c.get("last_message_at"))
        if ch_ok and dt_ok:
            convs.append(c)

    if not convs:
        st.info("No conversations match the filters on this page.")
        st.stop()

    # list UI
    labels = [
        f"{c['user_label'] or 'Chat'} · {c['last_message_at'][:19]} · {c['msg_count']} msgs · {c.get('last_channel') or 'unknown'}"
        for c in convs
    ]
    if "conv_idx" not in st.session_state:
        st.session_state.conv_idx = 0
    st.session_state.conv_idx = st.radio(
        "Select a thread",
        range(len(convs)),
        index=min(st.session_state.conv_idx, len(convs)-1),
        format_func=lambda i: labels[i],
    )

# selected conversation
selected = convs[st.session_state.conv_idx]
conv_id = selected["conversation_id"]  # <-- correct field name from your view

# ======== Reset message cursor when thread changes ========
if st.session_state.get("last_conv_id") != conv_id:
    st.session_state["cursor_before"] = None
    st.session_state["last_conv_id"] = conv_id

# ========= Header (glass card) =========
st.markdown(
    f"""
    <div class="header-card">
      <div class="small-cap">Chat</div>
      <div style="font-size:22px; font-weight:700; color:var(--navy); margin-top:2px;">
        {selected.get("user_label") or "Conversation"}
      </div>
      <div style="margin-top:4px; color:rgba(0,0,0,.55);">
        {selected.get('title') or '—'} · updated {selected['last_message_at']} · {selected['msg_count']} msgs
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# --- Export JSONL of entire thread ---
actions = st.columns([1, 1, 6])
with actions[0]:
    if st.button("Export JSONL"):
        all_rows, cursor = [], None
        while True:
            page = sb.rpc(
                "list_messages",
                {"p_conversation_id": conv_id, "p_before": cursor, "p_limit": 200},
            ).execute().data or []
            if not page:
                break
            all_rows.extend(page)
            cursor = page[-1]["created_at"]  # newest-first page
            if len(page) < 200:
                break

        all_rows = list(reversed(all_rows))  # oldest-first for export
        st.download_button(
            label="Download conversation.jsonl",
            mime="text/plain",
            data=to_jsonl(all_rows),
            file_name=f"conversation-{conv_id}.jsonl",
            use_container_width=True,
        )

# ========= Fetch + render messages =========
res = sb.rpc(
    "list_messages",
    {"p_conversation_id": conv_id, "p_before": st.session_state.get("cursor_before"), "p_limit": 50},
).execute().data

msgs = list(reversed(res))  # oldest -> newest
for m in msgs:
    bubble(m.get("role", "assistant"), m.get("content", ""), m.get("created_at", ""))
    meta = m.get("meta")
    if meta:
        with st.expander("Details"):
            st.json(meta)

# ========= Paging =========
if res:
    oldest_ts = res[-1]["created_at"]
    if st.button("Load earlier"):
        st.session_state["cursor_before"] = oldest_ts
        st.rerun()
else:
    st.info("No messages in this conversation yet.")
