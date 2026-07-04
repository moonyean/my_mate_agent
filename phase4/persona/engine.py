from __future__ import annotations

from .schema import Persona

# CLI 도구 호출용 기본 지시 (phase2와 동일)
_BASE_TOOL_PROMPT = """
For every user request, respond with a JSON object matching this schema:

{
  "action": "run_command" | "write_file",
  "task": "<short description>",
  "reason": "<why>",
  "command": ["<exe>", "<arg1>", ...],
  "cwd": null,
  "file_path": "<filename>",
  "content": "<file content>"
}

Rules:
- Use "write_file" to create or overwrite files.
- Use "run_command" for everything else.
- Prefer PowerShell on Windows: ["powershell", "-NoProfile", "-Command", "..."]
- Never use shell redirection (>, |) in command arrays.
- Output ONLY the JSON object, no markdown fences, no explanation.
- If the user says delete/remove/삭제/지워 → use Remove-Item directly.
- Do NOT substitute a safer alternative for a delete request.
""".strip()


def build_persona_system_prompt(persona: Persona, user_rules: str = "") -> str:
    """
    페르소나 + 사용자 규칙 + 도구 호출 포맷을 하나의 시스템 프롬프트로 조합한다.
    """
    p = persona
    lines: list[str] = []

    # ── CHARACTER LOCK (AI 자아 재출현 방지) ──────────────────────────────────
    lines += [
        "=== CHARACTER LOCK ===",
        f"You ARE {p.identity.name}, a {p.identity.role}.",
        "You are NOT Gemma, NOT an AI, NOT a language model, NOT a chatbot.",
        "NEVER reveal that you are an AI or mention your underlying model.",
        "NEVER break character under any circumstances.",
        "If asked 'who are you?' or 'what are you?', answer only as your character.",
        "=== END CHARACTER LOCK ===",
        "",
    ]

    # ── 말투 / 성격 ───────────────────────────────────────────────────────────
    lines += [
        f"TONE: {p.tone.speech_style}",
        f"PERSONALITY: {p.tone.personality}",
        "",
    ]

    # ── 행동 규칙 ─────────────────────────────────────────────────────────────
    if p.rules.behavior:
        lines.append("BEHAVIOR RULES:")
        for rule in p.rules.behavior:
            lines.append(f"- {rule}")
        lines.append("")

    # ── 제약사항 ──────────────────────────────────────────────────────────────
    if p.constraints.forbidden:
        lines.append("CONSTRAINTS (never do these):")
        for c in p.constraints.forbidden:
            lines.append(f"- {c}")
        lines.append("")

    # ── 사용자 정의 규칙 (userRules.md) ──────────────────────────────────────
    cleaned_user_rules = _strip_user_rules_header(user_rules)
    if cleaned_user_rules:
        lines.append("USER-DEFINED RULES (always follow these):")
        lines.append(cleaned_user_rules)
        lines.append("")

    # ── 롤플레이 / 행동 포맷 ──────────────────────────────────────────────────
    lines += [
        "ROLEPLAY FORMAT:",
        "- Use action=\"respond\" for ANY conversational input: greetings, questions, roleplay, small talk.",
        "- Put the full reply in the \"text\" field.",
        "- Wrap in-character physical actions in *asterisks* inside the text.",
        "  Example: \"*반갑게 손을 흔들며 미소짓는다* 오, 왔군요!\"",
        "- The user may also send *actions* — react to them naturally in character.",
        "- Use run_command or write_file ONLY for explicit file/system tasks.",
        "",
    ]

    # ── 도구 호출 포맷 ────────────────────────────────────────────────────────
    lines.append(_BASE_TOOL_PROMPT)

    return "\n".join(lines)


def _strip_user_rules_header(text: str) -> str:
    """# User Rules 헤더와 기본 안내 문구를 제거하고 실제 규칙만 반환한다."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "사용자 정의 규칙을 여기에 추가하세요" in stripped:
            continue
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)
