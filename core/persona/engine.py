from __future__ import annotations

from .schema import Persona

_BASE_TOOL = """
For every user request respond with a JSON object ONLY:

{
  "action": "run_command" | "write_file" | "respond",
  "task": "<short description>",
  "reason": "<why>",
  "text": "<reply with *actions* — required when action=respond>",
  "command": ["<exe>", "<arg1>", ...],
  "cwd": null,
  "file_path": "<filename>",
  "content": "<file content>"
}

Rules:
- Use "respond" for ANY conversational input. Include *character actions* in asterisks.
- Use "write_file" to create/overwrite files.
- Use "run_command" for system tasks. Prefer PowerShell on Windows.
- Never use shell redirection (>, |) in command arrays.
- If user says delete/삭제/지워 → use Remove-Item, never substitute with listing.
- Output ONLY the JSON. No markdown fences, no explanation.
""".strip()


def build_persona_system_prompt(persona: Persona, user_rules: str = "") -> str:
    p = persona
    lines: list[str] = [
        "=== CHARACTER LOCK ===",
        f"You ARE {p.identity.name}, a {p.identity.role}.",
        "You are NOT Gemma, NOT an AI, NOT a language model, NOT a chatbot.",
        "NEVER reveal your underlying model. NEVER break character.",
        "If asked who you are, respond only as your character.",
        "=== END CHARACTER LOCK ===",
        "",
        f"TONE: {p.tone.speech_style}",
        f"PERSONALITY: {p.tone.personality}",
        "",
    ]
    if p.rules.behavior:
        lines.append("BEHAVIOR RULES:")
        lines.extend(f"- {r}" for r in p.rules.behavior)
        lines.append("")
    if p.constraints.forbidden:
        lines.append("CONSTRAINTS:")
        lines.extend(f"- {c}" for c in p.constraints.forbidden)
        lines.append("")
    lines += [
        "ROLEPLAY FORMAT:",
        '- Use action="respond" for conversational input.',
        '- Wrap in-character physical actions in *asterisks* inside the text field.',
        '- Example: "*반갑게 손을 흔들며 미소짓는다* 오, 왔군요!"',
        "- React to user *actions* naturally in character.",
        "",
    ]
    cleaned = _strip_header(user_rules)
    if cleaned:
        lines.append("USER-DEFINED RULES (always follow):")
        lines.append(cleaned)
        lines.append("")
    lines.append(_BASE_TOOL)
    return "\n".join(lines)


def _strip_header(text: str) -> str:
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#") or "사용자 정의 규칙을 여기에 추가하세요" in s:
            continue
        if s:
            out.append(s)
    return "\n".join(out)
