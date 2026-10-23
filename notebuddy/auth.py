"""Password hashing (PBKDF2-SHA256), login with lockout, and remember-me session tokens."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time

from . import db

ITERATIONS = 240_000
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,24}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS).hex()


def register(username: str, email: str, password: str, confirm: str) -> tuple[dict | None, str | None]:
    username, email = username.strip(), email.strip()
    if not USERNAME_RE.match(username):
        return None, "Usernames are 3–24 characters: letters, numbers, dot, dash or underscore."
    if email and not EMAIL_RE.match(email):
        return None, "That email address doesn't look right."
    if len(password) < 8:
        return None, "Use a password with at least 8 characters."
    if password != confirm:
        return None, "The two passwords don't match."
    salt = os.urandom(16)
    try:
        uid = db.create_user(username, email, _hash(password, salt), salt.hex())
    except sqlite3.IntegrityError:
        return None, "That username is taken. Try another one."
    return {"id": uid, "username": username, "email": email}, None


def login(username: str, password: str) -> tuple[dict | None, str | None]:
    row = db.get_user_by_name(username.strip())
    generic = "Username or password is incorrect."
    if not row:
        _hash(password, b"0" * 16)  # keep timing similar for unknown users
        return None, generic
    if row["locked_until"] > time.time():
        mins = int((row["locked_until"] - time.time()) // 60) + 1
        return None, f"Too many attempts. Try again in about {mins} min."
    ok = hmac.compare_digest(_hash(password, bytes.fromhex(row["salt"])), row["pw_hash"])
    db.record_login(row["id"], ok)
    if not ok:
        return None, generic
    return {"id": row["id"], "username": row["username"], "email": row["email"]}, None


def new_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db.create_session(user_id, token)
    return token
