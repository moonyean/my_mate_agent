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
    """Build memory context string to prepend to the user's message."""
    parts: list[str] = []

    long_mem = markdown.read_long_memory()
    project_mem = markdown.read_project_memory()
    has_long = "No entries yet" not in long_mem
    has_project = "No entries yet" not in project_mem
    if has_long or has_project:
        parts.append("=== MEMORY CONTEXT ===")
        if has_long:
            parts.append(long_mem)
        if has_project:
            parts.append(project_mem)
        parts.append("=== END MEMORY CONTEXT ===")

    recent = db.get_recent_messages(session_id, limit=recent_limit)
    if recent:
        parts.append("\n=== RECENT CONVERSATION (this session) ===")
        for msg in recent:
            label = "User" if msg["role"] == "user" else "Assistant"
            parts.append(f"[{label}] {msg['content']}")
        parts.append("=== END RECENT CONVERSATION ===")

    return "\n".join(parts)


def summarize_to_long_memory(
    session_id: str,
    db: MemoryDB,
    markdown: MarkdownMemory,
) -> str:
    """Summarize completed session and append to long_memory.md via Ollama directly."""
    messages = db.get_recent_messages(session_id, limit=100)
    if not messages:
        return ""

    try:
        from openai import OpenAI

        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
        model = os.getenv("AGENT_MODEL", "gemma4:latest")
        client = OpenAI(base_url=base_url, api_key="ollama")

        conversation_text = "\n".join(
            f"[{'User' if m['role'] == 'user' else 'Assistant'}] {m['content']}"
            for m in messages
        )
        current_memory = markdown.read_long_memory()

        prompt = (
            f"Current long-term memory:\n{current_memory}\n\n"
            f"Session '{session_id}' conversation:\n{conversation_text}\n\n"
            "Add a brief (2-3 sentence) summary of what was accomplished in this session "
            "to the long-term memory. Keep all existing entries intact. "
            "Respond with the complete updated markdown content ONLY — no extra text."
        )

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        updated = response.choices[0].message.content or ""
        if updated.strip():
            markdown.update_long_memory(updated.strip())
        return updated
    except Exception as exc:
        return f"(요약 실패: {exc})"
