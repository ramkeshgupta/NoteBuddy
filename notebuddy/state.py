"""Small helpers around st.session_state: current user, API key and model."""
from __future__ import annotations

import os

import streamlit as st

from .llm import Cfg

MODEL_PRESETS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "Custom...",
]


def user() -> dict | None:
    return st.session_state.get("user")


def current_model() -> str:
    choice = st.session_state.get("model_choice", MODEL_PRESETS[0])
    if choice == "Custom...":
        return (st.session_state.get("model_custom") or MODEL_PRESETS[0]).strip()
    return choice


def api_key() -> str:
    return (st.session_state.get("api_key") or "").strip()


def cfg() -> Cfg:
    return Cfg(api_key(), current_model())


def init_defaults() -> None:
    st.session_state.setdefault("api_key", os.environ.get("GEMINI_API_KEY", ""))
    st.session_state.setdefault("model_choice", MODEL_PRESETS[0])
    st.session_state.setdefault("page", "chat")
    st.session_state.setdefault("chat_id", None)
