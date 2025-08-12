import os
import json
import streamlit as st
from supabase import create_client
from datetime import datetime, timezone, date

# ---------------- App + auth gate ----------------
st.set_page_config(page_title="Flabee Admin", layout="wide")

# Admin PIN from secrets (set this in Cloud later)
ADMIN_PIN = st.secrets.get("ADMIN_PIN", None)

# Supabase client (service key required)
sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_KEY"])

# Simple gate
st.sidebar.title("Admin")
pin_ok = False
if ADMIN_PIN:
    pin = st.sidebar.text_input("Enter admin PIN", type="password")
    if st.sidebar.button("Unlock"):
        if pin == ADMIN_PIN:
            st.session_state["admin_ok"] = True
        else:
            st.error("Wrong PIN.")
    pin_ok = st.session_state.get("admin_ok", False)
else:
    st.warning("ADMIN_PIN not set in secrets; running without gate.")
    pin_ok = True

if not pin_ok:
    st.stop()

# ---------------- Helpers ----------------
def iso_to_dt(ts: str):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None

def list_conversations(search: str, limit: int, offset: int):
    return sb.rpc(
        "list_conversations",
        {"p_search": search or None, "p_limit": limit, "p_offset": offset},
    ).execute().data or []

def list_messages(conv_id, before=None, limit=100):
    return sb.rpc(
        "list_messages",
        {"p_conversation_id": conv_id, "p_before": before, "p_limit": limit},
    ).execute().data or []

def refresh_state():
    st.session_state.pop("msgs_cache", None)

# ---------------- Sidebar: select conversation ----------------
with st.sidebar:
    st.subheader("Select Conversation")

    if "admin_conv_page" not in st.session_state:
        st.session_state.admin_conv_page = 1

    search = st.text_input("Search (user/last msg)", "")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("⟨ Prev", use_container_width=True, key="prev_admin"):
            st.session_state.admin_conv_page = max(1, st.session_state.admin_conv_page - 1)
    with c2:
        if st.button("Next ⟩", use_container_width=True, key="next_admin"):
            st.session_state.admin_conv_page += 1

    limit = 30
    offset = (st.session_state.admin_conv_page - 1) * limit
    convs = list_conversations(search, limit, offset)

    if not convs:
        st.info("No conversations found.")
        st.stop()

    labels = [
        f"{c['user_label'] or 'Chat'} • {c['status'] or 'open'} • {c['msg_count']} msgs • {c['last_message_at'][:19]}"
        for c in convs
    ]
    if "admin_conv_idx" not in st.session_state:
        st.session_state.admin_conv_idx = 0

    st.session_state.admin_conv_idx = st.radio(
        "Threads",
        range(len(convs)),
        index=min(st.session_state.admin_conv_idx, len(convs)-1),
        format_func=lambda i: labels[i],
    )

selected = convs[st.session_state.admin_conv_idx]
conv_id = selected["conversation_id"]

st.title(f"Admin • {selected.get('user_label') or 'Conversation'}")
st.caption(f"ID: {conv_id} • Updated: {selected['last_message_at']} • {selected['msg_count']} msgs")

# ---------------- Conversation actions ----------------
st.subheader("Conversation Actions")

col1, col2, col3 = st.columns([2,1,2])

with col1:
    new_title = st.text_input("Title", value=selected.get("title") or "")
    if st.button("Rename", use_container_width=True):
        sb.rpc("rename_conversation", {"p_conversation_id": conv_id, "p_title": new_title}).execute()
        st.success("Title updated.")
        refresh_state()

with col2:
    new_status = st.selectbox("Status", options=["open", "closed"], index=0 if (selected.get("status") or "open")=="open" else 1)
    if st.button("Update Status", use_container_width=True):
        sb.rpc("set_conversation_status", {"p_conversation_id": conv_id, "p_status": new_status}).execute()
        st.success("Status updated.")
        refresh_state()

with col3:
    tags_csv = st.text_input("Tags (comma-separated)", value=", ".join(selected.get("tags") or []))
    if st.button("Save Tags", use_container_width=True):
        tags_list = [t.strip() for t in tags_csv.split(",") if t.strip()]
        sb.rpc("set_conversation_tags", {"p_conversation_id": conv_id, "p_tags": tags_list}).execute()
        st.success("Tags updated.")
        refresh_state()

st.divider()

# ---------------- Messages: pick and edit ----------------
st.subheader("Edit Messages")

# cache messages per conv
if "msgs_cache" not in st.session_state:
    st.session_state.msgs_cache = {}

if conv_id not in st.session_state.msgs_cache:
    # load newest 200; you can paginate more if needed
    all_rows, cursor = [], None
    while True:
        page = list_messages(conv_id, before=cursor, limit=200)
        if not page:
            break
        all_rows.extend(page)
        cursor = page[-1]["created_at"]
        if len(page) < 200:
            break
    st.session_state.msgs_cache[conv_id] = list(reversed(all_rows))  # oldest->newest

msgs = st.session_state.msgs_cache[conv_id]

if not msgs:
    st.info("No messages in this conversation.")
else:
    # selection dropdown
    options = [f"{m['created_at'][:19]} • {m['role']} • {m['content'][:60].replace('\n',' ')}" for m in msgs]
    sel_idx = st.selectbox("Select message", options=range(len(msgs)), format_func=lambda i: options[i], index=len(msgs)-1)
    sel = msgs[sel_idx]

    st.write(f"**Message ID:** {sel['id']}  \n**Role:** {sel['role']}  \n**Created:** {sel['created_at']}")
    new_content = st.text_area("Edit content", value=sel["content"], height=180)

    cA, cB = st.columns([1,1])
    with cA:
        if st.button("Save Change", use_container_width=True):
            sb.rpc("update_message", {"p_message_id": sel["id"], "p_content": new_content}).execute()
            sel["content"] = new_content
            st.success("Message updated.")

    with cB:
        if st.button("Reload Messages", use_container_width=True):
            st.session_state.msgs_cache.pop(conv_id, None)
            st.rerun()

    # optional: show meta
    if sel.get("meta"):
        with st.expander("Message meta"):
            st.json(sel["meta"])
