"""Look and feel: a quiet, cool-grey canvas with one teal accent and a floating study-tools button."""
from __future__ import annotations

from html import escape

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

:root{
  --paper:#F5F6F4; --surface:#FFFFFF; --ink:#171A1F; --muted:#6A717C; --line:#E3E6E8;
  --accent:#0E7C86; --accent-ink:#0A5C64; --accent-soft:#E2F2F3;
  --ok:#2F855A; --ok-soft:#E6F4EC; --warn:#B7791F; --warn-soft:#FBF1DD; --bad:#C0392B; --bad-soft:#FBE9E6;
  --radius:14px;
}
html, body, .stApp, button, input, textarea, p, li, label, h1, h2, h3, h4 { font-family:'Manrope', system-ui, sans-serif; }
/* keep Streamlit's icon font intact so icon names render as icons, not text */
[data-testid="stIconMaterial"], span[class*="material"], .material-icons, .material-symbols-rounded {
  font-family:'Material Symbols Rounded' !important; font-feature-settings:'liga'; font-weight:400; letter-spacing:normal; text-transform:none; }
.stApp { background:var(--paper); color:var(--ink); }
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { display:none !important; }
header[data-testid="stHeader"] { background:transparent; }
.block-container { max-width:880px; padding-top:2rem; padding-bottom:8rem; }
h1,h2,h3 { letter-spacing:-0.02em; font-weight:800; color:var(--ink); }
h3 { font-size:1.15rem; margin:0; padding:0; }
p, li { line-height:1.62; }
a { color:var(--accent); }
:focus-visible { outline:2px solid var(--accent) !important; outline-offset:2px; }

/* sidebar */
[data-testid="stSidebar"] { background:var(--surface); border-right:1px solid var(--line); }
[data-testid="stSidebar"] .block-container, [data-testid="stSidebarUserContent"] { padding-top:1.2rem; }
[data-testid="stSidebar"] .stButton > button { justify-content:flex-start; text-align:left; width:100%;
  border:1px solid transparent; background:transparent; color:var(--ink); font-weight:600; padding:.45rem .7rem; }
[data-testid="stSidebar"] .stButton > button:hover { background:#F0F2F3; border-color:transparent; color:var(--ink); }
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] { background:var(--accent-soft); color:var(--accent-ink); }
[data-testid="stSidebar"] .stButton > button p { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.nb-label { font-size:.78rem; font-weight:700; color:var(--muted); margin:1.1rem 0 .3rem .2rem; }

/* brand */
.nb-brand { display:flex; align-items:center; gap:.6rem; font-weight:800; font-size:1.2rem; letter-spacing:-0.03em; }
.nb-mark { width:30px; height:30px; border-radius:9px; background:var(--ink); display:grid; place-items:center; }
.nb-hero { margin:12vh 0 1.4rem; }
.nb-hero .nb-brand { font-size:1.6rem; }
.nb-hero p { color:var(--muted); margin:.5rem 0 0; font-size:1.02rem; }

/* buttons */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {
  border-radius:10px; border:1px solid var(--line); background:var(--surface); color:var(--ink);
  font-weight:600; transition:border-color .15s, background .15s, transform .05s; }
.stButton > button:hover, .stDownloadButton > button:hover { border-color:var(--accent); color:var(--accent-ink); }
.stButton > button:active { transform:scale(.98); }
button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-primaryFormSubmit"] {
  background:var(--accent); color:#fff; border-color:var(--accent); }
button[data-testid="stBaseButton-primary"]:hover, button[data-testid="stBaseButton-primaryFormSubmit"]:hover {
  background:var(--accent-ink); border-color:var(--accent-ink); color:#fff; }
[data-testid="stForm"] { border:1px solid var(--line); border-radius:var(--radius); background:var(--surface); padding:1.1rem; }
[data-testid="stForm"] button { width:100%; }

/* inputs */
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] { border-radius:10px !important; }
[data-testid="stFileUploaderDropzone"] { border:1.5px dashed #C9CED3; background:var(--surface); border-radius:var(--radius); }
[data-testid="stFileUploaderDropzone"]:hover { border-color:var(--accent); }
[data-testid="stExpander"], [data-testid="stVerticalBlockBorderWrapper"] { border-radius:var(--radius); }
[data-testid="stExpander"] { border:1px solid var(--line); background:var(--surface); }
[data-testid="stTabs"] [role="tab"] { font-weight:700; }

/* chat */
[data-testid="stChatMessage"] { background:transparent; padding:.55rem 0; gap:.85rem; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
  background:var(--surface); border:1px solid var(--line); border-radius:var(--radius); padding:.7rem .9rem; }
[data-testid="stChatMessageAvatarAssistant"] { background:var(--ink); color:#fff; }
[data-testid="stChatMessageAvatarUser"] { background:var(--accent-soft); color:var(--accent-ink); }
[data-testid="stBottom"], [data-testid="stBottom"] > div { background:var(--paper); }
[data-testid="stChatInput"] { border-radius:16px; border:1px solid var(--line); background:var(--surface);
  box-shadow:0 10px 30px rgba(23,26,31,.07); }
[data-testid="stChatInput"]:focus-within { border-color:var(--accent); }

/* empty state */
.nb-empty { padding:2.2rem 0 1rem; }
.nb-empty h2 { font-size:1.9rem; margin:0 0 .4rem; }
.nb-empty p { color:var(--muted); margin:0 0 1.2rem; }

/* chips */
.nb-chip { display:inline-block; padding:.18rem .6rem; border-radius:999px; font-size:.78rem; font-weight:700; }
.nb-chip.ok { background:var(--ok-soft); color:var(--ok); }
.nb-chip.warn { background:var(--warn-soft); color:var(--warn); }
.nb-chip.bad { background:var(--bad-soft); color:var(--bad); }
.nb-chip.mute { background:#EEF0F1; color:var(--muted); }
.nb-issue { border-left:3px solid var(--line); padding:.2rem 0 .2rem .8rem; margin:.7rem 0; }
.nb-issue.high { border-color:var(--bad); } .nb-issue.medium { border-color:var(--warn); }
.nb-issue q { color:var(--muted); font-style:normal; }

/* floating study tools */
.st-key-fab { position:fixed; right:28px; bottom:92px; z-index:1000; width:auto !important; }
.st-key-fab button { height:52px; border-radius:26px; padding:0 1.15rem 0 1rem; background:var(--ink); color:#fff;
  border:none; font-weight:700; box-shadow:0 12px 28px rgba(23,26,31,.28), 0 0 0 4px rgba(14,124,134,.14);
  transition:transform .15s, box-shadow .15s; }
.st-key-fab button:hover { background:var(--ink); color:#fff; transform:translateY(-2px);
  box-shadow:0 16px 34px rgba(23,26,31,.32), 0 0 0 6px rgba(14,124,134,.2); }
.st-key-fab button * { color:#fff !important; }
[data-testid="stPopoverBody"] { border-radius:var(--radius); min-width:230px; padding:.6rem; }
[data-testid="stPopoverBody"] .stButton > button { width:100%; justify-content:flex-start; border-color:transparent; background:transparent; }
[data-testid="stPopoverBody"] .stButton > button:hover { background:var(--accent-soft); }
@media (max-width:640px){ .st-key-fab{ right:16px; bottom:84px; } .block-container{ padding-left:1rem; padding-right:1rem; } }

/* study plan */
.nb-day { background:var(--surface); border:1px solid var(--line); border-radius:var(--radius); padding:.9rem 1rem; margin:0 0 .9rem; }
.nb-day-h { display:flex; gap:.8rem; align-items:baseline; margin-bottom:.5rem; }
.nb-day-h span { color:var(--muted); font-size:.85rem; }
.nb-slot { display:grid; grid-template-columns:3.4rem 4px 1fr auto; gap:.7rem; align-items:center; padding:.32rem 0; }
.nb-slot .t { color:var(--muted); font-size:.85rem; font-variant-numeric:tabular-nums; }
.nb-slot .bar { align-self:stretch; border-radius:4px; background:var(--accent); }
.nb-slot.break .bar { background:#D5DADE; } .nb-slot.long_break .bar { background:#9FD0D4; }
.nb-slot .l { font-weight:600; } .nb-slot .l small { display:block; color:var(--muted); font-weight:500; }
.nb-slot.break .l, .nb-slot.long_break .l { color:var(--muted); font-weight:500; }
.nb-slot .m { color:var(--muted); font-size:.85rem; }

@media (prefers-reduced-motion:reduce){ * { transition:none !important; animation:none !important; } }
</style>
"""

MARK = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" '
        'stroke-linecap="round"><path d="M5 7h14M5 12h9M5 17h5"/></svg>')


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def brand(hero: bool = False, tagline: str = "") -> None:
    html = f'<div class="nb-brand"><span class="nb-mark">{MARK}</span>NoteBuddy</div>'
    if hero:
        html = f'<div class="nb-hero">{html}<p>{escape(tagline)}</p></div>'
    st.markdown(html, unsafe_allow_html=True)


def chip(text: str, tone: str = "mute") -> str:
    return f'<span class="nb-chip {tone}">{escape(text)}</span>'


def verdict_chip(v: dict | None) -> str:
    if not v:
        return chip("Not checked", "mute")
    tone = {"solid": "ok", "needs_review": "warn", "unreliable": "bad"}.get(v["verdict"], "mute")
    label = {"solid": "Looks solid", "needs_review": "Needs review", "unreliable": "Unreliable"}[v["verdict"]]
    return chip(f"{label} · {v['score']}/100", tone)


def plan_html(plan: dict) -> str:
    out = []
    for d in plan["days"]:
        rows = []
        for it in d["items"]:
            detail = f"<small>{escape(it['detail'])}</small>" if it["detail"] else ""
            rows.append(
                f'<div class="nb-slot {it["kind"]}"><span class="t">{it["start"]}</span><span class="bar"></span>'
                f'<span class="l">{escape(it["label"])}{detail}</span><span class="m">{it["minutes"]} min</span></div>'
            )
        out.append(
            f'<div class="nb-day"><div class="nb-day-h"><b>Day {d["n"]}</b><span>{escape(d["date"])}</span>'
            f'<span>{d["focus"]} min of focus</span></div>{"".join(rows)}</div>'
        )
    return "".join(out)
