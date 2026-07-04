from __future__ import annotations

import os

from .db import MemoryDB
from .markdown import MarkdownMemory


def build_agent_context(
    session_id: str,
    db: MemoryDB,
    markdown: MarkdownMemory,
    recent_limit: int = 5,
) -> str:
    parts: list[str] = []

    long = markdown.read_long()
    project = markdown.read_project()
    has_long = "No entries yet" not in long
    has_project = "No entries yet" not in project

    if has_long or has_project:
        parts.append("=== MEMORY CONTEXT ===")
        if has_long:
            parts.append(long)
        if has_project:
            parts.append(project)
        parts.append("=== END MEMORY CONTEXT ===")

    recent = db.get_recent_messages(session_id, limit=recent_limit)
    if recent:
        parts.append("\n=== RECENT CONVERSATION ===")
        for m in recent:
            label = "User" if m["role"] == "user" else "Assistant"
            parts.append(f"[{label}] {m['content']}")
        parts.append("=== END RECENT CONVERSATION ===")

    return "\n".join(parts)


def summarize_to_long_memory(session_id: str, db: MemoryDB, markdown: MarkdownMemory) -> str:
    messages = db.get_recent_messages(session_id, limit=100)
    if not messages:
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
            api_key="ollama",
        )
        convo = "\n".join(
            f"[{'User' if m['role']=='user' else 'Assistant'}] {m['content']}"
            for m in messages
        )
        prompt = (
            f"Current long-term memory:\n{markdown.read_long()}\n\n"
            f"Session '{session_id}':\n{convo}\n\n"
            "Append a 2-3 sentence summary of this session to the long-term memory. "
            "Keep existing entries. Return complete updated markdown only."
        )
        resp = client.chat.completions.create(
            model=os.getenv("AGENT_MODEL", "gemma4:latest"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        updated = resp.choices[0].message.content or ""
        if updated.strip():
            markdown.update_long(updated.strip())
        return updated
    except Exception as exc:
        return f"(요약 실패: {exc})"
