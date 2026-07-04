from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    timestamp  TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS tool_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL,
    action     TEXT    NOT NULL,
    task       TEXT    NOT NULL,
    command    TEXT,
    file_path  TEXT,
    exit_code  INTEGER,
    stdout     TEXT,
    stderr     TEXT,
    approved   INTEGER NOT NULL,
    timestamp  TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS permission_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL,
    action     TEXT    NOT NULL,
    task       TEXT    NOT NULL,
    risk_level TEXT    NOT NULL,
    approved   INTEGER NOT NULL,
    message    TEXT    NOT NULL,
    timestamp  TEXT    NOT NULL
);
"""


class MemoryDB:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _ts(self) -> str:
        return datetime.now().isoformat(timespec="seconds")

    def save_message(self, session_id: str, role: str, content: str) -> None:
        self._conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,?)",
            (session_id, role, content, self._ts()),
        )
        self._conn.commit()

    def save_tool_log(self, session_id: str, request, result) -> None:
        cmd = " ".join(request.command) if request.command else None
        self._conn.execute(
            "INSERT INTO tool_logs (session_id,action,task,command,file_path,exit_code,stdout,stderr,approved,timestamp) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (session_id, request.action, request.task, cmd, request.file_path,
             result.exit_code, result.stdout, result.stderr, int(result.approved), self._ts()),
        )
        self._conn.commit()

    def save_permission_log(self, session_id: str, request, perm, approved: bool) -> None:
        self._conn.execute(
            "INSERT INTO permission_logs (session_id,action,task,risk_level,approved,message,timestamp) VALUES (?,?,?,?,?,?,?)",
            (session_id, request.action, request.task, perm.risk.value, int(approved), perm.message, self._ts()),
        )
        self._conn.commit()

    def get_recent_messages(self, session_id: str, limit: int = 20) -> list[dict]:
        cur = self._conn.execute(
            "SELECT role, content, timestamp FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        )
        return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in reversed(cur.fetchall())]

    def get_all_sessions(self) -> list[str]:
        cur = self._conn.execute(
            "SELECT session_id, MIN(timestamp) as ts FROM messages GROUP BY session_id ORDER BY ts DESC"
        )
        return [r[0] for r in cur.fetchall()]

    def get_recent_tool_logs(self, limit: int = 20) -> list[dict]:
        cur = self._conn.execute(
            "SELECT session_id,action,task,command,file_path,exit_code,approved,timestamp FROM tool_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return [{"session_id":r[0],"action":r[1],"task":r[2],"command":r[3],
                 "file_path":r[4],"exit_code":r[5],"approved":bool(r[6]),"timestamp":r[7]}
                for r in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()
