"""Thin Gemini REST client. The key and model are passed per call, so they can be swapped live from the UI."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterator

import requests

BASE = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT = (10, 120)


class LLMError(Exception):
    """A problem worth showing to the person using the app."""


@dataclass(frozen=True)
class Cfg:
    api_key: str
    model: str


def _headers(key: str) -> dict:
    return {"x-goog-api-key": key, "Content-Type": "application/json"}


def _body(contents, system, json_mode, temperature) -> dict:
    body = {"contents": contents, "generationConfig": {"temperature": temperature}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    return body


def to_contents(history: list[dict], prompt: str) -> list[dict]:
    """Map chat history ({'role','content'}) to Gemini's format and append the new prompt."""
    out = []
    for m in history:
        role = "model" if m["role"] == "assistant" else "user"
        if not out and role == "model":
            continue  # Gemini expects the conversation to open with the user
        out.append({"role": role, "parts": [{"text": m["content"]}]})
    out.append({"role": "user", "parts": [{"text": prompt}]})
    return out


def _explain(status: int, text: str) -> str:
    try:
        detail = json.loads(text).get("error", {}).get("message", "")
    except Exception:
        detail = text[:200]
    low = detail.lower()
    if status in (400, 401, 403) and ("api key" in low or "api_key" in low or "permission" in low):
        return "Gemini rejected that API key. Check it in the sidebar and try again."
    if status == 404:
        return "That model name wasn't found. Pick another model in the sidebar."
    if status == 429:
        return "You've hit the Gemini rate limit or free quota. Wait a minute, or switch to another key or model."
    if status >= 500:
        return "Gemini is having trouble right now. Try again in a moment."
    return f"Gemini returned an error ({status}): {detail or 'unknown error'}"


def _text_of(obj: dict) -> str:
    cands = obj.get("candidates") or []
    if not cands:
        reason = (obj.get("promptFeedback") or {}).get("blockReason")
        if reason:
            raise LLMError(f"Gemini blocked that request ({reason.lower()}). Try rephrasing.")
        return ""
    parts = (cands[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def _check_key(cfg: Cfg) -> None:
    if not cfg.api_key:
        raise LLMError("Add your Gemini API key in the sidebar first.")


def generate(cfg: Cfg, prompt: str, system: str | None = None, history: list[dict] | None = None,
             json_mode: bool = False, temperature: float = 0.4) -> str:
    _check_key(cfg)
    contents = to_contents(history or [], prompt)
    url = f"{BASE}/models/{cfg.model}:generateContent"
    try:
        r = requests.post(url, headers=_headers(cfg.api_key),
                          json=_body(contents, system, json_mode, temperature), timeout=TIMEOUT)
    except requests.RequestException:
        raise LLMError("Couldn't reach Gemini. Check your internet connection.") from None
    if r.status_code != 200:
        raise LLMError(_explain(r.status_code, r.text))
    text = _text_of(r.json())
    if not text.strip():
        raise LLMError("Gemini sent back an empty answer. Try again.")
    return text


def stream(cfg: Cfg, prompt: str, system: str | None = None, history: list[dict] | None = None,
           temperature: float = 0.3) -> Iterator[str]:
    _check_key(cfg)
    contents = to_contents(history or [], prompt)
    url = f"{BASE}/models/{cfg.model}:streamGenerateContent?alt=sse"
    try:
        r = requests.post(url, headers=_headers(cfg.api_key),
                          json=_body(contents, system, False, temperature), timeout=TIMEOUT, stream=True)
    except requests.RequestException:
        raise LLMError("Couldn't reach Gemini. Check your internet connection.") from None
    if r.status_code != 200:
        raise LLMError(_explain(r.status_code, r.text))
    got_any = False
    for raw in r.iter_lines():
        if not raw:
            continue
        line = raw.decode("utf-8", errors="ignore")
        if not line.startswith("data:"):
            continue
        try:
            chunk = _text_of(json.loads(line[5:].strip()))
        except json.JSONDecodeError:
            continue
        if chunk:
            got_any = True
            yield chunk
    if not got_any:
        raise LLMError("Gemini sent back an empty answer. Try again.")


def parse_json(text: str):
    """Parse model JSON, tolerating code fences and stray prose."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        a, b = t.find(open_c), t.rfind(close_c)
        if a != -1 and b > a:
            try:
                return json.loads(t[a:b + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError("Gemini's reply wasn't in the expected format. Try again.")


def test_key(cfg: Cfg) -> None:
    generate(cfg, "Reply with the single word: ok", temperature=0)
