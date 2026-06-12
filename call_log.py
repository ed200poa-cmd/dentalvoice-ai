import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path("call_logs.db")


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS call_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_sid TEXT UNIQUE NOT NULL,
                caller_number TEXT,
                intent TEXT,
                outcome TEXT,
                conversation_summary TEXT,
                appointment_booked TEXT,
                transferred_to_human INTEGER DEFAULT 0,
                duration_seconds INTEGER,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_sid TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (call_sid) REFERENCES call_logs(call_sid)
            )
        """)
        conn.commit()


def create_call_record(call_sid: str, caller_number: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO call_logs (call_sid, caller_number, timestamp)
            VALUES (?, ?, ?)
            """,
            (call_sid, caller_number, datetime.utcnow().isoformat()),
        )
        conn.commit()


def update_call_record(
    call_sid: str,
    intent: str | None = None,
    outcome: str | None = None,
    appointment_booked: str | None = None,
    transferred_to_human: bool | None = None,
    conversation_summary: str | None = None,
) -> None:
    fields, values = [], []
    if intent is not None:
        fields.append("intent = ?")
        values.append(intent)
    if outcome is not None:
        fields.append("outcome = ?")
        values.append(outcome)
    if appointment_booked is not None:
        fields.append("appointment_booked = ?")
        values.append(appointment_booked)
    if transferred_to_human is not None:
        fields.append("transferred_to_human = ?")
        values.append(1 if transferred_to_human else 0)
    if conversation_summary is not None:
        fields.append("conversation_summary = ?")
        values.append(conversation_summary)

    if not fields:
        return

    values.append(call_sid)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            f"UPDATE call_logs SET {', '.join(fields)} WHERE call_sid = ?",
            values,
        )
        conn.commit()


def log_turn(call_sid: str, role: str, content: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO conversation_turns (call_sid, role, content, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (call_sid, role, content, datetime.utcnow().isoformat()),
        )
        conn.commit()


def get_all_logs() -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM call_logs ORDER BY timestamp DESC LIMIT 100"
        ).fetchall()
        return [dict(row) for row in rows]


def get_conversation(call_sid: str) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT role, content, timestamp FROM conversation_turns WHERE call_sid = ? ORDER BY id",
            (call_sid,),
        ).fetchall()
        return [dict(row) for row in rows]
