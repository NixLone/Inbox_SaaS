import os
import sqlite3
import secrets
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional, Tuple


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(db_path: str) -> None:
    conn = _connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_chat_id INTEGER UNIQUE,
                token TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT,
                phone TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_clients_user_phone ON clients(user_id, phone);

            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                client_id INTEGER,
                source TEXT NOT NULL,
                name TEXT,
                phone TEXT,
                text TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                tg_chat_id INTEGER,
                tg_message_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_leads_user_created ON leads(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_leads_user_status ON leads(user_id, status);
            """
        )
        conn.commit()
    finally:
        conn.close()


def _gen_token() -> str:
    # URL-safe token, short enough to copy
    return secrets.token_urlsafe(16)


def get_or_create_user_by_chat_id(db_path: str, tg_chat_id: int) -> Dict[str, Any]:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM users WHERE tg_chat_id = ?", (tg_chat_id,)).fetchone()
        if row:
            return dict(row)

        # Ensure token uniqueness
        token = _gen_token()
        while conn.execute("SELECT 1 FROM users WHERE token = ?", (token,)).fetchone():
            token = _gen_token()

        conn.execute(
            "INSERT INTO users (tg_chat_id, token, created_at) VALUES (?, ?, ?)",
            (tg_chat_id, token, utc_now_iso()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE tg_chat_id = ?", (tg_chat_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_user_by_token(db_path: str, token: str) -> Optional[Dict[str, Any]]:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM users WHERE token = ?", (token,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_client(db_path: str, user_id: int, name: Optional[str], phone: Optional[str]) -> Optional[int]:
    """Returns client_id or None if not enough data to create."""
    if not (name or phone):
        return None

    conn = _connect(db_path)
    try:
        if phone:
            row = conn.execute(
                "SELECT id FROM clients WHERE user_id = ? AND phone = ? ORDER BY id DESC LIMIT 1",
                (user_id, phone),
            ).fetchone()
            if row:
                # Optionally update name
                if name:
                    conn.execute("UPDATE clients SET name = COALESCE(?, name) WHERE id = ?", (name, row["id"]))
                    conn.commit()
                return int(row["id"])

        conn.execute(
            "INSERT INTO clients (user_id, name, phone, created_at) VALUES (?, ?, ?, ?)",
            (user_id, name, phone, utc_now_iso()),
        )
        conn.commit()
        return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
    finally:
        conn.close()


def create_lead(
    db_path: str,
    user_id: int,
    source: str,
    text: str,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    client_id: Optional[int] = None,
    status: str = "new",
    tg_chat_id: Optional[int] = None,
) -> int:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO leads (user_id, client_id, source, name, phone, text, status, created_at, tg_chat_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, client_id, source, name, phone, text, status, utc_now_iso(), tg_chat_id),
        )
        conn.commit()
        return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
    finally:
        conn.close()


def set_lead_status(db_path: str, lead_id: int, status: str) -> None:
    conn = _connect(db_path)
    try:
        conn.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id))
        conn.commit()
    finally:
        conn.close()


def set_lead_telegram_message(db_path: str, lead_id: int, tg_message_id: int, tg_chat_id: int) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "UPDATE leads SET tg_message_id = ?, tg_chat_id = ? WHERE id = ?",
            (tg_message_id, tg_chat_id, lead_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_lead_by_id(db_path: str, lead_id: int) -> Optional[Dict[str, Any]]:
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_leads_for_day(db_path: str, user_id: int, day: date) -> List[Dict[str, Any]]:
    # Compare by date prefix in ISO timestamp; ok for UTC MVP.
    day_prefix = day.isoformat()
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT * FROM leads
            WHERE user_id = ? AND created_at LIKE ?
            ORDER BY created_at ASC
            """,
            (user_id, f"{day_prefix}%"),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_recent_leads(db_path: str, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM leads WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def find_leads_by_client(db_path: str, user_id: int, query: str, limit: int = 20) -> List[Dict[str, Any]]:
    q = f"%{query.strip()}%"
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT * FROM leads
            WHERE user_id = ? AND (
                COALESCE(name,'') LIKE ? OR COALESCE(phone,'') LIKE ? OR text LIKE ?
            )
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, q, q, q, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
