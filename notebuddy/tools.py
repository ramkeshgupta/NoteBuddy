"""Study tools built on the LLM: accuracy check, summary, quiz and a study-plan scheduler.

The model only does the thinking (topics, questions, review). The schedule itself is built
deterministically in Python so breaks and session lengths are always sensible.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import llm
from .llm import Cfg, LLMError

MAX_CHARS = 150_000
CHECK_CHARS = 40_000


def _cap(text: str, limit: int = MAX_CHARS) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2:]
    return f"{head}\n\n[... middle of the document omitted ...]\n\n{tail}"


def _clamp(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


# ───────────────────────── accuracy check ─────────────────────────
VERIFY_SYSTEM = (
    "You are a careful subject-matter reviewer helping a student. You read their study notes and judge "
    "whether the information is correct, clear and complete enough to study from. Only flag real problems: "
    "factual errors, outdated claims, contradictions, missing key concepts. Never invent errors."
)


def verify_note(cfg: Cfg, text: str) -> dict:
    prompt = f"""Review these study notes.

Return JSON only, with this shape:
{{
  "subject": "short subject name",
  "score": 0-100 (how reliable and complete the notes are for studying),
  "summary": "two sentences max, plain language",
  "issues": [{{"excerpt": "short quote from the notes", "problem": "what is wrong", "correction": "the correct information", "severity": "low|medium|high"}}],
  "gaps": ["important topic missing from the notes"]
}}
Use empty lists if there are no issues or gaps. At most 8 issues and 6 gaps.

NOTES:
{_cap(text, CHECK_CHARS)}"""
    data = llm.parse_json(llm.generate(cfg, prompt, system=VERIFY_SYSTEM, json_mode=True, temperature=0.2))
    if not isinstance(data, dict):
        raise LLMError("Gemini's reply wasn't in the expected format. Try again.")
    score = _clamp(data.get("score"), 0, 100, 70)
    issues = []
    for i in (data.get("issues") or [])[:8]:
        if isinstance(i, dict) and i.get("problem"):
            sev = i.get("severity") if i.get("severity") in ("low", "medium", "high") else "medium"
            issues.append({"excerpt": str(i.get("excerpt", ""))[:240], "problem": str(i["problem"]),
                           "correction": str(i.get("correction", "")), "severity": sev})
    return {
        "subject": str(data.get("subject", ""))[:80],
        "score": score,
        "verdict": "solid" if score >= 80 else "needs_review" if score >= 55 else "unreliable",
        "summary": str(data.get("summary", "")),
        "issues": issues,
        "gaps": [str(g) for g in (data.get("gaps") or [])[:6]],
    }


# ───────────────────────── summary ─────────────────────────
SUMMARY_STYLES = {
    "Brief": "Exactly 5 bullet points, one short line each. Start with a one-sentence overview in bold.",
    "Standard": "A one-paragraph overview, then 6–10 bullets of the key ideas, then a 'Key terms' list with one-line definitions.",
    "Detailed": "A structured summary with a heading per major topic, concise bullets under each, and a 'Key terms' list at the end.",
}


def make_summary(cfg: Cfg, text: str, style: str) -> str:
    prompt = (
        "Summarise the student's notes below using only what they contain. Simple language, no filler.\n"
        f"Format: {SUMMARY_STYLES.get(style, SUMMARY_STYLES['Standard'])}\n\nNOTES:\n{_cap(text)}"
    )
    return llm.generate(cfg, prompt, temperature=0.3).strip()


# ───────────────────────── quiz ─────────────────────────
def make_quiz(cfg: Cfg, text: str, n: int, difficulty: str) -> list[dict]:
    prompt = f"""Write a {n}-question multiple-choice quiz from the student's notes below.
Difficulty: {difficulty}. Cover different parts of the notes. Test understanding, not trivia.
Each question has exactly 4 options, one correct, and plausible wrong options.

Return JSON only:
{{"questions": [{{"question": "...", "options": ["...","...","...","..."], "answer_index": 0-3, "explanation": "one or two sentences"}}]}}

NOTES:
{_cap(text)}"""
    data = llm.parse_json(llm.generate(cfg, prompt, json_mode=True, temperature=0.6))
    raw = data.get("questions", []) if isinstance(data, dict) else data
    out = []
    for q in raw or []:
        try:
            opts = [str(o) for o in q["options"]]
            ai = int(q["answer_index"])
            if len(opts) >= 2 and 0 <= ai < len(opts) and q.get("question"):
                out.append({"question": str(q["question"]), "options": opts,
                            "answer_index": ai, "explanation": str(q.get("explanation", ""))})
        except (KeyError, TypeError, ValueError):
            continue
    if not out:
        raise LLMError("Couldn't build a quiz from that note. Try again.")
    return out[:n]


# ───────────────────────── study planner ─────────────────────────
def topic_breakdown(cfg: Cfg, text: str) -> list[dict]:
    prompt = f"""Break these notes into 4–10 study topics, in the order a student should learn them.
Weight each topic 1–5 for how much study time it needs (difficulty and volume together).

Return JSON only:
{{"topics": [{{"title": "short title", "weight": 1-5, "focus": "one sentence on what to master"}}]}}

NOTES:
{_cap(text)}"""
    data = llm.parse_json(llm.generate(cfg, prompt, json_mode=True, temperature=0.3))
    raw = data.get("topics", []) if isinstance(data, dict) else data
    topics = []
    for t in raw or []:
        if isinstance(t, dict) and t.get("title"):
            topics.append({"title": str(t["title"])[:80], "weight": _clamp(t.get("weight"), 1, 5, 3),
                           "focus": str(t.get("focus", ""))[:200]})
    if not topics:
        raise LLMError("Couldn't split that note into topics. Try again.")
    return topics[:10]


# (focus, short break, long break) in minutes
RHYTHMS = {
    "Classic: 25 on, 5 off": (25, 5, 15),
    "Deep: 50 on, 10 off": (50, 10, 25),
    "Marathon: 90 on, 20 off": (90, 20, 30),
}


def auto_rhythm(hours_per_day: float) -> str:
    if hours_per_day <= 3:
        return "Classic: 25 on, 5 off"
    return "Deep: 50 on, 10 off"


def _day_slots(day_minutes: int, focus: int, short: int, long: int, long_every: int = 4):
    slots, t, n = [], 0, 0
    while t + focus <= day_minutes:
        slots.append(("focus", focus))
        t += focus
        n += 1
        is_long = n % long_every == 0
        b = long if is_long else short
        if t + b + focus <= day_minutes:  # only rest if another session still fits
            slots.append(("long_break" if is_long else "break", b))
            t += b
        else:
            break
    return slots


def _allocate(topics: list[dict], blocks: int):
    """Split `blocks` focus sessions across topics by weight (every topic gets one if possible)."""
    if blocks <= 0:
        return [], [t["title"] for t in topics]
    skipped = []
    if blocks < len(topics):
        keep = sorted(range(len(topics)), key=lambda i: -topics[i]["weight"])[:blocks]
        skipped = [t["title"] for i, t in enumerate(topics) if i not in keep]
        topics = [t for i, t in enumerate(topics) if i in keep]
    counts = [1] * len(topics)
    extra = blocks - len(topics)
    if extra > 0:
        total_w = sum(t["weight"] for t in topics)
        quotas = [extra * t["weight"] / total_w for t in topics]
        floors = [int(q) for q in quotas]
        left = extra - sum(floors)
        by_frac = sorted(range(len(topics)), key=lambda i: -(quotas[i] - floors[i]))
        for i in by_frac[:left]:
            floors[i] += 1
        counts = [c + f for c, f in zip(counts, floors)]
    return list(zip(topics, counts)), skipped


def build_schedule(topics: list[dict], days: int, hours_per_day: float, rhythm: tuple[int, int, int],
                   start_date: date, start_time: datetime, review_share: float = 0.15) -> dict:
    focus, short, long = rhythm
    day_minutes = int(hours_per_day * 60)
    focus = min(focus, day_minutes)
    per_day = [_day_slots(day_minutes, focus, short, long) for _ in range(days)]
    total_blocks = sum(1 for d in per_day for k, _ in d if k == "focus")
    review_blocks = 0 if total_blocks < 4 else max(1, round(total_blocks * review_share))
    alloc, skipped = _allocate(topics, total_blocks - review_blocks)

    labels: list[tuple[str, str]] = []  # (title, detail) per focus session
    for t, count in alloc:
        for part in range(1, count + 1):
            title = t["title"] if count == 1 else f"{t['title']} (part {part} of {count})"
            labels.append((title, t["focus"] if part == 1 else ""))
    labels += [("Review and self-test", "Close the notes. Explain each topic from memory, then check.")] * review_blocks

    plan_days, li = [], 0
    for d_i, slots in enumerate(per_day):
        clock = datetime.combine(start_date + timedelta(days=d_i), start_time.time())
        items, focus_total = [], 0
        for kind, minutes in slots:
            end = clock + timedelta(minutes=minutes)
            if kind == "focus":
                title, detail = labels[li] if li < len(labels) else ("Free study", "")
                li += 1
                focus_total += minutes
            else:
                title, detail = ("Long break" if kind == "long_break" else "Short break"), ""
            items.append({"kind": kind, "minutes": minutes, "label": title, "detail": detail,
                          "start": clock.strftime("%H:%M"), "end": end.strftime("%H:%M")})
            clock = end
        plan_days.append({"n": d_i + 1, "date": (start_date + timedelta(days=d_i)).strftime("%a %d %b"),
                          "focus": focus_total, "items": items})
    return {"days": plan_days, "skipped": skipped,
            "totals": {"focus_minutes": sum(d["focus"] for d in plan_days), "sessions": total_blocks,
                       "review_sessions": review_blocks}}


def plan_to_markdown(title: str, plan: dict) -> str:
    out = [f"# Study plan: {title}", ""]
    t = plan["totals"]
    out.append(f"{t['sessions']} focus sessions, {t['focus_minutes']} minutes of study in total.\n")
    for d in plan["days"]:
        out.append(f"## Day {d['n']} ({d['date']})")
        for it in d["items"]:
            line = f"- {it['start']}-{it['end']}  {it['label']} ({it['minutes']} min)"
            if it["detail"]:
                line += f": {it['detail']}"
            out.append(line)
        out.append("")
    if plan["skipped"]:
        out.append("Not covered (not enough time): " + ", ".join(plan["skipped"]))
    return "\n".join(out)
