"""SQLite storage. Every read/write is scoped by user_id so accounts never see each other's data."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.environ.get("NOTEBUDDY_DATA", "data"))
DB_PATH = DATA_DIR / "notebuddy.db"
FILES_DIR = DATA_DIR / "files"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email        TEXT,
    pw_hash      TEXT NOT NULL,
    salt         TEXT NOT NULL,
    failed       INTEGER NOT NULL DEFAULT 0,
    locked_until REAL NOT NULL DEFAULT 0,
    created      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    filename     TEXT,
    file_path    TEXT,
    text         TEXT NOT NULL,
    chars        INTEGER NOT NULL,
    verification TEXT,
    created      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chats (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title    TEXT NOT NULL,
    note_ids TEXT NOT NULL DEFAULT '[]',
    created  REAL NOT NULL,
    updated  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role    TEXT NOT NULL,
    content TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS artifacts (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    note_id INTEGER REFERENCES notes(id) ON DELETE CASCADE,
    kind    TEXT NOT NULL,
    payload TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_user    ON notes(user_id);
CREATE INDEX IF NOT EXISTS idx_chats_user    ON chats(user_id, updated DESC);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id);
"""


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    with conn() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ───────────────────────── users & sessions ─────────────────────────
def create_user(username: str, email: str, pw_hash: str, salt: str) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO users(username,email,pw_hash,salt,created) VALUES(?,?,?,?,?)",
            (username, email, pw_hash, salt, time.time()),
        )
        return cur.lastrowid


def get_user_by_name(username: str):
    with conn() as c:
        return c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()


def record_login(user_id: int, ok: bool, max_fails: int = 5, lock_seconds: int = 300) -> None:
    with conn() as c:
        if ok:
            c.execute("UPDATE users SET failed=0, locked_until=0 WHERE id=?", (user_id,))
            return
        row = c.execute("SELECT failed FROM users WHERE id=?", (user_id,)).fetchone()
        failed = (row["failed"] if row else 0) + 1
        locked = time.time() + lock_seconds if failed >= max_fails else 0
        c.execute(
            "UPDATE users SET failed=?, locked_until=? WHERE id=?",
            (0 if locked else failed, locked, user_id),
        )


def create_session(user_id: int, token: str, days: int = 14) -> None:
    with conn() as c:
        c.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
        c.execute(
            "INSERT INTO sessions(token_hash,user_id,expires) VALUES(?,?,?)",
            (_hash_token(token), user_id, time.time() + days * 86400),
        )


def get_user_by_session(token: str):
    with conn() as c:
        row = c.execute(
            """SELECT u.id, u.username, u.email FROM sessions s
               JOIN users u ON u.id = s.user_id
               WHERE s.token_hash=? AND s.expires>?""",
            (_hash_token(token), time.time()),
        ).fetchone()
        return dict(row) if row else None


def delete_session(token: str) -> None:
    with conn() as c:
        c.execute("DELETE FROM sessions WHERE token_hash=?", (_hash_token(token),))


# ───────────────────────── notes ─────────────────────────
def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:80] or "note"


def add_note(user_id: int, title: str, filename: str | None, text: str, raw: bytes | None = None) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO notes(user_id,title,filename,text,chars,created) VALUES(?,?,?,?,?,?)",
            (user_id, title, filename, text, len(text), time.time()),
        )
        nid = cur.lastrowid
        if raw is not None and filename:
            folder = FILES_DIR / str(user_id)
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{nid}_{_safe_name(filename)}"
            path.write_bytes(raw)
            c.execute("UPDATE notes SET file_path=? WHERE id=?", (str(path), nid))
        return nid


def _note_row(r) -> dict:
    d = dict(r)
    d["verification"] = json.loads(d["verification"]) if d.get("verification") else None
    return d


def list_notes(user_id: int) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            """SELECT id,title,filename,file_path,chars,verification,created
               FROM notes WHERE user_id=? ORDER BY created DESC""",
            (user_id,),
        ).fetchall()
    return [_note_row(r) for r in rows]


def get_note(user_id: int, note_id: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM notes WHERE id=? AND user_id=?", (note_id, user_id)).fetchone()
    return _note_row(r) if r else None


def set_verification(user_id: int, note_id: int, result: dict) -> None:
    with conn() as c:
        c.execute(
            "UPDATE notes SET verification=? WHERE id=? AND user_id=?",
            (json.dumps(result), note_id, user_id),
        )


def delete_note(user_id: int, note_id: int) -> None:
    with conn() as c:
        r = c.execute("SELECT file_path FROM notes WHERE id=? AND user_id=?", (note_id, user_id)).fetchone()
        if not r:
            return
        c.execute("DELETE FROM notes WHERE id=? AND user_id=?", (note_id, user_id))
    if r["file_path"]:
        try:
            Path(r["file_path"]).unlink(missing_ok=True)
        except OSError:
            pass


# ───────────────────────── chats ─────────────────────────
def create_chat(user_id: int, title: str, note_ids: list[int]) -> int:
    now = time.time()
    with conn() as c:
        cur = c.execute(
            "INSERT INTO chats(user_id,title,note_ids,created,updated) VALUES(?,?,?,?,?)",
            (user_id, title, json.dumps(note_ids), now, now),
        )
        return cur.lastrowid


def list_chats(user_id: int, limit: int = 40) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT id,title,note_ids,updated FROM chats WHERE user_id=? ORDER BY updated DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) | {"note_ids": json.loads(r["note_ids"])} for r in rows]


def get_chat(user_id: int, chat_id: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM chats WHERE id=? AND user_id=?", (chat_id, user_id)).fetchone()
    return (dict(r) | {"note_ids": json.loads(r["note_ids"])}) if r else None


def set_chat_notes(user_id: int, chat_id: int, note_ids: list[int]) -> None:
    with conn() as c:
        c.execute(
            "UPDATE chats SET note_ids=? WHERE id=? AND user_id=?",
            (json.dumps(note_ids), chat_id, user_id),
        )


def delete_chat(user_id: int, chat_id: int) -> None:
    with conn() as c:
        c.execute("DELETE FROM chats WHERE id=? AND user_id=?", (chat_id, user_id))


def add_message(user_id: int, chat_id: int, role: str, content: str) -> None:
    with conn() as c:
        owns = c.execute("SELECT 1 FROM chats WHERE id=? AND user_id=?", (chat_id, user_id)).fetchone()
        if not owns:
            return
        now = time.time()
        c.execute(
            "INSERT INTO messages(chat_id,role,content,created) VALUES(?,?,?,?)",
            (chat_id, role, content, now),
        )
        c.execute("UPDATE chats SET updated=? WHERE id=?", (now, chat_id))


def list_messages(user_id: int, chat_id: int) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            """SELECT m.role, m.content FROM messages m
               JOIN chats ch ON ch.id = m.chat_id
               WHERE m.chat_id=? AND ch.user_id=? ORDER BY m.id""",
            (chat_id, user_id),
        ).fetchall()
    return [dict(r) for r in rows]


# ───────────────────────── generated study material ─────────────────────────
def save_artifact(user_id: int, note_id: int, kind: str, payload: dict) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO artifacts(user_id,note_id,kind,payload,created) VALUES(?,?,?,?,?)",
            (user_id, note_id, kind, json.dumps(payload), time.time()),
        )


def list_artifacts(user_id: int, note_id: int, kind: str, limit: int = 10) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            """SELECT id,payload,created FROM artifacts
               WHERE user_id=? AND note_id=? AND kind=? ORDER BY id DESC LIMIT ?""",
            (user_id, note_id, kind, limit),
        ).fetchall()
    return [{"id": r["id"], "created": r["created"], "payload": json.loads(r["payload"])} for r in rows]
