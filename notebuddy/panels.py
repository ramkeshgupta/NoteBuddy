"""Floating 'Study tools' button and the three dialogs it opens: quiz, summary, study planner."""
from __future__ import annotations

from datetime import date, datetime, time as dtime

import streamlit as st

from . import db, llm, state, tools, ui


# ───────────────────────── shared bits ─────────────────────────
def _pick_note(key: str) -> dict | None:
    uid = state.user()["id"]
    notes = db.list_notes(uid)
    if not notes:
        st.info("Upload a note in your Library first, then come back here.")
        return None
    ids = [n["id"] for n in notes]
    titles = {n["id"]: n["title"] for n in notes}
    last = st.session_state.get("last_note")
    nid = st.selectbox("Note", ids, index=ids.index(last) if last in ids else 0,
                       format_func=lambda i: titles[i], key=key)
    st.session_state["last_note"] = nid
    return db.get_note(uid, nid)


def _ready() -> bool:
    if not state.api_key():
        st.warning("Add your Gemini API key in the sidebar to use this.")
        return False
    return True


def _clear(prefix: str) -> None:
    for k in [k for k in st.session_state if k.startswith(prefix)]:
        del st.session_state[k]


# ───────────────────────── quiz ─────────────────────────
@st.dialog("Quick quiz", width="large")
def quiz_dialog() -> None:
    note = _pick_note("quiz_note")
    if not note or not _ready():
        return
    uid = state.user()["id"]
    quiz = st.session_state.get("quiz")
    if quiz and quiz["note_id"] != note["id"]:
        quiz = None
        st.session_state.pop("quiz", None)
        _clear("quiz_q")

    if not quiz:
        c1, c2 = st.columns(2)
        n = c1.slider("Questions", 5, 10, 7, key="quiz_n")
        level = c2.select_slider("Difficulty", ["Easy", "Mixed", "Hard"], value="Mixed", key="quiz_level")
        if st.button("Generate quiz", type="primary"):
            with st.spinner("Writing questions from your note..."):
                try:
                    qs = tools.make_quiz(state.cfg(), note["text"], n, level)
                except llm.LLMError as e:
                    st.error(str(e))
                    return
            st.session_state["quiz"] = {"note_id": note["id"], "questions": qs, "answers": None}
            db.save_artifact(uid, note["id"], "quiz", {"questions": qs, "level": level})
            st.rerun(scope="fragment")
        return

    qs = quiz["questions"]
    if quiz["answers"] is None:
        with st.form("quiz_form"):
            picks = [st.radio(f"**{i + 1}. {q['question']}**", q["options"], index=None, key=f"quiz_q{i}")
                     for i, q in enumerate(qs)]
            submitted = st.form_submit_button("Check answers", type="primary")
        if submitted:
            quiz["answers"] = [q["options"].index(p) if p is not None else None for q, p in zip(qs, picks)]
            st.rerun(scope="fragment")
        return

    score = sum(1 for q, a in zip(qs, quiz["answers"]) if a == q["answer_index"])
    st.markdown(f"### You got {score} of {len(qs)}")
    st.progress(score / len(qs))
    for i, (q, a) in enumerate(zip(qs, quiz["answers"])):
        right = a == q["answer_index"]
        st.markdown(f"**{i + 1}. {q['question']}**")
        correct = q["options"][q["answer_index"]]
        if right:
            st.success(f"Correct: {correct}")
        else:
            mine = "No answer" if a is None else q["options"][a]
            st.error(f"Your answer: {mine}\n\nCorrect: {correct}")
        if q["explanation"]:
            st.caption(q["explanation"])
    c1, c2 = st.columns(2)
    if c1.button("Retake same quiz"):
        quiz["answers"] = None
        _clear("quiz_q")
        st.rerun(scope="fragment")
    if c2.button("New quiz", type="primary"):
        st.session_state.pop("quiz", None)
        _clear("quiz_q")
        st.rerun(scope="fragment")


# ───────────────────────── summary ─────────────────────────
@st.dialog("Quick summary", width="large")
def summary_dialog() -> None:
    note = _pick_note("sum_note")
    if not note or not _ready():
        return
    uid = state.user()["id"]
    style = st.radio("Length", list(tools.SUMMARY_STYLES), index=0, horizontal=True, key="sum_style")
    if st.button("Summarise", type="primary"):
        with st.spinner("Reading your note..."):
            try:
                text = tools.make_summary(state.cfg(), note["text"], style)
            except llm.LLMError as e:
                st.error(str(e))
                return
        st.session_state["summary"] = {"note_id": note["id"], "style": style, "text": text}
        db.save_artifact(uid, note["id"], "summary", {"style": style, "text": text})
    s = st.session_state.get("summary")
    if s and s["note_id"] == note["id"]:
        st.divider()
        st.markdown(s["text"])
        st.download_button("Download as Markdown", s["text"], file_name=f"{note['title']} summary.md",
                           mime="text/markdown")


# ───────────────────────── planner ─────────────────────────
@st.dialog("Study planner", width="large")
def planner_dialog() -> None:
    note = _pick_note("plan_note")
    if not note or not _ready():
        return
    c1, c2, c3 = st.columns(3)
    days = c1.number_input("Days to study", 1, 30, 3, key="plan_days")
    hours = c2.number_input("Hours per day", 0.5, 10.0, 2.0, step=0.5, key="plan_hours")
    start = c3.date_input("Start date", date.today(), key="plan_date")
    c4, c5 = st.columns(2)
    at = c4.time_input("Daily start time", dtime(18, 0), key="plan_time")
    options = ["Auto (recommended)"] + list(tools.RHYTHMS)
    choice = c5.selectbox("Session rhythm", options, key="plan_rhythm",
                          help="Auto picks short sessions for light days and longer ones for heavy days.")
    name = tools.auto_rhythm(hours) if choice.startswith("Auto") else choice
    focus, short, long = tools.RHYTHMS[name]
    st.caption(f"{name}. A longer {long}-minute break comes after every fourth session, "
               "and the last sessions are kept for review.")

    if st.button("Build my plan", type="primary"):
        cache = st.session_state.setdefault("topics", {})
        if note["id"] not in cache:
            with st.spinner("Splitting your note into topics..."):
                try:
                    cache[note["id"]] = tools.topic_breakdown(state.cfg(), note["text"])
                except llm.LLMError as e:
                    st.error(str(e))
                    return
        plan = tools.build_schedule(cache[note["id"]], int(days), float(hours), (focus, short, long),
                                    start, datetime.combine(start, at))
        st.session_state["plan"] = {"note_id": note["id"], "title": note["title"], "data": plan}
        db.save_artifact(state.user()["id"], note["id"], "plan", plan)

    p = st.session_state.get("plan")
    if p and p["note_id"] == note["id"]:
        plan = p["data"]
        t = plan["totals"]
        st.markdown(f"**{t['sessions']} focus sessions**, {t['focus_minutes']} minutes of study, "
                    f"{t['review_sessions']} kept for review.")
        if plan["skipped"]:
            st.warning("Not enough time to cover: " + ", ".join(plan["skipped"]) + ". Add days or hours to include them.")
        st.markdown(ui.plan_html(plan), unsafe_allow_html=True)
        st.download_button("Download plan", tools.plan_to_markdown(p["title"], plan),
                           file_name=f"{p['title']} study plan.md", mime="text/markdown")


# ───────────────────────── the floating button ─────────────────────────
def fab() -> None:
    with st.container(key="fab"):
        with st.popover("Study tools", icon=":material/auto_awesome:"):
            if st.button("Quick quiz", icon=":material/quiz:", key="fab_quiz"):
                quiz_dialog()
            if st.button("Summary", icon=":material/subject:", key="fab_sum"):
                summary_dialog()
            if st.button("Study planner", icon=":material/event_note:", key="fab_plan"):
                planner_dialog()
