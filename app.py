"""NoteBuddy: an open-source AI study assistant. Run with:  streamlit run app.py"""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from notebuddy import auth, db, ingest, llm, panels, state, tools, ui

st.set_page_config(page_title="NoteBuddy", page_icon="✦", layout="wide", initial_sidebar_state="expanded")


@st.cache_resource
def _boot() -> bool:
    db.init()
    return True


_boot()
ui.inject_css()
state.init_defaults()

SYSTEM = """You are NoteBuddy, a friendly study assistant.
Answer using ONLY the student's notes inside <notes>. Keep answers short: 2 to 5 sentences or a tight list, in simple language.
If the notes don't contain the answer, say so plainly. You may then add a brief answer labelled "Beyond your notes".
If the notes contain a factual mistake that matters for the question, point it out kindly and give the correction.
Use markdown sparingly.

<notes>
{notes}
</notes>"""

SYSTEM_NO_NOTES = """You are NoteBuddy, a friendly study assistant. The student has not selected any notes,
so answer briefly in simple language from general knowledge, and mention that you aren't using their notes."""

SUGGESTIONS = ["Summarise this in 5 lines", "What are the key terms I should know?",
               "Explain the hardest idea like I'm new to it"]


# ───────────────────────── sign in ─────────────────────────
def restore_session() -> None:
    if state.user():
        return
    token = st.query_params.get("t")
    if token:
        u = db.get_user_by_session(token)
        if u:
            st.session_state["user"] = u
            st.session_state["token"] = token
        else:
            st.query_params.pop("t", None)


def sign_in(u: dict, keep: bool) -> None:
    st.session_state["user"] = u
    if keep:
        token = auth.new_session(u["id"])
        st.session_state["token"] = token
        st.query_params["t"] = token
    st.rerun()


def sign_out() -> None:
    token = st.session_state.get("token")
    if token:
        db.delete_session(token)
    st.query_params.clear()
    st.session_state.clear()


def auth_view() -> None:
    _, mid, _ = st.columns([1, 1.5, 1])
    with mid:
        ui.brand(hero=True, tagline="Upload your notes. Ask in plain language. Get short answers.")
        tab_in, tab_up = st.tabs(["Sign in", "Create account"])
        with tab_in:
            with st.form("signin"):
                name = st.text_input("Username")
                pw = st.text_input("Password", type="password")
                keep = st.checkbox("Keep me signed in on this device")
                go = st.form_submit_button("Sign in", type="primary")
            if go:
                u, err = auth.login(name, pw)
                st.error(err) if err else sign_in(u, keep)
        with tab_up:
            with st.form("signup"):
                name = st.text_input("Username", key="su_name")
                email = st.text_input("Email (optional)", key="su_email")
                pw = st.text_input("Password", type="password", key="su_pw", help="At least 8 characters")
                pw2 = st.text_input("Confirm password", type="password", key="su_pw2")
                go = st.form_submit_button("Create account", type="primary")
            if go:
                u, err = auth.register(name, email, pw, pw2)
                st.error(err) if err else sign_in(u, True)
        st.caption("Your notes and chats are stored per account on the machine running this app.")


# ───────────────────────── sidebar ─────────────────────────
def _go(page: str, chat_id: int | None = None) -> None:
    st.session_state["page"] = page
    st.session_state["chat_id"] = chat_id
    st.session_state.pop("scope_new", None)


def _delete_chat(chat_id: int) -> None:
    db.delete_chat(state.user()["id"], chat_id)
    if st.session_state.get("chat_id") == chat_id:
        st.session_state["chat_id"] = None


def sidebar() -> None:
    uid = state.user()["id"]
    with st.sidebar:
        ui.brand()
        st.write("")
        page, active = st.session_state["page"], st.session_state["chat_id"]
        st.button("New chat", icon=":material/edit_square:", key="nav_new", on_click=_go, args=("chat",),
                  type="primary" if page == "chat" and active is None else "secondary")
        st.button("Library", icon=":material/folder_open:", key="nav_lib", on_click=_go, args=("library",),
                  type="primary" if page == "library" else "secondary")

        chats = db.list_chats(uid)
        if chats:
            st.markdown('<div class="nb-label">Recent chats</div>', unsafe_allow_html=True)
        for c in chats:
            a, b = st.columns([6, 1], vertical_alignment="center")
            a.button(c["title"], key=f"chat_{c['id']}", on_click=_go, args=("chat", c["id"]),
                     type="primary" if page == "chat" and active == c["id"] else "secondary")
            b.button(":material/close:", key=f"del_{c['id']}", on_click=_delete_chat, args=(c["id"],),
                     help="Delete chat")

        st.markdown('<div class="nb-label">Gemini</div>', unsafe_allow_html=True)
        with st.expander("API key and model", expanded=not state.api_key()):
            st.text_input("API key", type="password", key="api_key", placeholder="Paste your Gemini API key",
                          help="Kept in this browser session only. It is never written to the database.")
            st.selectbox("Model", state.MODEL_PRESETS, key="model_choice")
            if st.session_state["model_choice"] == "Custom...":
                st.text_input("Model name", key="model_custom", placeholder="e.g. gemini-2.5-flash")
            if st.button("Test connection", key="test_key"):
                try:
                    llm.test_key(state.cfg())
                    st.success("Connected.")
                except llm.LLMError as e:
                    st.error(str(e))
            st.caption("Get a free key at aistudio.google.com")

        st.markdown('<div class="nb-label">Account</div>', unsafe_allow_html=True)
        a, b = st.columns([3, 2], vertical_alignment="center")
        a.markdown(f"**{state.user()['username']}**")
        b.button("Sign out", key="signout", on_click=sign_out)


# ───────────────────────── chat ─────────────────────────
def chat_view() -> None:
    uid = state.user()["id"]
    notes = db.list_notes(uid)
    titles = {n["id"]: n["title"] for n in notes}
    chat_id = st.session_state["chat_id"]
    chat = db.get_chat(uid, chat_id) if chat_id else None
    if chat_id and not chat:
        chat_id = st.session_state["chat_id"] = None

    if not notes:
        st.markdown('<div class="nb-empty"><h2>Start with a note</h2><p>Add a PDF or text file to your library and '
                    'NoteBuddy will check it, then answer questions from it.</p></div>', unsafe_allow_html=True)
        st.button("Open library", type="primary", on_click=_go, args=("library",))
        return

    key = f"scope_{chat_id or 'new'}"
    if key not in st.session_state:
        saved = chat["note_ids"] if chat else list(titles)
        st.session_state[key] = [i for i in saved if i in titles]
    head, scope_col = st.columns([1, 1.6], vertical_alignment="center")
    head.markdown(f"### {chat['title'] if chat else 'New chat'}")
    scope = scope_col.multiselect("Notes to ask about", list(titles), format_func=lambda i: titles[i], key=key,
                                  label_visibility="collapsed", placeholder="Choose notes to ask about")
    if chat and scope != chat["note_ids"]:
        db.set_chat_notes(uid, chat_id, scope)

    history = db.list_messages(uid, chat_id) if chat else []
    for m in history:
        with st.chat_message(m["role"], avatar=":material/auto_awesome:" if m["role"] == "assistant" else None):
            st.markdown(m["content"])

    if not history:
        st.markdown('<div class="nb-empty"><h2>What are you studying?</h2><p>Ask anything about the notes you '
                    'selected above.</p></div>', unsafe_allow_html=True)
        cols = st.columns(len(SUGGESTIONS))
        for col, s in zip(cols, SUGGESTIONS):
            if col.button(s, key=f"sug_{s}"):
                st.session_state["pending_prompt"] = s
                st.rerun()

    prompt = st.chat_input("Ask about your notes") or st.session_state.pop("pending_prompt", None)
    if not prompt:
        return
    if not state.api_key():
        st.warning("Add your Gemini API key in the sidebar to start chatting.")
        return

    if not chat:
        chat_id = db.create_chat(uid, prompt.strip()[:48], scope)
        st.session_state["chat_id"] = chat_id
        st.session_state[f"scope_{chat_id}"] = scope
    db.add_message(uid, chat_id, "user", prompt)
    with st.chat_message("user"):
        st.markdown(prompt)

    selected = [n for n in (db.get_note(uid, i) for i in scope) if n]
    recent_user = " ".join(m["content"] for m in history if m["role"] == "user")[-400:]
    context = ingest.build_context(selected, f"{recent_user} {prompt}")
    system = SYSTEM.format(notes=context) if selected else SYSTEM_NO_NOTES

    with st.chat_message("assistant", avatar=":material/auto_awesome:"):
        try:
            reply = st.write_stream(llm.stream(state.cfg(), prompt, system=system, history=history[-12:]))
        except llm.LLMError as e:
            st.error(str(e))
            return
    db.add_message(uid, chat_id, "assistant", reply)
    if not chat:
        st.rerun()  # refresh the sidebar so the new chat shows up


# ───────────────────────── library ─────────────────────────
def _render_report(v: dict) -> None:
    st.markdown(ui.verdict_chip(v), unsafe_allow_html=True)
    if v.get("summary"):
        st.write(v["summary"])
    for i in v.get("issues", []):
        fix = f"<br><b>Fix:</b> {ui.escape(i['correction'])}" if i["correction"] else ""
        quote = f"<q>{ui.escape(i['excerpt'])}</q><br>" if i["excerpt"] else ""
        st.markdown(f'<div class="nb-issue {i["severity"]}">{quote}{ui.escape(i["problem"])}{fix}</div>',
                    unsafe_allow_html=True)
    if v.get("gaps"):
        st.markdown("**Missing from your notes**")
        for g in v["gaps"]:
            st.markdown(f"- {g}")
    st.caption("Checked by the AI model against general knowledge, not a textbook. Double-check anything important.")


def _check(uid: int, nid: int, text: str) -> str | None:
    try:
        db.set_verification(uid, nid, tools.verify_note(state.cfg(), text))
    except llm.LLMError as e:
        return str(e)
    return None


def _add_note(uid: int, title: str, filename: str | None, text: str, raw: bytes | None, check: bool) -> None:
    nid = db.add_note(uid, title, filename, text, raw)
    if check and state.api_key():
        err = _check(uid, nid, text)
        if err:
            st.warning(f"Saved '{title}', but the accuracy check failed: {err}")
    elif check:
        st.info(f"Saved '{title}'. Add an API key to run the accuracy check.")


def _chat_with(nid: int) -> None:
    st.session_state["page"] = "chat"
    st.session_state["chat_id"] = None
    st.session_state["scope_new"] = [nid]


def library_view() -> None:
    uid = state.user()["id"]
    st.markdown("### Library")
    check = st.toggle("Check accuracy when I add a note", value=True,
                      help="Gemini reviews each note for mistakes and gaps before you study from it.")
    tab_file, tab_text = st.tabs(["Upload files", "Paste text"])
    with tab_file:
        files = st.file_uploader("Drop PDF, DOCX, TXT or MD files", type=ingest.SUPPORTED,
                                 accept_multiple_files=True, label_visibility="collapsed")
        if files and st.button("Add to library", type="primary", key="add_files"):
            for f in files:
                with st.spinner(f"Reading {f.name}..."):
                    try:
                        raw = f.getvalue()
                        text = ingest.extract_text(f.name, raw)
                    except Exception as e:
                        st.error(f"{f.name}: {e}")
                        continue
                    _add_note(uid, f.name.rsplit(".", 1)[0], f.name, text, raw, check)
            st.rerun()
    with tab_text:
        title = st.text_input("Title", placeholder="e.g. Cell biology, chapter 3")
        body = st.text_area("Your notes", height=180, label_visibility="collapsed", placeholder="Paste your notes here")
        if st.button("Save note", type="primary", key="add_text"):
            if len(body.strip()) < 40 or not title.strip():
                st.error("Add a title and at least a few sentences.")
            else:
                with st.spinner("Saving..."):
                    _add_note(uid, title.strip(), None, ingest.clean(body), None, check)
                st.rerun()

    notes = db.list_notes(uid)
    if not notes:
        st.markdown('<div class="nb-empty"><p>Nothing here yet. Your notes will appear here and stay with your '
                    'account.</p></div>', unsafe_allow_html=True)
        return
    st.write("")
    for n in notes:
        with st.container(border=True):
            a, b = st.columns([3, 1.4], vertical_alignment="center")
            a.markdown(f"**{n['title']}**")
            a.caption(f"{n['chars']:,} characters, added {datetime.fromtimestamp(n['created']):%d %b %Y}")
            b.markdown(ui.verdict_chip(n["verification"]), unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns(4)
            c1.button("Ask", icon=":material/chat:", key=f"ask_{n['id']}", on_click=_chat_with, args=(n["id"],))
            if c2.button("Re-check", icon=":material/fact_check:", key=f"chk_{n['id']}"):
                if not state.api_key():
                    st.warning("Add your Gemini API key in the sidebar first.")
                else:
                    with st.spinner("Checking..."):
                        full = db.get_note(uid, n["id"])
                        err = _check(uid, n["id"], full["text"])
                    st.error(err) if err else st.rerun()
            if n["file_path"]:
                try:
                    with open(n["file_path"], "rb") as fh:
                        c3.download_button("Original", fh.read(), file_name=n["filename"] or "note",
                                           key=f"dl_{n['id']}", icon=":material/download:")
                except OSError:
                    pass
            with c4.popover(":material/delete:"):
                st.write("Delete this note?")
                if st.button("Yes, delete", key=f"del_note_{n['id']}", type="primary"):
                    db.delete_note(uid, n["id"])
                    st.rerun()
            if n["verification"]:
                with st.expander("Accuracy report"):
                    _render_report(n["verification"])


# ───────────────────────── router ─────────────────────────
restore_session()
if not state.user():
    auth_view()
else:
    sidebar()
    (library_view if st.session_state["page"] == "library" else chat_view)()
    panels.fab()
